"""
Current academic term selection (Complaints Part 4 Stage 4a; DEC-314).

The current term is the reporting window for complaint analytics. These two functions are the
only way to change it.

Concurrency: each change runs in one transaction that first locks every term row with
SELECT ... FOR UPDATE in primary-key order. Two Super Admins changing the current term at the
same time are therefore serialised (the second waits for the first to commit), and the fixed
lock order means they cannot deadlock each other. The current term is read again *after* the
locks are held, so the second change sees the first one's result. New terms are always created
non-current (AcademicTerm.save() refuses anything else), so a term inserted after the locks are
taken cannot become a second current term.

The database is the final safeguard: a unique index on the nullable flag allows only one TRUE.
If that ever fires (for example after raw SQL), the transaction has already rolled back when
the IntegrityError is caught here, and CurrentTermConflict is raised for the caller to report.
"""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from .models import AcademicTerm, Batch, Section, Semester


class CurrentTermConflict(Exception):
    """The current term changed at the same time and the database refused the change."""


def current_term():
    """The current term, or None when none is set."""
    return AcademicTerm.objects.filter(is_current=True).first()


CONFLICT_MESSAGE = "The current term changed at the same time. Please try again."


class CurrentTermChanged(Exception):
    """clear_current_term(expected=...) found a different current term, so nothing changed."""


ANY = object()


@transaction.atomic
def _change_current(target_pk, expected_pk=ANY):
    """Make the term with `target_pk` current, or leave no term current when it is None.
    With `expected_pk`, change nothing unless that term (or None) is current under the locks.
    Returns (previous current term or None, changed)."""
    terms = {term.pk: term for term in AcademicTerm.objects.select_for_update().order_by("pk")}
    if target_pk is not None and target_pk not in terms:
        raise AcademicTerm.DoesNotExist("The selected academic term no longer exists.")
    previous = next((term for term in terms.values() if term.is_current), None)  # read under the locks
    if expected_pk is not ANY and (previous.pk if previous else None) != expected_pk:
        raise CurrentTermChanged(previous)
    if (previous.pk if previous else None) == target_pk:
        return previous, False
    if previous is not None:
        # Cleared first: MySQL checks the unique index row by row.
        AcademicTerm.objects.filter(pk=previous.pk)._write_current_flag(None)
    if target_pk is not None:
        AcademicTerm.objects.filter(pk=target_pk)._write_current_flag(True)
    return previous, True


def _run(target_pk, expected_pk=ANY):
    try:
        return _change_current(target_pk, expected_pk)
    except IntegrityError as exc:  # caught after _change_current's transaction rolled back
        raise CurrentTermConflict(CONFLICT_MESSAGE) from exc


def set_current_term(term):
    """Make `term` the only current term. Returns (previous current term or None, changed);
    changed is False when it was already current. Raises CurrentTermConflict if the database
    refuses the change, and AcademicTerm.DoesNotExist for an unsaved or missing term."""
    if term is None or term.pk is None:
        raise AcademicTerm.DoesNotExist("A saved academic term is required.")
    previous, changed = _run(term.pk)
    term._mark_current_flag(True)
    if previous is not None and previous.pk != term.pk:
        previous._mark_current_flag(None)
    return previous, changed


def clear_current_term(expected=ANY):
    """Leave no term current. Returns (previous current term or None, changed).

    `expected` (a term, or None) guards against stale screens: if a different term is current
    when the locks are held, nothing changes and CurrentTermChanged is raised."""
    expected_pk = expected if expected is ANY else (expected.pk if expected is not None else None)
    previous, changed = _run(None, expected_pk)
    if previous is not None:
        previous._mark_current_flag(None)
    return previous, changed


# ---------------------------------------------------------------------------------------------
# Academic entry active state (Collective Issues CI-1; COLLECTIVE_ISSUES_SPEC.md section 5.7)
# ---------------------------------------------------------------------------------------------

@transaction.atomic
def set_entry_active(entry, active, *, actor=None):
    """Activate or deactivate a Batch, Semester or Section in one transaction.

    A cohort's eligibility depends on all three entries, so this takes the cohort locks used by
    every representation-related transaction: first **all** Section rows in ascending primary
    key (the set of sections used with a batch or semester isn't stored, and a list-editable
    admin save changes several entries in display order), then the Batch or Semester row being
    changed. Representation services never lock Batch or Semester rows, so there is no reverse
    order. Deactivation closes nothing: the cohort simply becomes inactive (DEC-323, DEC-324).
    """
    if not isinstance(entry, (Batch, Semester, Section)):
        raise TypeError("set_entry_active takes a Batch, Semester or Section.")
    list(Section.objects.select_for_update().order_by("pk"))
    model = type(entry)
    if model is not Section:
        model.objects.select_for_update().filter(pk=entry.pk).get()
    entry.is_active = active
    model.objects.filter(pk=entry.pk).update(is_active=active)
    return entry


# ---------------------------------------------------------------------------------------------
# Portal management of entries and terms (DEC-330). Nothing here deletes (DEC-210).
# ---------------------------------------------------------------------------------------------

ENTRY_FIELDS = {Batch: "name", Semester: "number", Section: "name"}
ENTRY_EXISTS = "An entry with this value already exists."
TERM_EXISTS = "A term with this name already exists."


def _entry_value(value):
    return " ".join(value.split()) if isinstance(value, str) else value


@transaction.atomic
def create_entry(model, value):
    """Add a Batch, Semester or Section. It starts active."""
    field = ENTRY_FIELDS[model]
    entry = model(**{field: _entry_value(value)})
    entry.full_clean()
    try:
        with transaction.atomic():
            entry.save()
    except IntegrityError as error:
        raise ValidationError({field: ENTRY_EXISTS}) from error
    return entry


@transaction.atomic
def update_entry(entry, value):
    """Rename a Batch or Section, or renumber a Semester, under the same locks as
    set_entry_active: every Section row first, then the Batch or Semester row."""
    model = type(entry)
    field = ENTRY_FIELDS[model]
    list(Section.objects.select_for_update().order_by("pk"))
    fresh = model.objects.select_for_update().get(pk=entry.pk)
    setattr(fresh, field, _entry_value(value))
    fresh.full_clean()
    try:
        with transaction.atomic():
            fresh.save(update_fields=[field])
    except IntegrityError as error:
        raise ValidationError({field: ENTRY_EXISTS}) from error
    return fresh


@transaction.atomic
def create_term(*, name, start_date, end_date):
    """Add an academic term. A new term is never current."""
    term = AcademicTerm(name=name, start_date=start_date, end_date=end_date)
    term.full_clean(exclude=["is_current"])
    try:
        with transaction.atomic():
            term.save()
    except IntegrityError as error:
        raise ValidationError({"name": TERM_EXISTS}) from error
    return term


@transaction.atomic
def update_term(term, *, name, start_date, end_date):
    """Change a term's name or dates. Its current flag is never written here."""
    fresh = AcademicTerm.objects.select_for_update().get(pk=term.pk)
    fresh.name, fresh.start_date, fresh.end_date = name, start_date, end_date
    fresh.full_clean(exclude=["is_current"])
    try:
        with transaction.atomic():
            fresh.save()
    except IntegrityError as error:
        raise ValidationError({"name": TERM_EXISTS}) from error
    return fresh
