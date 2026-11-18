"""Real concurrent transactions for CR/GR representation (Collective Issues CI-1;
COLLECTIVE_ISSUES_SPEC.md section 5.7). MySQL only: each operation runs on its own thread and
database connection, and the first holds its locks in an open transaction until released.

`race(first, second)`:
1. runs `first` in a transaction that stays open (its locks held);
2. starts `second` on another connection and checks that it waits on those locks;
3. releases `first` and returns both outcomes.
"""

import itertools
import threading

from django.core.exceptions import ValidationError
from django.db import connections, transaction
from django.test import TransactionTestCase, skipUnlessDBFeature

from academics.models import Batch, Section, Semester
from academics.services import set_entry_active
from accounts import representation as rep
from accounts import services
from accounts.models import CohortRepresentation, StudentProfile, User
from accounts.representation import Cohort

from .helpers import make_advisor, make_student, make_super_admin

WAIT = 5
_sap = itertools.count(46000000)


def student(cohort_tuple, name="Student"):
    return make_student(f"{next(_sap)}@student.uol.edu.pk", academics={"x": 1}, cohort=cohort_tuple, full_name=name)


def outcome(fn):
    try:
        return ("ok", fn())
    except ValidationError as error:
        return ("refused", error)
    except Exception as error:  # reported by the test
        return ("error", error)


@skipUnlessDBFeature("has_select_for_update")
class RepresentationRaceTests(TransactionTestCase):
    def setUp(self):
        self.batch = Batch.objects.create(name="Fall 2024")
        self.other_batch = Batch.objects.create(name="Spring 2025")
        self.semester = Semester.objects.create(number=4)
        self.section_a = Section.objects.create(name="A")
        self.section_b = Section.objects.create(name="B")
        self.home = (self.batch, self.semester, self.section_a)
        self.away = (self.batch, self.semester, self.section_b)
        self.cohort = Cohort(*(e.pk for e in self.home))
        self.away_cohort = Cohort(*(e.pk for e in self.away))
        self.admin = make_super_admin()
        self.advisor = make_advisor(cohorts=[self.home])
        self.s = [student(self.home, f"Home {i}") for i in range(5)]

    # ---- helpers ------------------------------------------------------------------------------

    def run_in_thread(self, fn, results, key):
        def target():
            try:
                results[key] = outcome(fn)
            finally:
                connections.close_all()

        thread = threading.Thread(target=target)
        thread.start()
        return thread

    def race(self, first, second, *, second_waits=True):
        results, locked, release = {}, threading.Event(), threading.Event()

        def held():
            with transaction.atomic():
                value = outcome(first)
                locked.set()
                release.wait(WAIT * 2)
                if value[0] != "ok":
                    return value
            return value

        def unwrap():
            value = held()
            if value[0] != "ok":
                raise RuntimeError(f"first operation failed: {value}")
            return value[1]

        a = self.run_in_thread(unwrap, results, "first")
        self.assertTrue(locked.wait(WAIT), "the first operation did not take its locks")
        b = self.run_in_thread(second, results, "second")
        b.join(1)
        if second_waits:
            self.assertTrue(b.is_alive(), "the second operation should wait for the first one's locks")
        release.set()
        a.join(WAIT * 2)
        b.join(WAIT * 2)
        self.assertFalse(a.is_alive() or b.is_alive(), "an operation did not finish (deadlock?)")
        self.assertEqual(results["first"][0], "ok", results["first"])
        return results["second"]

    def u(self, user):
        return User.objects.get(pk=user.pk)

    def current(self, cohort=None):
        return CohortRepresentation.objects.current().filter(**(cohort or self.cohort).filter()).first()

    def appoint(self, cr, gr, cohort=None):
        return lambda: rep.appoint_representatives(self.u(self.admin), cohort or self.cohort, cr=self.u(cr), gr=self.u(gr))

    def deactivate(self, user, replacement=None):
        return lambda: services.set_account_active(self.u(user), False, actor=self.u(self.admin),
                                                   replacement=self.u(replacement) if replacement else None)

    def move(self, user, section, replacement=None):
        return lambda: services.update_student_profile(
            StudentProfile.objects.get(user_id=user.pk), {"section": Section.objects.get(pk=section.pk)},
            actor=self.u(self.admin), replacement=self.u(replacement) if replacement else None)

    def entry_off(self, entry):
        return lambda: set_entry_active(type(entry).objects.get(pk=entry.pk), False, actor=self.u(self.admin))

    def register(self, user, section):
        return lambda: services.register_student(self.u(user), full_name="New Student", batch=self.batch,
                                                 semester=self.semester, section=Section.objects.get(pk=section.pk))

    def new_user(self):
        return User.objects.create_user(email=f"{next(_sap)}@student.uol.edu.pk", full_name="")

    # ---- 1. two simultaneous first appointments -------------------------------------------------

    def test_two_first_appointments_with_no_representation_row(self):
        self.assertIsNone(self.current())
        second = self.race(self.appoint(self.s[0], self.s[1]), self.appoint(self.s[2], self.s[3]))
        self.assertEqual(second[0], "refused")
        self.assertEqual(CohortRepresentation.objects.filter(**self.cohort.filter()).count(), 1)
        self.assertEqual((self.current().cr_id, self.current().gr_id), (self.s[0].pk, self.s[1].pk))

    # ---- 2. first appointment against registration ----------------------------------------------

    def test_first_appointment_then_registration(self):
        newcomer = self.new_user()
        second = self.race(self.appoint(self.s[0], self.s[1]), self.register(newcomer, self.section_a))
        self.assertEqual(second[0], "ok")  # a registration never affects existing posts
        self.assertEqual((self.current().cr_id, self.current().gr_id), (self.s[0].pk, self.s[1].pk))
        self.assertTrue(StudentProfile.objects.filter(user=newcomer, **self.cohort.filter()).exists())

    def test_registration_then_first_appointment_sees_the_newcomer(self):
        b1 = student(self.away, "B One")
        newcomer = self.new_user()
        # The appointment waits for the registration's cohort lock, then sees the newcomer as a
        # committed, eligible member of section B.
        second = self.race(self.register(newcomer, self.section_b), self.appoint(b1, newcomer, cohort=self.away_cohort))
        self.assertEqual(second[0], "ok")
        self.assertEqual(self.current(self.away_cohort).gr_id, newcomer.pk)

    # ---- 3. first appointment against candidate deactivation ------------------------------------

    def test_appointment_against_candidate_deactivation_deactivation_first(self):
        second = self.race(self.deactivate(self.s[1]), self.appoint(self.s[0], self.s[1]))
        self.assertEqual(second[0], "refused")
        self.assertIsNone(self.current())

    def test_appointment_against_candidate_deactivation_appointment_first(self):
        second = self.race(self.appoint(self.s[0], self.s[1]), self.deactivate(self.s[1]))
        self.assertEqual(second[0], "refused")  # a GR of a represented cohort with 3 others left
        self.assertTrue(self.u(self.s[1]).is_active)
        self.assertEqual(self.current().gr_id, self.s[1].pk)

    # ---- 4. first appointment against candidate cohort change -----------------------------------

    def test_appointment_against_candidate_cohort_change(self):
        second = self.race(self.move(self.s[0], self.section_b), self.appoint(self.s[0], self.s[1]))
        self.assertEqual(second[0], "refused")
        self.assertIsNone(self.current())

    # ---- 5. simultaneous replacement of the same post ---------------------------------------------

    def test_simultaneous_replacements_of_the_same_post(self):
        period = rep.appoint_representatives(self.admin, self.cohort, cr=self.s[0], gr=self.s[1])

        def replace(person):
            return lambda: rep.replace_representatives(self.u(self.admin), self.cohort, expected_period=period.pk,
                                                       cr=self.u(person))

        second = self.race(replace(self.s[2]), replace(self.s[3]))
        self.assertEqual(second[0], "refused")
        self.assertEqual(CohortRepresentation.objects.current().filter(**self.cohort.filter()).count(), 1)
        self.assertEqual(self.current().cr_id, self.s[2].pk)

    # ---- 6. replacement against the candidate's deactivation ------------------------------------

    def test_replacement_against_candidate_deactivation(self):
        period = rep.appoint_representatives(self.admin, self.cohort, cr=self.s[0], gr=self.s[1])
        second = self.race(self.deactivate(self.s[2]), lambda: rep.replace_representatives(
            self.u(self.admin), self.cohort, expected_period=period.pk, cr=self.u(self.s[2])))
        self.assertEqual(second[0], "refused")
        self.assertEqual(self.current().pk, period.pk)

    # ---- 7. registration or cohort change against a representative's deactivation ----------------

    def test_registration_against_closure_both_orders(self):
        pair = (self.other_batch, self.semester, self.section_a)
        x, y = student(pair, "X"), student(pair, "Y")
        pair_cohort = Cohort(*(e.pk for e in pair))
        rep.appoint_representatives(self.admin, pair_cohort, cr=x, gr=y)
        newcomer = self.new_user()

        def register_into_pair():
            return services.register_student(self.u(newcomer), full_name="New", batch=self.other_batch,
                                             semester=self.semester, section=self.section_a)

        # Registration first: three students, so deactivating the CR now needs a replacement.
        second = self.race(register_into_pair, self.deactivate(x))
        self.assertEqual(second[0], "refused")
        self.assertIsNotNone(self.current(pair_cohort))
        # Deactivation (with the newcomer as replacement) against a cohort change into the pair.
        second = self.race(self.deactivate(x, replacement=newcomer), self.move(self.s[4], self.section_a))
        self.assertEqual(second[0], "ok")
        self.assertEqual(self.current(pair_cohort).cr_id, newcomer.pk)

    def test_cohort_change_against_closure(self):
        pair = (self.other_batch, self.semester, self.section_b)
        x, y = student(pair, "X"), student(pair, "Y")
        pair_cohort = Cohort(*(e.pk for e in pair))
        rep.appoint_representatives(self.admin, pair_cohort, cr=x, gr=y)
        # Closing first (two students, CR leaves), then a student moves in: posts stay closed.
        second = self.race(self.deactivate(x), lambda: services.update_student_profile(
            StudentProfile.objects.get(user_id=self.s[4].pk),
            {"batch": Batch.objects.get(pk=self.other_batch.pk), "section": Section.objects.get(pk=self.section_b.pk)},
            actor=self.u(self.admin)))
        self.assertEqual(second[0], "ok")
        self.assertIsNone(self.current(pair_cohort))
        self.assertEqual(CohortRepresentation.objects.get(cr_id=x.pk).end_reason, "cohort_closed")

    # ---- 8. appointment and replacement against Section deactivation ------------------------------

    def test_appointment_against_section_deactivation_both_orders(self):
        second = self.race(self.appoint(self.s[0], self.s[1]), self.entry_off(self.section_a))
        self.assertEqual(second[0], "ok")
        self.assertIsNotNone(self.current())  # represented, now inactive: the period stays
        set_entry_active(self.section_a, True, actor=self.admin)
        period = self.current()
        second = self.race(self.entry_off(self.section_a), lambda: rep.replace_representatives(
            self.u(self.admin), self.cohort, expected_period=period.pk, cr=self.u(self.s[2])))
        self.assertEqual(second[0], "refused")
        self.assertEqual(self.current().pk, period.pk)

    def test_section_deactivation_first_refuses_the_first_appointment(self):
        second = self.race(self.entry_off(self.section_a), self.appoint(self.s[0], self.s[1]))
        self.assertEqual(second[0], "refused")
        self.assertIsNone(self.current())

    # ---- 9. and 10. Batch and Semester deactivation ---------------------------------------------

    def test_appointment_against_batch_deactivation_both_orders(self):
        second = self.race(self.appoint(self.s[0], self.s[1]), self.entry_off(self.batch))
        self.assertEqual(second[0], "ok")
        self.assertIsNotNone(self.current())  # 13: existing periods unchanged
        set_entry_active(self.batch, True, actor=self.admin)
        second = self.race(self.entry_off(self.batch), self.appoint(self.s[2], self.s[3], cohort=self.away_cohort_of(2)))
        self.assertEqual(second[0], "refused")

    def test_appointment_against_semester_deactivation_both_orders(self):
        second = self.race(self.appoint(self.s[0], self.s[1]), self.entry_off(self.semester))
        self.assertEqual(second[0], "ok")
        self.assertIsNotNone(self.current())
        set_entry_active(self.semester, True, actor=self.admin)
        second = self.race(self.entry_off(self.semester), self.appoint(self.s[2], self.s[3], cohort=self.away_cohort_of(2)))
        self.assertEqual(second[0], "refused")

    def away_cohort_of(self, count):
        """Move `count` free students into section B (an awaiting cohort) for a second first appointment."""
        for user in self.s[2:2 + count]:
            services.update_student_profile(StudentProfile.objects.get(user_id=user.pk),
                                            {"section": self.section_b}, actor=self.admin)
        return self.away_cohort

    # ---- 11. registration and cohort change against academic deactivation --------------------------

    def test_registration_and_cohort_change_against_entry_deactivation(self):
        for entry in (self.batch, self.semester, self.section_b):
            with self.subTest(entry=str(entry)):
                newcomer = self.new_user()
                second = self.race(self.entry_off(entry), self.register(newcomer, self.section_b))
                self.assertEqual(second[0], "refused")
                self.assertFalse(StudentProfile.objects.filter(user=newcomer).exists())
                second = self.race(self.entry_off(entry), self.move(self.s[4], self.section_b))
                self.assertEqual(second[0], "refused")
                set_entry_active(type(entry).objects.get(pk=entry.pk), True, actor=self.admin)

    # ---- 12. and 14. no deadlock ---------------------------------------------------------------------

    def test_multi_row_section_save_against_cohort_changes_does_not_deadlock(self):
        section_c = Section.objects.create(name="C")
        movers = [student((self.batch, self.semester, s), f"Mover {s.name}") for s in (self.section_b, section_c)]
        barrier, errors = threading.Barrier(3), []

        def admin_save():
            # A list-editable save changes several Section rows in display order (C before A).
            with transaction.atomic():
                for section in (section_c, self.section_a):
                    set_entry_active(Section.objects.get(pk=section.pk), True, actor=self.u(self.admin))

        def change(user, section):
            return lambda: services.update_student_profile(
                StudentProfile.objects.get(user_id=user.pk), {"section": Section.objects.get(pk=section.pk)},
                actor=self.u(self.admin))

        jobs = [admin_save, change(movers[0], section_c), change(movers[1], self.section_b)]

        def wrap(job):
            try:
                barrier.wait()
                for _ in range(5):
                    job()
            except Exception as error:  # reported below
                errors.append(error)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=wrap, args=(job,)) for job in jobs]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)
        self.assertFalse(any(t.is_alive() for t in threads), "deadlock")
        self.assertEqual(errors, [])

    def test_opposite_cohort_changes_do_not_deadlock(self):
        b_student = student(self.away, "B")
        barrier, errors = threading.Barrier(2), []

        def bounce(user, first, then):
            def job():
                try:
                    barrier.wait()
                    for i in range(6):
                        target = first if i % 2 == 0 else then
                        services.update_student_profile(StudentProfile.objects.get(user_id=user.pk),
                                                        {"section": Section.objects.get(pk=target.pk)},
                                                        actor=self.u(self.admin))
                except Exception as error:  # reported below
                    errors.append(error)
                finally:
                    connections.close_all()
            return job

        threads = [threading.Thread(target=bounce(self.s[4], self.section_b, self.section_a)),
                   threading.Thread(target=bounce(b_student, self.section_a, self.section_b))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)
        self.assertFalse(any(t.is_alive() for t in threads), "deadlock")
        self.assertEqual(errors, [])
