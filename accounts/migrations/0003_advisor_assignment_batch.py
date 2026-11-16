"""
Scope Batch Advisor assignments to the exact batch + semester + section cohort
(DEC-205).

Existing assignments cannot be given a batch automatically: guessing would grant an
advisor access to the wrong students. If any exist, the migration stops as its first
step, before any schema change and without changing or deleting data. It lists the
assignments so they can be recorded, removed, and re-created with a batch after migrating.
Checking first matters because MySQL cannot roll back schema changes.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class UnscopedAssignmentsExist(Exception):
    pass


def refuse_if_assignments_exist(apps, schema_editor):
    AdvisorAssignment = apps.get_model("accounts", "AdvisorAssignment")
    existing = list(
        AdvisorAssignment.objects.using(schema_editor.connection.alias)
        .select_related("advisor", "semester", "section")
        .order_by("pk")
    )
    if existing:
        listing = "; ".join(
            f"#{a.pk} {a.advisor.email}: semester {a.semester.number}, section {a.section.name}"
            for a in existing
        )
        raise UnscopedAssignmentsExist(
            f"{len(existing)} advisor assignment(s) have no batch, and a batch cannot be inferred "
            f"safely: {listing}. Nothing has been changed. Record these assignments, remove them, "
            "run migrate again, then re-create each one with its batch."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("academics", "0001_initial"),
        ("accounts", "0002_account_foundation"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(refuse_if_assignments_exist, migrations.RunPython.noop),
        migrations.AddField(
            model_name="advisorassignment",
            name="batch",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="advisor_assignments",
                to="academics.batch",
            ),
        ),
        # Add the new constraint before dropping the old one: on MySQL the old composite
        # index may be the one backing the advisor foreign key.
        migrations.AddConstraint(
            model_name="advisorassignment",
            constraint=models.UniqueConstraint(
                fields=("advisor", "batch", "semester", "section"), name="unique_advisor_cohort_assignment"
            ),
        ),
        migrations.RemoveConstraint(
            model_name="advisorassignment",
            name="unique_advisor_assignment",
        ),
        migrations.AlterModelOptions(
            name="advisorassignment",
            options={"ordering": ["batch__name", "semester__number", "section__name"]},
        ),
    ]
