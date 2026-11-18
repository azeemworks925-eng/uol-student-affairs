"""CR/GR cohort representation (Collective Issues CI-1; COLLECTIVE_ISSUES_SPEC.md section 5;
DEC-016, DEC-212, DEC-245, DEC-323, DEC-324; one post per student: DEC-240). The
multi-connection MySQL races are in test_representation_concurrency."""

import itertools
from unittest import mock

from django.contrib.messages import get_messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from academics.models import Batch, Section, Semester
from academics.services import set_entry_active
from accounts import representation as rep
from accounts import services
from accounts.models import (
    REPRESENTATION_END_REASONS,
    CohortRepresentation,
    ProtectedRepresentationError,
    StudentProfile,
    StudentProfileChange,
    User,
)
from accounts.representation import Cohort

from .helpers import make_academics, make_advisor, make_student, make_super_admin

Reason = CohortRepresentation.EndReason
TABLE = CohortRepresentation._meta.db_table
_sap = itertools.count(41000000)


def student(cohort_tuple, name="Student", *, active=True):
    user = make_student(f"{next(_sap)}@student.uol.edu.pk", academics={"x": 1}, cohort=cohort_tuple, full_name=name)
    if not active:
        User.objects.filter(pk=user.pk).update(is_active=False)
        user.refresh_from_db()
    return user


def current(cohort):
    return CohortRepresentation.objects.current().filter(**cohort.filter()).first()


class RepresentationTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = make_academics()
        cls.home = (cls.a["batch"], cls.a["semester"], cls.a["section"])
        cls.other = (cls.a["other_batch"], cls.a["semester"], cls.a["section"])
        cls.cohort = Cohort(*(e.pk for e in cls.home))
        cls.other_cohort = Cohort(*(e.pk for e in cls.other))
        cls.admin = make_super_admin()
        cls.advisor = make_advisor(cohorts=[cls.home], full_name="Dr. Ayesha Rahman")
        cls.outsider = make_advisor("otheradvisor@uol.edu.pk", cohorts=[cls.other], full_name="Other Advisor")
        cls.s = [student(cls.home, f"Home {i}") for i in range(5)]
        cls.away = student(cls.other, "Away Student")

    def appoint(self, cr=None, gr=None, actor=None):
        return rep.appoint_representatives(actor or self.admin, self.cohort, cr=cr or self.s[0], gr=gr or self.s[1])


# ---------------------------------------------------------------------------------------------
# Model and database
# ---------------------------------------------------------------------------------------------

class DatabaseConstraintTests(RepresentationTestCase):
    """Raw SQL skips every ORM guard: these are what MySQL and SQLite themselves enforce."""

    def insert(self, cr, gr, cohort=None, is_active=True, ended=False, reason=""):
        cohort = cohort or self.cohort
        with connection.cursor() as cursor:
            cursor.execute(
                f"INSERT INTO {connection.ops.quote_name(TABLE)} (batch_id, semester_id, section_id, cr_id, gr_id, "
                "is_active, started_at, ended_at, end_reason) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                [cohort.batch_id, cohort.semester_id, cohort.section_id, cr.pk, gr.pk, is_active,
                 "2026-11-18 10:00:00", "2026-11-18 11:00:00" if ended else None, reason])

    def refused(self, **kwargs):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.insert(**kwargs)

    def test_a_period_names_two_different_students(self):
        self.refused(cr=self.s[0], gr=self.s[0])

    def test_one_current_period_per_cohort(self):
        self.insert(self.s[0], self.s[1])
        self.refused(cr=self.s[2], gr=self.s[3])
        self.insert(self.s[2], self.s[3], is_active=None, ended=True, reason="cr_replaced")  # history is fine

    def test_a_student_holds_one_current_post_per_role(self):
        self.insert(self.s[0], self.s[1])
        self.refused(cr=self.s[0], gr=self.away, cohort=self.other_cohort)
        self.refused(cr=self.away, gr=self.s[1], cohort=self.other_cohort)

    def test_current_flag_and_ending_are_consistent(self):
        self.refused(cr=self.s[0], gr=self.s[1], is_active=False)
        self.refused(cr=self.s[0], gr=self.s[1], is_active=None)  # ended without a date or reason
        self.refused(cr=self.s[0], gr=self.s[1], is_active=None, ended=True, reason="unknown_reason")
        self.refused(cr=self.s[0], gr=self.s[1], is_active=True, ended=True, reason="cr_replaced")

    def test_end_reason_values_match_the_model(self):
        self.assertEqual(tuple(Reason.values), REPRESENTATION_END_REASONS)


class OrmGuardTests(RepresentationTestCase):
    def test_periods_are_never_edited_or_deleted_through_the_orm(self):
        period = self.appoint()
        with self.assertRaises(ProtectedRepresentationError):
            CohortRepresentation.objects.filter(pk=period.pk).update(gr=self.s[2])
        with self.assertRaises(ProtectedRepresentationError):
            CohortRepresentation.objects.all().delete()
        with self.assertRaises(ProtectedRepresentationError):
            period.delete()
        period.gr = self.s[2]
        with self.assertRaises(ProtectedRepresentationError):
            period.save()
        with self.assertRaises(ProtectedRepresentationError):
            CohortRepresentation.objects.bulk_update([period], ["gr"])
        with self.assertRaises(ProtectedRepresentationError):
            CohortRepresentation(cr=self.s[2], gr=self.s[3], is_active=None, **self.other_cohort.filter()).save()
        self.assertEqual(current(self.cohort).gr_id, self.s[1].pk)


class MigrationTests(TransactionTestCase):
    def test_migration_is_additive_and_reversible(self):
        executor = MigrationExecutor(connection)
        executor.migrate([("accounts", "0003_advisor_assignment_batch")])
        with connection.cursor() as cursor:
            self.assertNotIn(TABLE, connection.introspection.table_names(cursor))
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, TABLE)
        for name in ("representation_cr_gr_different", "representation_one_current_per_cohort",
                     "representation_one_current_cr_post", "representation_one_current_gr_post",
                     "representation_current_true_or_null", "representation_ending_consistent"):
            self.assertIn(name, constraints)


# ---------------------------------------------------------------------------------------------
# Appointment, replacement, swap
# ---------------------------------------------------------------------------------------------

class AppointmentTests(RepresentationTestCase):
    def test_both_posts_are_appointed_together(self):
        with self.assertRaises(ValidationError):
            rep.appoint_representatives(self.admin, self.cohort, cr=self.s[0], gr=None)
        period = self.appoint()
        self.assertEqual((period.cr_id, period.gr_id, period.started_by_id), (self.s[0].pk, self.s[1].pk, self.admin.pk))

    def test_assigned_advisor_may_appoint_and_others_may_not(self):
        with self.assertRaises(PermissionDenied):
            self.appoint(actor=self.outsider)
        with self.assertRaises(PermissionDenied):
            self.appoint(actor=self.s[4])
        self.assertIsNotNone(self.appoint(actor=self.advisor))

    def test_candidates_must_be_eligible(self):
        inactive = student(self.home, "Inactive", active=False)
        cases = [(self.s[0], self.s[0], "gr"), (self.away, self.s[1], "cr"), (self.s[0], inactive, "gr"),
                 (self.s[0], self.advisor, "gr")]
        for cr, gr, field in cases:
            with self.subTest(cr=cr.full_name, gr=gr.full_name), self.assertRaises(ValidationError) as ctx:
                self.appoint(cr=cr, gr=gr)
            self.assertIn(field, ctx.exception.message_dict)
        self.assertIsNone(current(self.cohort))

    def test_a_post_holder_elsewhere_is_not_eligible(self):
        away2 = student(self.other, "Away Two")
        rep.appoint_representatives(self.admin, self.other_cohort, cr=self.away, gr=away2)
        # Only reachable by bypassing the services (a raw cohort change); still refused.
        StudentProfile.objects.filter(user=self.away).update(batch=self.a["batch"])
        with self.assertRaises(ValidationError) as ctx:
            self.appoint(cr=self.away, gr=self.s[1])
        self.assertIn("already holds", ctx.exception.message_dict["cr"][0])
        self.assertIsNone(current(self.cohort))

    def test_already_represented_and_inactive_cohorts_are_refused(self):
        self.appoint()
        with self.assertRaises(ValidationError):
            self.appoint(cr=self.s[2], gr=self.s[3])
        cohort3 = (self.a["batch"], self.a["other_semester"], self.a["section"])
        x, y = student(cohort3, "X"), student(cohort3, "Y")
        set_entry_active(self.a["other_semester"], False, actor=self.admin)
        with self.assertRaises(ValidationError):
            rep.appoint_representatives(self.admin, Cohort(*(e.pk for e in cohort3)), cr=x, gr=y)


class ReplacementTests(RepresentationTestCase):
    def setUp(self):
        self.period = self.appoint()

    def test_replace_cr_gr_both_and_swap_keep_history(self):
        p2 = rep.replace_representatives(self.admin, self.cohort, expected_period=self.period.pk, cr=self.s[2])
        self.assertEqual((p2.cr_id, p2.gr_id), (self.s[2].pk, self.s[1].pk))
        p3 = rep.replace_representatives(self.admin, self.cohort, expected_period=p2.pk, gr=self.s[3])
        p4 = rep.replace_representatives(self.admin, self.cohort, expected_period=p3.pk, cr=self.s[0], gr=self.s[4])
        p5 = rep.swap_representatives(self.advisor, self.cohort, expected_period=p4.pk)
        self.assertEqual((p5.cr_id, p5.gr_id), (self.s[4].pk, self.s[0].pk))
        history = list(CohortRepresentation.objects.filter(**self.cohort.filter()).order_by("pk"))
        self.assertEqual([p.end_reason for p in history],
                         ["cr_replaced", "gr_replaced", "both_replaced", "both_replaced", ""])
        self.assertEqual([p.is_active for p in history], [None, None, None, None, True])
        self.assertTrue(all(p.ended_at and p.ended_by_id for p in history[:-1]))

    def test_stale_form_is_refused(self):
        rep.replace_representatives(self.admin, self.cohort, expected_period=self.period.pk, cr=self.s[2])
        with self.assertRaises(ValidationError):
            rep.replace_representatives(self.admin, self.cohort, expected_period=self.period.pk, cr=self.s[3])
        self.assertEqual(current(self.cohort).cr_id, self.s[2].pk)

    def test_removal_without_replacement_is_refused(self):
        with self.assertRaises(ValidationError):
            rep.replace_representatives(self.admin, self.cohort, expected_period=self.period.pk)
        with self.assertRaises(ValidationError):
            rep.replace_representatives(self.admin, self.cohort, expected_period=self.period.pk, cr=self.s[0])
        with self.assertRaises(ValidationError):
            rep.replace_representatives(self.admin, self.cohort, expected_period=self.period.pk, cr=self.s[1])
        self.assertEqual(current(self.cohort).pk, self.period.pk)

    def test_no_remove_operation_exists(self):
        self.assertFalse(any("remove" in name for name in dir(rep) + dir(services)))

    def test_a_failed_insert_rolls_back_the_ending(self):
        with mock.patch.object(rep, "_start", side_effect=ValidationError("injected")):
            with self.assertRaises(ValidationError):
                rep.replace_representatives(self.admin, self.cohort, expected_period=self.period.pk, cr=self.s[2])
        self.assertEqual(current(self.cohort).pk, self.period.pk)


# ---------------------------------------------------------------------------------------------
# Lifecycle: deactivation and cohort change (DEC-212, DEC-323)
# ---------------------------------------------------------------------------------------------

class DeactivationTests(RepresentationTestCase):
    def setUp(self):
        self.period = self.appoint()

    def test_deactivating_a_representative_needs_a_replacement(self):
        with self.assertRaises(ValidationError) as ctx:
            services.set_account_active(self.s[0], False, actor=self.admin)
        self.assertIn("replacement", ctx.exception.message_dict)
        self.assertIn("CR", ctx.exception.message_dict["replacement"][0])
        self.s[0].refresh_from_db()
        self.assertTrue(self.s[0].is_active)
        self.assertEqual(current(self.cohort).pk, self.period.pk)

    def test_deactivation_with_a_replacement_is_atomic(self):
        services.set_account_active(self.s[1], False, actor=self.admin, replacement=self.s[2])
        self.assertFalse(User.objects.get(pk=self.s[1].pk).is_active)
        period = current(self.cohort)
        self.assertEqual((period.cr_id, period.gr_id), (self.s[0].pk, self.s[2].pk))
        self.assertEqual(CohortRepresentation.objects.get(pk=self.period.pk).end_reason, Reason.GR_REPLACED)

    def test_closure_when_fewer_than_two_active_students_remain(self):
        cohort3 = (self.a["batch"], self.a["semester"], self.a["other_section"])
        x, y = student(cohort3, "X"), student(cohort3, "Y")
        c3 = Cohort(*(e.pk for e in cohort3))
        first = rep.appoint_representatives(self.admin, c3, cr=x, gr=y)
        services.set_account_active(x, False, actor=self.admin)
        self.assertIsNone(current(c3))
        self.assertEqual(CohortRepresentation.objects.get(pk=first.pk).end_reason, Reason.COHORT_CLOSED)

    def test_inactive_cohort_period_simply_ends(self):
        set_entry_active(self.a["batch"], False, actor=self.admin)
        services.set_account_active(self.s[0], False, actor=self.admin)
        self.assertIsNone(current(self.cohort))
        self.assertEqual(CohortRepresentation.objects.get(pk=self.period.pk).end_reason, Reason.STUDENT_DEACTIVATED)

    def test_reactivation_never_restores_a_post(self):
        services.set_account_active(self.s[0], False, actor=self.admin, replacement=self.s[2])
        services.set_account_active(self.s[0], True, actor=self.admin)
        self.assertTrue(User.objects.get(pk=self.s[0].pk).is_active)
        self.assertEqual(current(self.cohort).cr_id, self.s[2].pk)

    def test_failure_rolls_back_account_and_representation(self):
        with mock.patch.object(rep, "_start", side_effect=RuntimeError("injected")):
            with self.assertRaises(RuntimeError):
                services.set_account_active(self.s[0], False, actor=self.admin, replacement=self.s[2])
        self.assertTrue(User.objects.get(pk=self.s[0].pk).is_active)
        self.assertEqual(current(self.cohort).pk, self.period.pk)

    def test_non_representatives_and_staff_are_unaffected(self):
        services.set_account_active(self.s[4], False, actor=self.admin)
        services.set_account_active(self.outsider, False, actor=self.admin)
        self.assertEqual(current(self.cohort).pk, self.period.pk)

    def test_last_active_super_admin_is_protected(self):
        with self.assertRaises(ValidationError) as ctx:
            services.set_account_active(self.admin, False, actor=self.admin)
        self.assertEqual(ctx.exception.message_dict["is_active"], [services.LAST_SUPER_ADMIN])
        second = make_super_admin("deputy@uol.edu.pk")
        services.set_account_active(second, False, actor=self.admin)
        self.assertFalse(User.objects.get(pk=second.pk).is_active)


class CohortChangeTests(RepresentationTestCase):
    def setUp(self):
        self.period = self.appoint()
        self.profile = StudentProfile.objects.get(user=self.s[0])

    def move(self, profile=None, replacement=None, to=None):
        to = to or {"batch": self.a["other_batch"]}
        return services.update_student_profile(profile or self.profile, to, actor=self.admin, replacement=replacement)

    def test_moving_a_representative_needs_a_replacement(self):
        with self.assertRaises(ValidationError):
            self.move()
        self.assertEqual(StudentProfile.objects.get(pk=self.profile.pk).batch_id, self.a["batch"].pk)
        self.assertFalse(StudentProfileChange.objects.exists())

    def test_move_with_replacement_is_atomic_and_audited(self):
        self.move(replacement=self.s[3])
        self.assertEqual(StudentProfile.objects.get(pk=self.profile.pk).batch_id, self.a["other_batch"].pk)
        self.assertEqual(current(self.cohort).cr_id, self.s[3].pk)
        change = StudentProfileChange.objects.get()
        self.assertEqual((change.field_name, change.new_value, change.changed_by_id), ("batch", "Spring 2025", self.admin.pk))

    def test_failure_after_the_profile_rolls_everything_back(self):
        with mock.patch.object(services, "record_profile_changes", side_effect=RuntimeError("injected")):
            with self.assertRaises(RuntimeError):
                self.move(replacement=self.s[3])
        self.assertEqual(StudentProfile.objects.get(pk=self.profile.pk).batch_id, self.a["batch"].pk)
        self.assertEqual(current(self.cohort).pk, self.period.pk)
        self.assertFalse(StudentProfileChange.objects.exists())

    def test_moving_into_an_inactive_cohort_is_refused(self):
        set_entry_active(self.a["other_batch"], False, actor=self.admin)
        profile = StudentProfile.objects.get(user=self.s[4])
        with self.assertRaises(ValidationError):
            self.move(profile=profile)

    def test_closure_when_the_move_leaves_fewer_than_two(self):
        cohort3 = (self.a["batch"], self.a["semester"], self.a["other_section"])
        x, y = student(cohort3, "X"), student(cohort3, "Y")
        p3 = rep.appoint_representatives(self.admin, Cohort(*(e.pk for e in cohort3)), cr=x, gr=y)
        self.move(profile=StudentProfile.objects.get(user=x), to={"section": self.a["section"]})
        self.assertEqual(CohortRepresentation.objects.get(pk=p3.pk).end_reason, Reason.COHORT_CLOSED)

    def test_moving_out_of_an_inactive_cohort_ends_the_period(self):
        set_entry_active(self.a["section"], False, actor=self.admin)  # home becomes inactive
        target = {"batch": self.a["other_batch"], "semester": self.a["other_semester"], "section": self.a["other_section"]}
        self.move(to=target)  # no replacement needed or possible (DEC-324)
        self.assertEqual(CohortRepresentation.objects.get(pk=self.period.pk).end_reason, Reason.COHORT_CHANGED)
        self.assertIsNone(current(self.cohort))

    def test_arriving_students_never_change_posts(self):
        services.update_student_profile(StudentProfile.objects.get(user=self.away), {"batch": self.a["batch"]}, actor=self.admin)
        self.assertEqual(current(self.cohort).pk, self.period.pk)


class AcademicStructureTests(RepresentationTestCase):
    def test_deactivation_keeps_periods_and_locks_all_sections(self):
        period = self.appoint()
        Section.objects.create(name="C")
        with mock.patch("academics.services.Section.objects.select_for_update", wraps=Section.objects.select_for_update) as locked:
            set_entry_active(self.a["batch"], False, actor=self.admin)
        locked.assert_called()
        self.assertEqual(current(self.cohort).pk, period.pk)  # no closure (DEC-323, DEC-324)
        self.assertFalse(Batch.objects.get(pk=self.a["batch"].pk).is_active)
        set_entry_active(self.a["semester"], False, actor=self.admin)
        set_entry_active(self.a["section"], False, actor=self.admin)
        self.assertEqual(current(self.cohort).pk, period.pk)
        self.assertFalse(Semester.objects.get(pk=self.a["semester"].pk).is_active)

    def test_registration_of_an_inactive_account_is_refused(self):
        user = User.objects.create_user(email=f"{next(_sap)}@student.uol.edu.pk", full_name="")
        stale = User.objects.get(pk=user.pk)  # the caller's instance still says active
        User.objects.filter(pk=user.pk).update(is_active=False)
        with self.assertRaisesMessage(ValidationError, services.INACTIVE_ACCOUNT):
            services.register_student(stale, full_name="New", batch=self.a["batch"], semester=self.a["semester"],
                                      section=self.a["section"])
        self.assertFalse(StudentProfile.objects.filter(user=user).exists())
        self.assertEqual(User.objects.get(pk=user.pk).full_name, "")

    def test_registration_rechecks_role_under_the_lock(self):
        user = User.objects.create_user(email=f"{next(_sap)}@student.uol.edu.pk", full_name="")
        stale = User.objects.get(pk=user.pk)
        User.objects.filter(pk=user.pk).update(role=User.Role.BATCH_ADVISOR)
        with self.assertRaises(ValueError):
            services.register_student(stale, full_name="New", batch=self.a["batch"], semester=self.a["semester"],
                                      section=self.a["section"])
        self.assertFalse(StudentProfile.objects.filter(user=user).exists())

    def test_registration_rechecks_the_profile_after_locking(self):
        user = User.objects.create_user(email=f"{next(_sap)}@student.uol.edu.pk", full_name="")
        real_lock_users = services.lock_users

        def concurrent_registration_commits_first(ids):
            # Simulates a registration that committed while this one waited for its locks.
            StudentProfile.objects.create(user=user, batch=self.a["batch"], semester=self.a["semester"],
                                          section=self.a["other_section"])
            return real_lock_users(ids)

        with mock.patch("accounts.services.lock_users", side_effect=concurrent_registration_commits_first):
            with self.assertRaises(services.AlreadyRegistered):
                services.register_student(user, full_name="Second", batch=self.a["batch"],
                                          semester=self.a["semester"], section=self.a["section"])
        # The simulated profile shares this test's transaction, so the refusal rolls it back too;
        # what matters is that no second profile or name change was written.
        self.assertFalse(StudentProfile.objects.filter(user=user, section=self.a["section"]).exists())
        self.assertEqual(User.objects.get(pk=user.pk).full_name, "")

    def test_registration_uses_the_locked_user_row(self):
        user = User.objects.create_user(email=f"{next(_sap)}@student.uol.edu.pk", full_name="")
        stale = User.objects.get(pk=user.pk)
        User.objects.filter(pk=user.pk).update(is_staff=True)  # changed elsewhere meanwhile
        profile = services.register_student(stale, full_name="  New Student ", batch=self.a["batch"],
                                            semester=self.a["semester"], section=self.a["section"])
        fresh = User.objects.get(pk=user.pk)
        self.assertEqual((fresh.full_name, fresh.is_staff), ("New Student", True))  # nothing overwritten
        self.assertEqual(stale.full_name, "New Student")
        self.assertEqual(profile.user_id, user.pk)

    def test_deactivating_an_unregistered_student_locks_every_section(self):
        user = User.objects.create_user(email=f"{next(_sap)}@student.uol.edu.pk", full_name="")
        with mock.patch("accounts.services.lock_all_sections", wraps=rep.lock_all_sections) as locked:
            services.set_account_active(user, False, actor=self.admin)
        locked.assert_called_once()
        self.assertFalse(User.objects.get(pk=user.pk).is_active)
        with mock.patch("accounts.services.lock_all_sections") as locked:
            services.set_account_active(self.s[4], False, actor=self.admin)  # registered: its cohort only
            services.set_account_active(self.outsider, False, actor=self.admin)  # staff: unchanged
        locked.assert_not_called()

    def test_registration_into_an_inactive_cohort_is_refused(self):
        user = User.objects.create_user(email=f"{next(_sap)}@student.uol.edu.pk", full_name="")
        set_entry_active(self.a["section"], False, actor=self.admin)
        with self.assertRaises(ValidationError):
            services.register_student(user, full_name="New", batch=self.a["batch"], semester=self.a["semester"],
                                      section=self.a["section"])
        self.assertFalse(StudentProfile.objects.filter(user=user).exists())


# ---------------------------------------------------------------------------------------------
# Authority and consistency checks (spec 5.3)
# ---------------------------------------------------------------------------------------------

class AuthorityTests(RepresentationTestCase):
    def test_current_and_acting_representative(self):
        self.assertIsNone(rep.current_representative(self.s[0]))
        period = self.appoint()
        self.assertEqual(rep.current_representative(self.s[0]).pk, period.pk)
        self.assertEqual(rep.can_act_as_representative(self.s[1]).pk, period.pk)
        self.assertIsNone(rep.current_representative(self.s[2]))
        set_entry_active(self.a["semester"], False, actor=self.admin)
        self.assertEqual(rep.current_representative(self.s[0]).pk, period.pk)  # history stays viewable
        self.assertIsNone(rep.can_act_as_representative(self.s[0]))  # no new actions

    def test_checks_read_the_database_when_services_are_bypassed(self):
        period = self.appoint()
        StudentProfile.objects.filter(user=self.s[0]).update(batch=self.a["other_batch"])  # bypasses the services
        self.assertIsNone(rep.current_representative(User.objects.get(pk=self.s[0].pk)))
        User.objects.filter(pk=self.s[1].pk).update(is_active=False)
        self.assertIsNone(rep.can_act_as_representative(User.objects.get(pk=self.s[1].pk)))
        breaches = rep.representation_breaches()
        self.assertEqual([(p.pk, posts) for p, posts in breaches], [(period.pk, ["cr", "gr"])])

    def test_no_breach_in_normal_operation(self):
        self.appoint()
        services.set_account_active(self.s[0], False, actor=self.admin, replacement=self.s[2])
        self.assertEqual(rep.representation_breaches(), [])


# ---------------------------------------------------------------------------------------------
# Admin integration
# ---------------------------------------------------------------------------------------------

class AdminIntegrationTests(RepresentationTestCase):
    def setUp(self):
        self.client.force_login(self.admin)
        self.period = self.appoint()

    def user_url(self, user):
        return reverse("admin:accounts_user_change", args=[user.pk])

    def test_deactivation_form_offers_and_requires_a_replacement(self):
        page = self.client.get(self.user_url(self.s[0]))
        self.assertContains(page, "New CR (Class Representative)")
        field = page.context["adminform"].form.fields["replacement"]
        self.assertEqual(set(field.queryset.values_list("pk", flat=True)), {self.s[2].pk, self.s[3].pk, self.s[4].pk})
        response = self.client.post(self.user_url(self.s[0]), {"full_name": "Home 0"})  # is_active unticked
        self.assertEqual(response.status_code, 200)
        self.assertIn("replacement", response.context["adminform"].form.errors)
        self.assertTrue(User.objects.get(pk=self.s[0].pk).is_active)
        response = self.client.post(self.user_url(self.s[0]), {"full_name": "Home 0", "replacement": self.s[3].pk})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.get(pk=self.s[0].pk).is_active)
        self.assertEqual(current(self.cohort).cr_id, self.s[3].pk)

    def test_forged_replacement_is_refused(self):
        response = self.client.post(self.user_url(self.s[0]), {"full_name": "Home 0", "replacement": self.away.pk})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.get(pk=self.s[0].pk).is_active)

    def test_last_super_admin_message_still_shown(self):
        response = self.client.post(self.user_url(self.admin), {"full_name": "Head"})
        self.assertContains(response, services.LAST_SUPER_ADMIN)

    def test_profile_form_moves_with_a_replacement(self):
        profile = StudentProfile.objects.get(user=self.s[1])
        url = reverse("admin:accounts_studentprofile_change", args=[profile.pk])
        data = {"batch": self.a["other_batch"].pk, "semester": self.a["semester"].pk, "section": self.a["section"].pk}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("replacement", response.context["adminform"].form.errors)
        response = self.client.post(url, {**data, "replacement": self.s[4].pk})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(current(self.cohort).gr_id, self.s[4].pk)
        self.assertEqual(StudentProfileChange.objects.filter(profile=profile).count(), 1)

    def test_service_refusal_during_save_is_a_message_not_a_server_error(self):
        with mock.patch("accounts.admin.set_account_active", side_effect=ValidationError("Changed meanwhile.")):
            response = self.client.post(self.user_url(self.s[4]), {"full_name": "Home 4"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any("Changed meanwhile." in str(m) for m in get_messages(response.wsgi_request)))
        self.assertTrue(User.objects.get(pk=self.s[4].pk).is_active)

    def test_academic_admin_saves_use_the_locking_service(self):
        with mock.patch("academics.admin.set_entry_active", wraps=set_entry_active) as service:
            self.client.post(reverse("admin:academics_section_change", args=[self.a["other_section"].pk]),
                             {"name": "B"})  # is_active unticked: deactivate
            changelist = reverse("admin:academics_batch_changelist")
            batches = list(Batch.objects.order_by("name"))
            data = {"form-TOTAL_FORMS": str(len(batches)), "form-INITIAL_FORMS": str(len(batches)), "_save": "Save"}
            for i, batch in enumerate(batches):
                data[f"form-{i}-id"] = str(batch.pk)
                if batch.pk != self.a["other_batch"].pk:
                    data[f"form-{i}-is_active"] = "on"
            self.client.post(changelist, data)
        self.assertEqual(service.call_count, 2)
        self.assertFalse(Section.objects.get(pk=self.a["other_section"].pk).is_active)
        self.assertFalse(Batch.objects.get(pk=self.a["other_batch"].pk).is_active)


# ---------------------------------------------------------------------------------------------
# Portal pages
# ---------------------------------------------------------------------------------------------

class ManagementPageTests(RepresentationTestCase):
    def url(self, scope, name="", *args):
        return reverse(f"{scope}_representatives{name}", args=args)

    def test_access(self):
        self.assertEqual(self.client.get(self.url("advisor")).status_code, 302)  # anonymous
        self.client.force_login(self.s[0])
        self.assertEqual(self.client.get(self.url("advisor")).status_code, 403)
        self.assertEqual(self.client.get(self.url("super_admin")).status_code, 403)
        self.client.force_login(self.advisor)
        self.assertEqual(self.client.get(self.url("super_admin")).status_code, 403)
        self.assertEqual(self.client.get(self.url("advisor")).status_code, 200)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.url("super_admin")).status_code, 200)

    def test_advisor_sees_and_manages_only_assigned_cohorts(self):
        self.client.force_login(self.advisor)
        page = self.client.get(self.url("advisor"))
        self.assertEqual([c.cohort for c in page.context["cards"]], [self.cohort])
        self.assertNotContains(page, "Away Student")
        forged = self.client.post(self.url("advisor", "_appoint", self.other_cohort.key),
                                  {f"cohort-{self.other_cohort.key.replace('.', '-')}-appoint-cr": self.away.pk})
        self.assertEqual(forged.status_code, 404)
        self.assertEqual(self.client.post(self.url("advisor", "_appoint", "1.2"), {}).status_code, 404)

    def test_appoint_replace_and_swap_through_the_pages(self):
        self.client.force_login(self.advisor)
        anchor = "cohort-" + self.cohort.key.replace(".", "-")
        response = self.client.post(self.url("advisor", "_appoint", self.cohort.key),
                                    {f"{anchor}-appoint-cr": self.s[0].pk, f"{anchor}-appoint-gr": self.s[1].pk})
        self.assertRedirects(response, self.url("advisor") + "#" + anchor)
        period = current(self.cohort)
        response = self.client.post(self.url("advisor", "_replace", self.cohort.key, "gr"),
                                    {f"{anchor}-gr-person": self.s[2].pk, f"{anchor}-gr-expected_period": period.pk})
        self.assertEqual(response.status_code, 302)
        period2 = current(self.cohort)
        self.assertEqual(period2.gr_id, self.s[2].pk)
        stale = self.client.post(self.url("advisor", "_replace", self.cohort.key, "cr"),
                                 {f"{anchor}-cr-person": self.s[3].pk, f"{anchor}-cr-expected_period": period.pk})
        self.assertEqual(stale.status_code, 400)
        self.assertContains(stale, "changed by someone else", status_code=400)
        self.client.post(self.url("advisor", "_replace", self.cohort.key, "swap"), {f"{anchor}-swap-expected_period": period2.pk})
        self.assertEqual((current(self.cohort).cr_id, current(self.cohort).gr_id), (self.s[2].pk, self.s[0].pk))
        page = self.client.get(self.url("advisor"))
        self.assertContains(page, "History")
        self.assertContains(page, "CR and GR replaced")

    def test_validation_errors_are_shown_on_the_card(self):
        self.client.force_login(self.admin)
        anchor = "cohort-" + self.cohort.key.replace(".", "-")
        response = self.client.post(self.url("super_admin", "_appoint", self.cohort.key),
                                    {f"{anchor}-appoint-cr": self.s[0].pk, f"{anchor}-appoint-gr": self.s[0].pk})
        self.assertContains(response, "The CR and the GR must be different students.", status_code=400)
        forged = self.client.post(self.url("super_admin", "_appoint", self.cohort.key),
                                  {f"{anchor}-appoint-cr": self.away.pk, f"{anchor}-appoint-gr": self.s[1].pk})
        self.assertEqual(forged.status_code, 400)
        self.assertIsNone(current(self.cohort))

    def test_no_remove_route_and_post_only(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(self.url("super_admin", "_replace", self.cohort.key, "remove"), {}).status_code, 404)
        self.assertEqual(self.client.get(self.url("super_admin", "_appoint", self.cohort.key)).status_code, 405)

    def test_awaiting_state_and_too_few_students(self):
        lonely = (self.a["other_batch"], self.a["other_semester"], self.a["other_section"])
        student(lonely, "Only One")
        self.client.force_login(self.admin)
        page = self.client.get(self.url("super_admin"))
        self.assertContains(page, "Awaiting representatives")
        self.assertContains(page, "Not possible yet")

    def test_admin_filters_and_breach_panel(self):
        self.client.force_login(self.admin)
        self.appoint()
        page = self.client.get(self.url("super_admin"), {"status": "awaiting"})
        self.assertNotIn(self.cohort, [c.cohort for c in page.context["cards"]])
        User.objects.filter(pk=self.s[0].pk).update(is_active=False)
        page = self.client.get(self.url("super_admin"))
        self.assertContains(page, "1 cohort needs attention")

    def test_navigation_links_are_live(self):
        self.client.force_login(self.advisor)
        self.assertContains(self.client.get(reverse("advisor_home")), self.url("advisor"))
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("super_admin_home")), self.url("super_admin"))

    def test_advisor_candidates_exclude_holders_of_unassigned_cohorts(self):
        # A post in cohort B (not this advisor's) held by a student who is now in cohort A: an
        # inconsistent state (the breach panel shows it), set up by bypassing the services.
        away2 = student(self.other, "Away Two")
        rep.appoint_representatives(self.admin, self.other_cohort, cr=self.away, gr=away2)
        StudentProfile.objects.filter(user=self.away).update(batch=self.a["batch"])
        period = self.appoint()
        self.client.force_login(self.advisor)
        page = self.client.get(self.url("advisor"))
        [card] = page.context["cards"]
        self.assertEqual(card.cohort, self.cohort)
        self.assertNotIn(self.away.pk, [s.pk for s in card.candidates])
        self.assertIn(self.s[2].pk, [s.pk for s in card.candidates])
        for post in ("cr", "gr"):
            choices = [value for value, _ in card.forms[post].fields["person"].choices]
            self.assertNotIn(self.away.pk, [getattr(v, "value", v) for v in choices])
        self.assertNotContains(page, "Away Student")
        # The service, not the choice list, is the boundary: a forged submission is refused.
        anchor = "cohort-" + self.cohort.key.replace(".", "-")
        forged = self.client.post(self.url("advisor", "_replace", self.cohort.key, "cr"),
                                  {f"{anchor}-cr-person": self.away.pk, f"{anchor}-cr-expected_period": period.pk})
        self.assertEqual(forged.status_code, 400)
        self.assertEqual(current(self.cohort).pk, period.pk)
        with self.assertRaises(ValidationError):
            rep.replace_representatives(self.advisor, self.cohort, expected_period=period.pk, cr=self.away)
        self.assertEqual((current(self.cohort).cr_id, current(self.cohort).gr_id), (self.s[0].pk, self.s[1].pk))

    def test_page_queries_do_not_grow_with_cohorts(self):
        self.client.force_login(self.admin)
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as before:
            self.client.get(self.url("super_admin"))
        for name in ("C", "D", "E"):
            section = Section.objects.create(name=name)
            student((self.a["batch"], self.a["semester"], section), "More")
        with CaptureQueriesContext(connection) as after:
            self.client.get(self.url("super_admin"))
        self.assertEqual(len(after), len(before))
