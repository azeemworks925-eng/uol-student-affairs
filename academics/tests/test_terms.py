"""Academic terms (Complaints Part 4 Stage 4a): model, database constraints, reporting window,
current-term services and their concurrency, and the migration."""

import threading
from datetime import date, datetime, timedelta, timezone as dt_timezone
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, connections, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from academics import services
from academics.models import REPORTING_TIME_ZONE, AcademicTerm, ProtectedTermError, TermQuerySet, term_window

TABLE = AcademicTerm._meta.db_table
UTC = dt_timezone.utc


def make_term(name="Fall 2026", start=date(2026, 9, 1), end=date(2027, 1, 15)):
    return AcademicTerm.objects.create(name=name, start_date=start, end_date=end)


def raw(sql, params=()):
    """Raw SQL, which skips every ORM guard: only the database constraints apply."""
    with connection.cursor() as cursor:
        cursor.execute(sql.format(table=connection.ops.quote_name(TABLE)), params)


def current_pks():
    return list(AcademicTerm.objects.filter(is_current=True).values_list("pk", flat=True))


class ModelTests(TestCase):
    def test_valid_term_and_its_labels(self):
        term = make_term()
        self.assertIsNone(term.is_current)
        self.assertEqual(str(term), "Fall 2026")
        self.assertEqual(term.dates_label, "1 Sep 2026 – 15 Jan 2027")

    def test_a_one_day_term_is_valid(self):
        term = AcademicTerm(name="Exam day", start_date=date(2026, 5, 1), end_date=date(2026, 5, 1))
        term.full_clean()
        term.save()

    def test_reversed_dates_are_a_validation_error(self):
        term = AcademicTerm(name="Backwards", start_date=date(2026, 9, 2), end_date=date(2026, 9, 1))
        with self.assertRaises(ValidationError) as ctx:
            term.full_clean()
        self.assertIn("end_date", ctx.exception.message_dict)

    def test_dates_at_the_ends_of_the_calendar_are_refused(self):
        for start, end, field in ((date(1, 1, 1), date(2026, 1, 1), "start_date"),
                                  (date(2026, 1, 1), date(9999, 12, 31), "end_date")):
            with self.subTest(field=field), self.assertRaises(ValidationError) as ctx:
                AcademicTerm(name="Edge", start_date=start, end_date=end).full_clean()
            self.assertIn(field, ctx.exception.message_dict)
        AcademicTerm(name="Edge", start_date=date(1900, 1, 1), end_date=date(9998, 12, 31)).full_clean()
        term_window(date(1900, 1, 1), date(9998, 12, 31))[1].astimezone(UTC)  # representable

    def test_database_refuses_reversed_dates(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_term("Backwards", start=date(2026, 9, 2), end=date(2026, 9, 1))

    def test_database_refuses_duplicate_names(self):
        make_term()
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_term()

    def test_duplicate_names_ignore_case_accents_and_spacing(self):
        make_term("Fall 2026")
        for name in ("fall 2026", "FÁLL 2026", "  Fall   2026 "):
            with self.subTest(name=name), self.assertRaises(ValidationError) as ctx:
                AcademicTerm(name=name, start_date=date(2026, 1, 1), end_date=date(2026, 2, 1)).full_clean()
            self.assertIn("name", ctx.exception.message_dict)

    def test_clean_normalises_spacing_and_allows_renaming_itself(self):
        term = make_term()
        term.name = "  Fall   2026  "
        term.full_clean()
        self.assertEqual(term.name, "Fall 2026")

    def test_many_terms_can_be_not_current(self):
        for name in ("A", "B", "C"):
            make_term(name)
        self.assertEqual(AcademicTerm.objects.filter(is_current__isnull=True).count(), 3)
        self.assertEqual(current_pks(), [])

    def test_ordering_is_newest_first(self):
        old = make_term("Spring 2026", date(2026, 2, 1), date(2026, 6, 30))
        new = make_term()
        self.assertEqual(list(AcademicTerm.objects.all()), [new, old])


class DatabaseConstraintTests(TestCase):
    """Raw SQL skips the ORM guards, so these show what MySQL and SQLite themselves enforce."""

    def setUp(self):
        self.a, self.b = make_term("A"), make_term("B")

    def test_one_current_term_is_accepted(self):
        raw("UPDATE {table} SET is_current = %s WHERE id = %s", [True, self.a.pk])
        self.assertEqual(current_pks(), [self.a.pk])

    def test_database_refuses_a_second_current_term(self):
        raw("UPDATE {table} SET is_current = %s WHERE id = %s", [True, self.a.pk])
        with self.assertRaises(IntegrityError), transaction.atomic():
            raw("UPDATE {table} SET is_current = %s WHERE id = %s", [True, self.b.pk])
        self.assertEqual(current_pks(), [self.a.pk])

    def test_database_refuses_false_and_other_values(self):
        for value in (False, 0, 2, -1):
            with self.subTest(value=value), self.assertRaises(IntegrityError), transaction.atomic():
                raw("UPDATE {table} SET is_current = %s WHERE id = %s", [value, self.a.pk])
        self.assertIsNone(AcademicTerm.objects.get(pk=self.a.pk).is_current)

    def test_a_second_truthy_value_cannot_make_two_current_terms(self):
        # Regression: on SQLite a check written as Q(is_current=True) is a bare truthiness
        # test, so 1 and 2 would both pass and the unique index would allow both.
        raw("UPDATE {table} SET is_current = %s WHERE id = %s", [1, self.a.pk])
        with self.assertRaises(IntegrityError), transaction.atomic():
            raw("UPDATE {table} SET is_current = %s WHERE id = %s", [2, self.b.pk])
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) FROM {connection.ops.quote_name(TABLE)} WHERE is_current IS NOT NULL")
            self.assertEqual(cursor.fetchone()[0], 1)

    def test_database_refuses_reversed_dates_on_update(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            raw("UPDATE {table} SET end_date = %s WHERE id = %s", [date(2026, 1, 1), self.a.pk])


class OrmGuardTests(TestCase):
    """The current flag changes only through academics.services; terms are never deleted."""

    def setUp(self):
        self.term = make_term()
        services.set_current_term(self.term)
        self.other = make_term("Spring 2026", date(2026, 2, 1), date(2026, 6, 30))

    def test_new_terms_cannot_be_created_current(self):
        for value in (True, False):
            with self.subTest(value=value), self.assertRaises(ProtectedTermError):
                AcademicTerm.objects.create(name=f"New {value}", start_date=date(2027, 2, 1),
                                            end_date=date(2027, 6, 1), is_current=value)

    def test_instance_save_cannot_change_the_flag(self):
        self.other.is_current = True
        with self.assertRaises(ProtectedTermError):
            self.other.save()
        self.term.is_current = None
        with self.assertRaises(ProtectedTermError):
            self.term.save(update_fields=["is_current"])
        self.assertEqual(current_pks(), [self.term.pk])

    def test_a_stale_copy_cannot_clear_the_flag(self):
        stale = AcademicTerm.objects.get(pk=self.other.pk)
        services.set_current_term(stale)
        self.other.name = "Renamed"  # self.other still says not current
        with self.assertRaises(ProtectedTermError):
            self.other.save()
        self.assertEqual(current_pks(), [self.other.pk])

    def test_an_unsaved_copy_with_an_existing_pk_cannot_clear_the_flag(self):
        forged = AcademicTerm(pk=self.term.pk, name="Forged", start_date=date(2026, 9, 1), end_date=date(2027, 1, 15))
        with self.assertRaises(ProtectedTermError):
            forged.save()
        self.assertEqual(AcademicTerm.objects.get(pk=self.term.pk).name, "Fall 2026")

    def test_other_fields_still_save(self):
        self.term.name = "Fall 2026 (main)"
        self.term.save()
        AcademicTerm.objects.filter(pk=self.other.pk).update(name="Spring 2026 (main)")
        self.term.refresh_from_db()
        self.assertEqual((self.term.name, self.term.is_current), ("Fall 2026 (main)", True))

    def test_bulk_paths_cannot_write_the_flag(self):
        with self.assertRaises(ProtectedTermError):
            AcademicTerm.objects.filter(pk=self.other.pk).update(is_current=True)
        with self.assertRaises(ProtectedTermError):
            AcademicTerm.objects.update(is_current=None)
        self.other.is_current = True
        with self.assertRaises(ProtectedTermError):
            AcademicTerm.objects.bulk_update([self.other], ["is_current"])
        with self.assertRaises(ProtectedTermError):
            AcademicTerm.objects.bulk_create([AcademicTerm(name="X", start_date=date(2027, 1, 1),
                                                           end_date=date(2027, 2, 1), is_current=True)])
        with self.assertRaises(ProtectedTermError):
            AcademicTerm.objects.bulk_create(
                [AcademicTerm(name="Fall 2026", start_date=date(2026, 9, 1), end_date=date(2027, 1, 15))],
                update_conflicts=True, update_fields=["is_current"], unique_fields=["name"],
            )
        self.assertEqual(current_pks(), [self.term.pk])

    def test_plain_bulk_create_still_works(self):
        AcademicTerm.objects.bulk_create([AcademicTerm(name="Bulk", start_date=date(2027, 2, 1), end_date=date(2027, 6, 1))])
        self.assertIsNone(AcademicTerm.objects.get(name="Bulk").is_current)

    def test_terms_cannot_be_deleted(self):
        with self.assertRaises(ProtectedTermError):
            self.other.delete()
        with self.assertRaises(ProtectedTermError):
            AcademicTerm.objects.all().delete()
        self.assertEqual(AcademicTerm.objects.count(), 2)


class WindowTests(TestCase):
    """One boundary rule: start date 00:00 Asia/Karachi inclusive, the day after the end date
    00:00 Asia/Karachi exclusive."""

    def test_window_is_local_midnight_to_the_midnight_after_the_end_date(self):
        start, end = term_window(date(2026, 9, 1), date(2027, 1, 15))
        self.assertEqual(start, datetime(2026, 9, 1, tzinfo=REPORTING_TIME_ZONE))
        self.assertEqual(end, datetime(2027, 1, 16, tzinfo=REPORTING_TIME_ZONE))
        self.assertEqual(make_term().window(), (start, end))

    def test_window_in_utc(self):
        # Asia/Karachi is UTC+05:00 with no daylight saving.
        start, end = term_window(date(2026, 9, 1), date(2027, 1, 15))
        self.assertEqual(start.astimezone(UTC), datetime(2026, 8, 31, 19, 0, tzinfo=UTC))
        self.assertEqual(end.astimezone(UTC), datetime(2027, 1, 15, 19, 0, tzinfo=UTC))

    def test_window_does_not_depend_on_the_active_time_zone(self):
        expected = term_window(date(2026, 9, 1), date(2027, 1, 15))
        with timezone.override("UTC"):
            self.assertEqual(term_window(date(2026, 9, 1), date(2027, 1, 15)), expected)
        with timezone.override("America/New_York"):
            self.assertEqual(term_window(date(2026, 9, 1), date(2027, 1, 15)), expected)

    def test_boundaries(self):
        start, end = term_window(date(2026, 9, 1), date(2027, 1, 15))

        def inside(moment):
            return start <= moment < end

        local = REPORTING_TIME_ZONE
        self.assertTrue(inside(datetime(2026, 9, 1, 0, 0, tzinfo=local)))  # exact start
        self.assertFalse(inside(datetime(2026, 9, 1, tzinfo=local) - timedelta(microseconds=1)))
        self.assertTrue(inside(datetime(2027, 1, 15, 23, 59, 59, 999999, tzinfo=local)))  # end date, late
        self.assertFalse(inside(datetime(2027, 1, 16, 0, 0, tzinfo=local)))  # midnight after the end date
        # The same instants written in UTC.
        self.assertTrue(inside(datetime(2026, 8, 31, 19, 0, tzinfo=UTC)))
        self.assertFalse(inside(datetime(2026, 8, 31, 18, 59, 59, tzinfo=UTC)))
        self.assertTrue(inside(datetime(2027, 1, 15, 18, 59, 59, tzinfo=UTC)))
        self.assertFalse(inside(datetime(2027, 1, 15, 19, 0, tzinfo=UTC)))


class ServiceTests(TestCase):
    def setUp(self):
        self.fall = make_term()
        self.spring = make_term("Spring 2026", date(2026, 2, 1), date(2026, 6, 30))

    def test_selecting_the_first_current_term(self):
        self.assertIsNone(services.current_term())
        previous, changed = services.set_current_term(self.fall)
        self.assertEqual((previous, changed, self.fall.is_current), (None, True, True))
        self.assertEqual(services.current_term(), self.fall)

    def test_switching_the_current_term(self):
        services.set_current_term(self.fall)
        previous, changed = services.set_current_term(self.spring)
        self.assertEqual((previous, changed), (self.fall, True))
        self.assertEqual(current_pks(), [self.spring.pk])

    def test_selecting_the_already_current_term_changes_nothing(self):
        services.set_current_term(self.fall)
        updated = AcademicTerm.objects.get(pk=self.fall.pk).updated_at
        previous, changed = services.set_current_term(self.fall)
        self.assertEqual((previous, changed), (self.fall, False))
        self.assertEqual(AcademicTerm.objects.get(pk=self.fall.pk).updated_at, updated)
        self.assertEqual(current_pks(), [self.fall.pk])

    def test_a_stale_instance_is_judged_by_the_database(self):
        stale = AcademicTerm.objects.get(pk=self.fall.pk)  # loaded while not current
        services.set_current_term(self.spring)
        services.set_current_term(stale)
        self.assertEqual(current_pks(), [self.fall.pk])

    def test_clearing_the_current_term(self):
        services.set_current_term(self.fall)
        previous, changed = services.clear_current_term()
        self.assertEqual((previous, changed), (self.fall, True))
        self.assertEqual(current_pks(), [])

    def test_clearing_when_none_is_current(self):
        self.assertEqual(services.clear_current_term(), (None, False))
        self.assertEqual(services.clear_current_term(expected=None), (None, False))

    def test_clearing_with_the_expected_term(self):
        services.set_current_term(self.fall)
        self.assertEqual(services.clear_current_term(expected=self.fall), (self.fall, True))

    def test_clearing_a_term_that_is_no_longer_current_changes_nothing(self):
        services.set_current_term(self.spring)
        with self.assertRaises(services.CurrentTermChanged) as ctx:
            services.clear_current_term(expected=self.fall)
        self.assertEqual(ctx.exception.args[0], self.spring)
        self.assertEqual(current_pks(), [self.spring.pk])

    def test_unsaved_or_missing_terms_are_refused(self):
        with self.assertRaises(AcademicTerm.DoesNotExist):
            services.set_current_term(AcademicTerm(name="Unsaved", start_date=date(2026, 1, 1), end_date=date(2026, 2, 1)))
        with self.assertRaises(AcademicTerm.DoesNotExist):
            services.set_current_term(None)
        gone = make_term("Gone")
        raw("DELETE FROM {table} WHERE id = %s", [gone.pk])
        with self.assertRaises(AcademicTerm.DoesNotExist):
            services.set_current_term(gone)
        self.assertEqual(current_pks(), [])

    def test_an_integrity_error_rolls_back_and_leaves_the_caller_usable(self):
        services.set_current_term(self.fall)
        real = TermQuerySet._write_current_flag
        calls = []

        def fail_on_set(queryset, value):
            calls.append(value)
            if value is True:
                raise IntegrityError("simulated duplicate current term")
            return real(queryset, value)

        with mock.patch.object(TermQuerySet, "_write_current_flag", fail_on_set):
            with self.assertRaises(services.CurrentTermConflict):
                services.set_current_term(self.spring)
        self.assertEqual(calls, [None, True])  # the old term was cleared before the failure ...
        self.assertEqual(current_pks(), [self.fall.pk])  # ... and that was rolled back
        # The surrounding transaction (this test's) is still usable.
        self.assertEqual(AcademicTerm.objects.count(), 2)

    def test_the_service_locks_every_term_in_primary_key_order(self):
        services.set_current_term(self.spring)
        with CaptureQueriesContext(connection) as queries:
            services.set_current_term(self.fall)
        statements = [q["sql"].upper() for q in queries.captured_queries if "SAVEPOINT" not in q["sql"].upper()]
        lock_sql = statements[0]
        self.assertTrue(lock_sql.startswith("SELECT"))
        self.assertNotIn("WHERE", lock_sql)  # every row, not only the current one
        self.assertIn("ORDER BY", lock_sql)
        if connection.features.has_select_for_update:
            self.assertIn("FOR UPDATE", lock_sql)
        # Then the old term is cleared before the new one is set.
        self.assertEqual(len(statements), 3)
        self.assertTrue(statements[1].startswith("UPDATE") and str(self.spring.pk) in statements[1])
        self.assertTrue(statements[2].startswith("UPDATE") and str(self.fall.pk) in statements[2])


@skipUnlessDBFeature("has_select_for_update")
class ConcurrencyTests(TransactionTestCase):
    """Real concurrent transactions on separate MySQL connections (one per thread)."""

    WAIT = 5  # seconds; generous so a slow machine does not fail the test

    def setUp(self):
        self.a = make_term("A", date(2026, 1, 1), date(2026, 6, 30))
        self.b = make_term("B", date(2026, 7, 1), date(2026, 12, 31))
        self.c = make_term("C", date(2027, 1, 1), date(2027, 6, 30))

    def in_thread(self, target, results, key):
        def run():
            try:
                results[key] = target()
            except Exception as error:  # reported by the test
                results[key] = error
            finally:
                connections.close_all()

        thread = threading.Thread(target=run)
        thread.start()
        return thread

    def hold_change(self, change, results):
        """Run `change` inside a transaction that stays open (locks held) until released."""
        locked, release = threading.Event(), threading.Event()

        def target():
            with transaction.atomic():
                outcome = change()
                locked.set()
                release.wait(self.WAIT * 2)
            return outcome

        thread = self.in_thread(target, results, "first")
        self.assertTrue(locked.wait(self.WAIT), "the first change did not take its locks")
        return thread, release

    def test_simultaneous_selection_is_serialised(self):
        results = {}
        first, release = self.hold_change(lambda: services.set_current_term(AcademicTerm.objects.get(pk=self.a.pk)), results)
        second = self.in_thread(lambda: services.set_current_term(AcademicTerm.objects.get(pk=self.b.pk)), results, "second")
        second.join(1)
        self.assertTrue(second.is_alive(), "the second change should wait for the first one's locks")
        self.assertEqual(current_pks(), [])  # nothing committed yet
        release.set()
        first.join(self.WAIT)
        second.join(self.WAIT)
        self.assertEqual(results["first"], (None, True))
        previous, changed = results["second"]
        self.assertEqual((previous.pk, changed), (self.a.pk, True))  # it saw the first change
        self.assertEqual(current_pks(), [self.b.pk])

    def test_clear_waits_for_a_selection_and_then_clears_it(self):
        results = {}
        first, release = self.hold_change(lambda: services.set_current_term(AcademicTerm.objects.get(pk=self.a.pk)), results)
        second = self.in_thread(services.clear_current_term, results, "second")
        second.join(1)
        self.assertTrue(second.is_alive())
        release.set()
        first.join(self.WAIT)
        second.join(self.WAIT)
        previous, changed = results["second"]
        self.assertEqual((previous.pk, changed), (self.a.pk, True))
        self.assertEqual(current_pks(), [])

    def test_a_stale_clear_after_a_concurrent_switch_changes_nothing(self):
        services.set_current_term(self.a)
        results = {}
        first, release = self.hold_change(lambda: services.set_current_term(AcademicTerm.objects.get(pk=self.b.pk)), results)
        second = self.in_thread(lambda: services.clear_current_term(expected=self.a), results, "second")
        second.join(1)
        self.assertTrue(second.is_alive())
        release.set()
        first.join(self.WAIT)
        second.join(self.WAIT)
        self.assertIsInstance(results["second"], services.CurrentTermChanged)
        self.assertEqual(current_pks(), [self.b.pk])

    def test_concurrent_clears(self):
        services.set_current_term(self.a)
        results = {}
        first, release = self.hold_change(services.clear_current_term, results)
        second = self.in_thread(services.clear_current_term, results, "second")
        second.join(1)
        self.assertTrue(second.is_alive())
        release.set()
        first.join(self.WAIT)
        second.join(self.WAIT)
        self.assertEqual(results["first"][1], True)
        self.assertEqual(results["second"], (None, False))  # it saw that nothing was current any more
        self.assertEqual(current_pks(), [])

    def test_many_writers_never_leave_two_current_terms_or_deadlock(self):
        terms = [self.a, self.b, self.c]
        barrier, errors = threading.Barrier(6), []

        def writer(index):
            try:
                barrier.wait()
                for step in range(8):
                    if (index + step) % 4 == 3:
                        services.clear_current_term()
                    else:
                        services.set_current_term(AcademicTerm.objects.get(pk=terms[(index + step) % 3].pk))
                    self.assertLessEqual(len(current_pks()), 1)
            except Exception as error:  # reported below
                errors.append(error)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)
        self.assertEqual(errors, [])
        self.assertLessEqual(len(current_pks()), 1)


class MigrationTests(TransactionTestCase):
    """academics.0002_academicterm is reversible on MySQL and SQLite."""

    def test_migration_can_be_reversed_and_reapplied(self):
        executor = MigrationExecutor(connection)
        executor.migrate([("academics", "0001_initial")])
        with connection.cursor() as cursor:
            self.assertNotIn(TABLE, connection.introspection.table_names(cursor))
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        with connection.cursor() as cursor:
            self.assertIn(TABLE, connection.introspection.table_names(cursor))
            constraints = connection.introspection.get_constraints(cursor, TABLE)
        self.assertIn("academic_term_dates_valid", constraints)
        self.assertIn("academic_term_current_true_or_null", constraints)
        unique_columns = [c["columns"] for c in constraints.values() if c["unique"] and not c["primary_key"]]
        self.assertIn(["is_current"], unique_columns)
        self.assertIn(["name"], unique_columns)
