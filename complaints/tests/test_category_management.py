"""Complaint category and subcategory management (Complaints Part 4 Stage 2, spec section 4)."""

from django.db import transaction
from django.test import TestCase

from complaints.models import ComplaintCategory, ComplaintSubcategory, ProtectedRecordError

from .helpers import make_academics, make_student, submit


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
