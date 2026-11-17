"""
Database-managed academic structure (DEC-020).

Entries are deactivated rather than deleted, so students and historical records that
refer to them are preserved (DEC-210). Inactive entries are hidden from new choices.
"""

import unicodedata
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q


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


# ---------------------------------------------------------------------------------------------
# Academic terms (Complaints Part 4 Stage 4a; COMPLAINTS_PART4_SPEC.md section 6.1, DEC-314)
# ---------------------------------------------------------------------------------------------

# The reporting window is defined in the university's local time, whatever the server's zone.
REPORTING_TIME_ZONE = ZoneInfo("Asia/Karachi")
EARLIEST_TERM_DATE, LATEST_TERM_DATE = date(1900, 1, 1), date(9998, 12, 31)
CURRENT_FLAG_MESSAGE = "The current term can only be changed with set_current_term() or clear_current_term()."


def term_name_key(name):
    """Comparison key ignoring case and accents, like MySQL's utf8mb4_0900_ai_ci, so duplicate
    names are refused the same way on MySQL and SQLite (as complaint category names are)."""
    decomposed = unicodedata.normalize("NFKD", name)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()


class ProtectedTermError(Exception):
    """Raised when code tries to delete a term or to change the current term outside the services."""


def term_window(start_date, end_date):
    """The reporting window for a term as timezone-aware datetimes: (inclusive start, exclusive end).

    Start: `start_date` at 00:00 Asia/Karachi. End: the day after `end_date` at 00:00 Asia/Karachi,
    so the whole of the end date is included. Query with `created_at >= start, created_at < end`.
    This is the only place the boundary is calculated.
    """
    start = datetime.combine(start_date, time.min, tzinfo=REPORTING_TIME_ZONE)
    end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=REPORTING_TIME_ZONE)
    return start, end


class TermQuerySet(models.QuerySet):
    """Terms are never deleted, and the current flag is written only by academics.services
    (which locks the term rows first). Bulk paths that would bypass that are refused; other
    fields update normally. Raw SQL is outside what the ORM can protect; the database
    constraints still allow at most one current term."""

    def delete(self):
        raise ProtectedTermError("Academic terms cannot be deleted.")

    delete.alters_data = True
    delete.queryset_only = True

    def update(self, **kwargs):
        if "is_current" in kwargs:
            raise ProtectedTermError(CURRENT_FLAG_MESSAGE)
        return super().update(**kwargs)

    update.alters_data = True

    def bulk_update(self, objs, fields, batch_size=None):
        if "is_current" in fields:
            raise ProtectedTermError(CURRENT_FLAG_MESSAGE)
        return super().bulk_update(objs, fields, batch_size=batch_size)

    bulk_update.alters_data = True

    def bulk_create(self, objs, batch_size=None, ignore_conflicts=False, update_conflicts=False,
                    update_fields=None, unique_fields=None):
        objs = list(objs)
        if any(obj.is_current is not None for obj in objs) or (update_conflicts and "is_current" in (update_fields or ())):
            raise ProtectedTermError(CURRENT_FLAG_MESSAGE)
        return super().bulk_create(
            objs, batch_size=batch_size, ignore_conflicts=ignore_conflicts, update_conflicts=update_conflicts,
            update_fields=update_fields, unique_fields=unique_fields,
        )

    bulk_create.alters_data = True

    def _write_current_flag(self, value):
        """For academics.services only, while it holds the locks on every term row."""
        return super().update(is_current=value)


class AcademicTerm(models.Model):
    """A named, dated academic term: the reporting window for complaint analytics (DEC-314).

    At most one term is current. The current term has `is_current=True`; every other term has
    NULL, never False. A plain unique index allows many NULLs but only one TRUE on both MySQL
    and SQLite, and a check constraint refuses False, so the database itself guarantees at most
    one current term (MySQL ignores conditional unique constraints, so none is used). Terms may
    overlap: only the current term is reported.
    """

    name = models.CharField(max_length=50, unique=True, help_text="For example: Fall 2026.")
    start_date = models.DateField(help_text="The first day of the term.")
    end_date = models.DateField(help_text="The last day of the term (included).")
    is_current = models.BooleanField(null=True, default=None, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TermQuerySet.as_manager()

    class Meta:
        ordering = ["-start_date", "name"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__gte=F("start_date")), name="academic_term_dates_valid"
            ),
            models.CheckConstraint(
                # An explicit comparison: on SQLite, Q(is_current=True) compiles to a bare
                # truthiness test that would accept 2 alongside 1 (two "current" terms).
                condition=Q(is_current__isnull=True) | Q(is_current__in=[True]), name="academic_term_current_true_or_null"
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def dates_label(self):
        """The exact dates, for example "1 Sep 2026 – 15 Jan 2027"."""
        return f"{self.start_date.day} {self.start_date:%b %Y} – {self.end_date.day} {self.end_date:%b %Y}"

    def window(self):
        return term_window(self.start_date, self.end_date)

    def clean(self):
        super().clean()
        if self.name:
            self.name = " ".join(self.name.split())
            key = term_name_key(self.name)
            for pk, existing in AcademicTerm.objects.exclude(pk=self.pk).values_list("pk", "name"):
                if term_name_key(existing) == key:
                    raise ValidationError({"name": f"A term named “{existing}” already exists."})
        # The window's boundaries must stay representable in UTC (term_window adds a day and
        # converts from UTC+05:00), so dates at the very ends of the calendar are refused.
        for field in ("start_date", "end_date"):
            value = getattr(self, field)
            if value and not (EARLIEST_TERM_DATE <= value <= LATEST_TERM_DATE):
                raise ValidationError({field: "Enter a date between 1 Jan 1900 and 31 Dec 9998."})
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "The end date cannot be before the start date."})

    def save(self, *args, **kwargs):
        # The current flag is changed only by academics.services. Compare with the stored row,
        # not in-memory state.
        update_fields = kwargs.get("update_fields")
        writes_flag = update_fields is None or "is_current" in update_fields
        if writes_flag:
            # An instance built with an existing pk would overwrite that row, so it is compared too.
            if self.pk is None or kwargs.get("force_insert"):
                stored = None
            else:
                stored = AcademicTerm._base_manager.filter(pk=self.pk).values_list("is_current", flat=True).first()
            if self.is_current != stored:
                raise ProtectedTermError(CURRENT_FLAG_MESSAGE)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ProtectedTermError("Academic terms cannot be deleted.")
