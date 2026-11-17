"""Complaint category and subcategory management (Complaints Part 4 Stage 2, spec section 4)."""

from unittest import mock

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from complaints import category_services as cs
from complaints import services
from complaints.forms import ComplaintSubmissionForm
from complaints.models import ComplaintCategory, ComplaintSubcategory, ProtectedRecordError

from .helpers import make_academics, make_advisor, make_student, make_super_admin, submit


def names(queryset):
    return list(queryset.order_by("position", "name", "pk").values_list("name", flat=True))


class ModelGuardTests(TestCase):
    """No hard deletion; a subcategory's parent is fixed; update() keeps working."""

    @classmethod
    def setUpTestData(cls):
        cls.unused = ComplaintCategory.objects.create(name="Unused", position=20)
        cls.other = ComplaintCategory.objects.create(name="Elsewhere", position=21)
        cls.sub = ComplaintSubcategory.objects.create(category=cls.unused, name="Unused sub")

    def assert_still_there(self):
        self.assertTrue(ComplaintCategory.objects.filter(pk=self.unused.pk).exists())
        self.assertTrue(ComplaintSubcategory.objects.filter(pk=self.sub.pk).exists())

    def test_instance_delete_is_refused_even_when_unreferenced(self):
        for record in (self.sub, self.unused):
            with self.subTest(record=str(record)), self.assertRaises(ProtectedRecordError), transaction.atomic():
                record.delete()
        self.assert_still_there()

    def test_queryset_delete_is_refused(self):
        for queryset in (
            ComplaintSubcategory.objects.filter(pk=self.sub.pk),
            ComplaintCategory.objects.filter(pk=self.unused.pk),
            ComplaintCategory.objects.all(),
            self.unused.subcategories.all(),
        ):
            with self.subTest(model=queryset.model.__name__), self.assertRaises(ProtectedRecordError), transaction.atomic():
                queryset.delete()
        self.assert_still_there()

    def test_update_keeps_working(self):
        self.assertEqual(ComplaintCategory.objects.filter(pk=self.unused.pk).update(is_active=False), 1)
        self.assertEqual(ComplaintSubcategory.objects.filter(pk=self.sub.pk).update(position=3), 1)
        self.unused.refresh_from_db()
        self.sub.refresh_from_db()
        self.assertEqual((self.unused.is_active, self.sub.position), (False, 3))
        self.assertEqual(list(ComplaintCategory.objects.active().filter(pk=self.unused.pk)), [])

    def test_subcategory_parent_cannot_change(self):
        loaded = ComplaintSubcategory.objects.get(pk=self.sub.pk)
        loaded.category = self.other
        with self.assertRaises(ProtectedRecordError):
            loaded.save()
        forged = ComplaintSubcategory(pk=self.sub.pk, category=self.other, name=self.sub.name, created_at=self.sub.created_at)
        with self.assertRaises(ProtectedRecordError):
            forged.save()
        with self.assertRaises(ProtectedRecordError):
            ComplaintSubcategory(pk=self.sub.pk, category=self.other).save(update_fields=["category"])
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.category, self.unused)

    def test_other_subcategory_saves_still_work(self):
        loaded = ComplaintSubcategory.objects.get(pk=self.sub.pk)
        loaded.name = "Renamed"
        loaded.save()
        loaded.refresh_from_db()
        self.assertEqual((loaded.name, loaded.category), ("Renamed", self.unused))

    def test_referenced_category_is_still_protected_by_its_foreign_keys(self):
        student = make_student(academics=make_academics())
        complaint = submit(student, self.unused, subcategory=self.sub)
        for record in (self.sub, self.unused):
            with self.assertRaises(ProtectedRecordError), transaction.atomic():
                record.delete()
        complaint.refresh_from_db()
        self.assertEqual((complaint.category, complaint.subcategory), (self.unused, self.sub))


# ---------- Service layer ----------

class ServiceTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = make_super_admin()
        # A known baseline, whether or not the seeded rows survived in a kept test database
        # (a TransactionTestCase flush removes them; categories cannot be deleted to reset).
        for position, name in enumerate(["Academic", "Non-academic", "Personal/Wellbeing", "Other"], start=1):
            ComplaintCategory.objects.get_or_create(name=name, defaults={"position": position})
        cls.base = list(ComplaintCategory.objects.order_by("position", "name"))

    def all_names(self):
        return names(ComplaintCategory.objects.all())


class ServicePermissionTests(ServiceTestCase):
    def test_every_operation_requires_an_active_super_admin(self):
        category = cs.create_category(self.admin, "Facilities")
        sub = cs.create_subcategory(self.admin, category, "Lighting")
        inactive_admin = make_super_admin("old@uol.edu.pk")
        inactive_admin.is_active = False
        inactive_admin.save()
        actors = [None, make_student(academics=make_academics()), make_advisor(), inactive_admin]
        operations = [
            lambda a: cs.create_category(a, "X"), lambda a: cs.rename_category(a, category, "Y"),
            lambda a: cs.set_category_active(a, category, False), lambda a: cs.move_category(a, category, cs.UP),
            lambda a: cs.create_subcategory(a, category, "X"), lambda a: cs.rename_subcategory(a, sub, "Y"),
            lambda a: cs.set_subcategory_active(a, sub, False), lambda a: cs.move_subcategory(a, sub, cs.UP),
        ]
        for actor in actors:
            for index, operation in enumerate(operations):
                with self.subTest(actor=getattr(actor, "email", None), operation=index), self.assertRaises(PermissionDenied):
                    operation(actor)
        category.refresh_from_db()
        sub.refresh_from_db()
        self.assertEqual((category.name, category.is_active, sub.name, sub.is_active), ("Facilities", True, "Lighting", True))


class CreateRenameTests(ServiceTestCase):
    def test_create_appends_and_normalises(self):
        category = cs.create_category(self.admin, "   Campus \t  facilities  ")
        self.assertEqual(category.name, "Campus facilities")
        self.assertEqual(self.all_names()[-1], "Campus facilities")
        self.assertTrue(category.is_active)
        first = cs.create_subcategory(self.admin, category, " Lighting ")
        second = cs.create_subcategory(self.admin, category, "Heating")
        self.assertEqual(names(category.subcategories.all()), ["Lighting", "Heating"])
        self.assertLess(first.position, second.position)

    def test_invalid_names(self):
        for bad in ("", "   ", "\t\n", "x" * 81):
            with self.subTest(name=bad[:10]), self.assertRaises(ValidationError) as caught:
                cs.create_category(self.admin, bad)
            self.assertIn("name", caught.exception.message_dict)
        self.assertEqual(cs.create_category(self.admin, "y" * 80).name, "y" * 80)

    def test_duplicates_ignore_case_accents_and_include_inactive(self):
        cs.create_category(self.admin, "Facilities")
        ComplaintCategory.objects.filter(name="Other").update(is_active=False)
        for duplicate in ("facilities", "FACILITIES", "  Facilities ", "Fácilities", "other", "Acádemic"):
            with self.subTest(name=duplicate), self.assertRaises(ValidationError) as caught:
                cs.create_category(self.admin, duplicate)
            self.assertIn("already exists", caught.exception.message_dict["name"][0])

    def test_rename_checks_duplicates_but_allows_its_own_name(self):
        category = cs.create_category(self.admin, "Facilities")
        with self.assertRaises(ValidationError):
            cs.rename_category(self.admin, category, "ACADEMIC")
        self.assertEqual(cs.rename_category(self.admin, category, "FACILITIES").name, "FACILITIES")
        self.assertEqual(cs.rename_category(self.admin, category, " Campus  facilities ").name, "Campus facilities")

    def test_subcategory_names_are_unique_within_their_parent_only(self):
        first = cs.create_category(self.admin, "Facilities")
        second = cs.create_category(self.admin, "Transport")
        cs.create_subcategory(self.admin, first, "Other")
        self.assertEqual(cs.create_subcategory(self.admin, second, "Other").name, "Other")
        hidden = cs.create_subcategory(self.admin, first, "Parking")
        cs.set_subcategory_active(self.admin, hidden, False)
        for duplicate in ("other", "PARKING", "Óther"):
            with self.subTest(name=duplicate), self.assertRaises(ValidationError):
                cs.create_subcategory(self.admin, first, duplicate)
        lighting = cs.create_subcategory(self.admin, first, "Lighting")
        with self.assertRaises(ValidationError):
            cs.rename_subcategory(self.admin, lighting, "parking")

    def test_database_integrity_error_becomes_a_field_error(self):
        # A duplicate that only the database detects (for example, a concurrent create).
        with mock.patch.object(cs, "_refuse_duplicate"), mock.patch.object(
            ComplaintCategory, "save", side_effect=IntegrityError("duplicate")
        ):
            with self.assertRaises(ValidationError) as caught:
                cs.create_category(self.admin, "Facilities")
        self.assertIn("already exists", caught.exception.message_dict["name"][0])
        self.assertFalse(ComplaintCategory.objects.filter(name="Facilities").exists())

    def test_create_subcategory_under_an_inactive_category(self):
        category = cs.create_category(self.admin, "Facilities")
        cs.set_category_active(self.admin, category, False)
        sub = cs.create_subcategory(self.admin, category, "Lighting")
        self.assertTrue(sub.is_active)
        self.assertEqual(sub.category, category)


class OrderingTests(ServiceTestCase):
    def test_up_and_down(self):
        start = self.all_names()
        other = ComplaintCategory.objects.get(name=start[-1])
        cs.move_category(self.admin, other, cs.UP)
        self.assertEqual(self.all_names()[-2:], [start[-1], start[-2]])
        cs.move_category(self.admin, other, cs.DOWN)
        self.assertEqual(self.all_names(), start)

    def test_boundaries_are_no_ops(self):
        start = self.all_names()
        cs.move_category(self.admin, ComplaintCategory.objects.get(name=start[0]), cs.UP)
        cs.move_category(self.admin, ComplaintCategory.objects.get(name=start[-1]), cs.DOWN)
        self.assertEqual(self.all_names(), start)

    def test_tied_positions_are_renumbered_so_moves_work(self):
        category = cs.create_category(self.admin, "Facilities")
        for name in ("Charlie", "Alpha", "Bravo"):
            ComplaintSubcategory.objects.create(category=category, name=name, position=0)  # all tied
        self.assertEqual(names(category.subcategories.all()), ["Alpha", "Bravo", "Charlie"])
        cs.move_subcategory(self.admin, category.subcategories.get(name="Charlie"), cs.UP)
        self.assertEqual(names(category.subcategories.all()), ["Alpha", "Charlie", "Bravo"])
        self.assertEqual(list(category.subcategories.order_by("position").values_list("position", flat=True)), [1, 2, 3])

    def test_subcategory_moves_stay_within_their_parent(self):
        first = cs.create_category(self.admin, "Facilities")
        second = cs.create_category(self.admin, "Transport")
        a = cs.create_subcategory(self.admin, first, "A")
        cs.create_subcategory(self.admin, first, "B")
        cs.create_subcategory(self.admin, second, "Z")
        cs.move_subcategory(self.admin, a, cs.DOWN)
        self.assertEqual(names(first.subcategories.all()), ["B", "A"])
        self.assertEqual(names(second.subcategories.all()), ["Z"])

    def test_invalid_direction(self):
        with self.assertRaises(ValidationError):
            cs.move_category(self.admin, self.base[0], "sideways")

    def test_order_shows_in_the_student_form(self):
        last = ComplaintCategory.objects.get(name=self.all_names()[-1])
        for _ in range(len(self.all_names())):
            cs.move_category(self.admin, last, cs.UP)
        labels = [label for _, label in ComplaintSubmissionForm().fields["category"].choices][1:]
        self.assertEqual(labels[0], last.name)


class ActivationTests(ServiceTestCase):
    def setUp(self):
        self.category = cs.create_category(self.admin, "Facilities")
        self.sub = cs.create_subcategory(self.admin, self.category, "Lighting")
        self.student = make_student(academics=make_academics())

    def offered(self):
        form = ComplaintSubmissionForm()
        categories = [label for _, label in form.fields["category"].choices][1:]
        subcategories = [label for _, options in form.fields["subcategory"].choices[1:] for _, label in options]
        return categories, subcategories

    def test_deactivating_a_category_does_not_change_child_flags(self):
        cs.set_category_active(self.admin, self.category, False)
        self.sub.refresh_from_db()
        self.assertTrue(self.sub.is_active)

    def test_active_subcategory_under_inactive_parent_is_unavailable(self):
        cs.set_category_active(self.admin, self.category, False)
        categories, subcategories = self.offered()
        self.assertNotIn("Facilities", categories)
        self.assertNotIn("Lighting", subcategories)
        self.category.refresh_from_db()
        with self.assertRaises(ValidationError) as caught:
            submit(self.student, self.category, subcategory=self.sub)
        self.assertIn("category", caught.exception.message_dict)

    def test_reactivation_restores_availability(self):
        cs.set_category_active(self.admin, self.category, False)
        cs.set_category_active(self.admin, self.category, True)
        categories, subcategories = self.offered()
        self.assertIn("Facilities", categories)
        self.assertIn("Lighting", subcategories)
        self.category.refresh_from_db()
        self.assertEqual(submit(self.student, self.category, subcategory=self.sub).subcategory, self.sub)

    def test_inactive_subcategory_is_unavailable_under_an_active_parent(self):
        cs.set_subcategory_active(self.admin, self.sub, False)
        self.assertNotIn("Lighting", self.offered()[1])
        with self.assertRaises(ValidationError):
            submit(self.student, self.category, subcategory=self.sub)

    def test_last_active_category_cannot_be_deactivated(self):
        ComplaintCategory.objects.exclude(pk=self.category.pk).update(is_active=False)
        with self.assertRaises(ValidationError) as caught:
            cs.set_category_active(self.admin, self.category, False)
        self.assertEqual(caught.exception.code, "last_active_category")
        self.category.refresh_from_db()
        self.assertTrue(self.category.is_active)
        cs.set_category_active(self.admin, self.base[0], True)
        self.assertFalse(cs.set_category_active(self.admin, self.category, False).is_active)

    def test_repeating_the_current_state_is_harmless(self):
        cs.set_category_active(self.admin, self.category, True)
        cs.set_subcategory_active(self.admin, self.sub, True)
        self.assertTrue(ComplaintCategory.objects.get(pk=self.category.pk).is_active)


class HistoricalIntegrityServiceTests(ServiceTestCase):
    def test_rename_and_deactivation_never_touch_complaints(self):
        category = cs.create_category(self.admin, "Facilities")
        sub = cs.create_subcategory(self.admin, category, "Lighting")
        student = make_student(academics=make_academics())
        complaint = submit(student, category, subcategory=sub)
        events = list(complaint.events.values_list("pk", "kind", "message"))
        cs.rename_category(self.admin, category, "Campus facilities")
        cs.rename_subcategory(self.admin, sub, "Lights")
        cs.set_subcategory_active(self.admin, sub, False)
        cs.set_category_active(self.admin, category, False)
        complaint.refresh_from_db()
        self.assertEqual((complaint.category_id, complaint.subcategory_id), (category.pk, sub.pk))
        self.assertEqual((complaint.category.name, complaint.subcategory.name), ("Campus facilities", "Lights"))
        self.assertEqual(list(complaint.events.values_list("pk", "kind", "message")), events)
        self.assertEqual(complaint.status, services.Status.RECEIVED)
