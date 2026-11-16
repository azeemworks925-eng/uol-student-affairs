"""Migration safety for scoping advisor assignments to batch + semester + section."""

import importlib

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

migration_0003 = importlib.import_module("accounts.migrations.0003_advisor_assignment_batch")

TABLE = "accounts_advisorassignment"
BEFORE = [("accounts", "0002_account_foundation"), ("academics", "0001_initial")]
AFTER = [("accounts", "0003_advisor_assignment_batch")]


class AssignmentBatchMigrationTests(TransactionTestCase):
    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def columns(self):
        with connection.cursor() as cursor:
            return {c.name: c for c in connection.introspection.get_table_description(cursor, TABLE)}

    def constraint_names(self):
        with connection.cursor() as cursor:
            return set(connection.introspection.get_constraints(cursor, TABLE))

    def row_count(self):
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) FROM {TABLE}")
            return cursor.fetchone()[0]

    def test_migrates_to_a_required_batch_with_cohort_uniqueness(self):
        self.migrate(BEFORE)
        self.assertNotIn("batch_id", self.columns())

        self.migrate(AFTER)

        self.assertFalse(self.columns()["batch_id"].null_ok)
        names = self.constraint_names()
        self.assertIn("unique_advisor_cohort_assignment", names)
        self.assertNotIn("unique_advisor_assignment", names)

    def test_existing_assignments_stop_the_migration_before_any_change(self):
        old_apps = self.migrate(BEFORE)
        User = old_apps.get_model("accounts", "User")
        advisor = User.objects.create(email="advisor@uol.edu.pk", role="batch_advisor")
        semester = old_apps.get_model("academics", "Semester").objects.create(number=4)
        section = old_apps.get_model("academics", "Section").objects.create(name="A")
        old_apps.get_model("accounts", "AdvisorAssignment").objects.create(
            advisor=advisor, semester=semester, section=section
        )

        with self.assertRaises(migration_0003.UnscopedAssignmentsExist) as ctx:
            self.migrate(AFTER)

        self.assertIn("advisor@uol.edu.pk: semester 4, section A", str(ctx.exception))
        self.assertNotIn("batch_id", self.columns())  # No schema change, even on MySQL.
        self.assertIn("unique_advisor_assignment", self.constraint_names())
        self.assertEqual(self.row_count(), 1)  # Data preserved.

        # Follow the documented recovery path: remove, migrate, then re-create with a batch.
        with connection.cursor() as cursor:
            cursor.execute(f"DELETE FROM {TABLE}")
        self.migrate(AFTER)
        self.assertFalse(self.columns()["batch_id"].null_ok)
