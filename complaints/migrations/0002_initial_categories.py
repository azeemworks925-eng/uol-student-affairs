"""The initial main categories (DEC-220). They are ordinary rows: the Super Admin can rename,
reorder, deactivate or add to them later; nothing in the code depends on these names."""

from django.db import migrations

INITIAL_CATEGORIES = ["Academic", "Non-academic", "Personal/Wellbeing", "Other"]


def add_initial_categories(apps, schema_editor):
    Category = apps.get_model("complaints", "ComplaintCategory")
    for position, name in enumerate(INITIAL_CATEGORIES, start=1):
        Category.objects.get_or_create(name=name, defaults={"position": position})


class Migration(migrations.Migration):
    dependencies = [("complaints", "0001_initial")]

    # Reversing leaves the rows in place: categories may already be referenced by complaints.
    operations = [migrations.RunPython(add_initial_categories, migrations.RunPython.noop)]
