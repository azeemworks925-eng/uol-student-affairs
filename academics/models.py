"""
Database-managed academic structure (DEC-020).

Entries are deactivated rather than deleted, so students and historical records that
refer to them are preserved (DEC-210). Inactive entries are hidden from new choices.
"""

from django.core.validators import MinValueValidator
from django.db import models


class ActiveQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class Batch(models.Model):
    name = models.CharField(max_length=50, unique=True, help_text="For example: Fall 2024.")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ActiveQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "batches"

    def __str__(self):
        return self.name


class Semester(models.Model):
    number = models.PositiveSmallIntegerField(unique=True, validators=[MinValueValidator(1)])
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ActiveQuerySet.as_manager()

    class Meta:
        ordering = ["number"]

    def __str__(self):
        return f"Semester {self.number}"


class Section(models.Model):
    name = models.CharField(max_length=20, unique=True, help_text="For example: A.")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ActiveQuerySet.as_manager()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"Section {self.name}"
