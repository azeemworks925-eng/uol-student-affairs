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

from django.db import IntegrityError, transaction

from .models import AcademicTerm


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
    term.is_current = True
    if previous is not None and previous.pk != term.pk:
        previous.is_current = None
    return previous, changed


def clear_current_term(expected=ANY):
    """Leave no term current. Returns (previous current term or None, changed).

    `expected` (a term, or None) guards against stale screens: if a different term is current
    when the locks are held, nothing changes and CurrentTermChanged is raised."""
    expected_pk = expected if expected is ANY else (expected.pk if expected is not None else None)
    previous, changed = _run(None, expected_pk)
    if previous is not None:
        previous.is_current = None
    return previous, changed
