"""
Cohort representation: each cohort's CR and GR (Collective Issues CI-1).

Specification: docs/technical/COLLECTIVE_ISSUES_SPEC.md sections 5.1 to 5.7. Decisions: DEC-016
(exactly one CR and one GR), DEC-205 (exact cohort), DEC-240 (one post per student), DEC-245 (who
manages them), DEC-323 (no vacancy once represented; "Awaiting representatives"; closure).

Every operation here runs inside one transaction and takes locks in the global order of
spec 5.7, which rules out deadlocks:

1. the `Section` rows of the cohorts involved, ascending primary key (academic active-state
   changes, in academics.services, take all of them);
2. (academic active-state changes only) the Batch or Semester row being changed;
3. the cohorts' current `CohortRepresentation` rows, ascending primary key;
4. the `User` and `StudentProfile` rows involved, ascending primary key.

The Section row is the cohort lock: it always exists, even for a cohort that has no
representation period yet, so first appointments and membership changes are serialised too.
Representation services never lock a Batch or Semester row; they read the batch, semester and
section active states only after taking the Section lock. Django's MySQL connection runs READ
COMMITTED, so those reads see the latest committed state.

The database guarantees the per-row rules (both posts filled, different people, one current
period per cohort, one current CR or GR post per student). These services guarantee the
cross-row rule: a represented, eligible cohort never has a vacant post.
"""

from dataclasses import dataclass

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from academics.models import Batch, Section, Semester

from .models import AdvisorAssignment, CohortRepresentation, StudentProfile, User

Period = CohortRepresentation
Reason = CohortRepresentation.EndReason
POST_LABELS = {"cr": "CR", "gr": "GR"}
POST_NAMES = {"cr": "Class Representative", "gr": "Girls Representative"}  # DEC-016

INACTIVE_COHORT = "This cohort is inactive, so representatives can't be appointed or replaced in it."
CONCURRENT_CHANGE = "The representatives changed at the same time. Please check the cohort and try again."
STALE_PERIOD = "These representatives were changed by someone else. The cohort now shows the current CR and GR."
ALREADY_REPRESENTED = "This cohort's CR and GR were just appointed by someone else."
DETAILS_CHANGED = "This student's details changed at the same time. Please try again."


@dataclass(frozen=True)
class Cohort:
    """An exact batch + semester + section cohort (DEC-205), by primary keys."""

    batch_id: int
    semester_id: int
    section_id: int

    @classmethod
    def of(cls, obj):
        return cls(obj.batch_id, obj.semester_id, obj.section_id)

    @classmethod
    def parse(cls, value):
        """From the "batch.semester.section" form used in URLs; None if malformed."""
        try:
            parts = [int(part) for part in str(value).split(".")]
        except ValueError:
            return None
        return cls(*parts) if len(parts) == 3 and all(p > 0 for p in parts) else None

    @property
    def key(self):
        return f"{self.batch_id}.{self.semester_id}.{self.section_id}"

    def filter(self, prefix=""):
        return {f"{prefix}batch_id": self.batch_id, f"{prefix}semester_id": self.semester_id,
                f"{prefix}section_id": self.section_id}


# ---------------------------------------------------------------------------------------------
# Locks and fresh reads
# ---------------------------------------------------------------------------------------------

def lock_sections(section_ids):
    """Step 1 of the global lock order: the cohort locks, ascending primary key."""
    ids = sorted({pk for pk in section_ids if pk is not None})
    if ids:
        list(Section.objects.select_for_update().filter(pk__in=ids).order_by("pk"))


def lock_current_periods(period_ids):
    """Step 3: current representation periods, ascending primary key."""
    ids = sorted({pk for pk in period_ids if pk is not None})
    if not ids:
        return {}
    return {p.pk: p for p in Period.objects.select_for_update().filter(pk__in=ids, is_active=True).order_by("pk")}


def lock_users(user_ids):
    """Step 4: user rows, ascending primary key."""
    ids = sorted({pk for pk in user_ids if pk is not None})
    if not ids:
        return {}
    return {u.pk: u for u in User.objects.select_for_update().filter(pk__in=ids).order_by("pk")}


def cohort_is_active(cohort):
    """Plain fresh reads of the three entries (after the Section lock; never a Batch/Semester lock)."""
    return (
        Batch.objects.filter(pk=cohort.batch_id, is_active=True).exists()
        and Semester.objects.filter(pk=cohort.semester_id, is_active=True).exists()
        and Section.objects.filter(pk=cohort.section_id, is_active=True).exists()
    )


def active_members(cohort):
    """Active student accounts whose current profile is in this exact cohort."""
    return User.objects.filter(is_active=True, role=User.Role.STUDENT, **cohort.filter("student_profile__"))


def current_period(cohort):
    return Period.objects.current().filter(**cohort.filter()).first()


def current_post_of(user_id):
    """The current period in which this user is CR or GR, if any."""
    return Period.objects.current().filter(Q(cr_id=user_id) | Q(gr_id=user_id)).first()


def post_in(period, user_id):
    return "cr" if period.cr_id == user_id else "gr" if period.gr_id == user_id else None


def can_manage_cohort(actor, cohort):
    """DEC-245: the Super Admin, or a Batch Advisor assigned to this exact cohort."""
    if not (actor and actor.is_authenticated and actor.is_active):
        return False
    if actor.is_super_admin:
        return True
    return actor.is_batch_advisor and AdvisorAssignment.objects.filter(advisor=actor, **cohort.filter()).exists()


def _require_manager(actor, cohort):
    if not can_manage_cohort(actor, cohort):
        raise PermissionDenied("Only the Super Admin or a Batch Advisor of this cohort can manage its representatives.")


def _check_candidate(user, cohort, field, *, own_period=None):
    """An eligible representative: active, a student, in this exact cohort, holding no other post."""
    if user is None or not user.is_active or not user.is_student:
        raise ValidationError({field: "Choose an active student of this cohort."})
    profile = StudentProfile.objects.filter(user_id=user.pk).values_list("batch_id", "semester_id", "section_id").first()
    if profile is None or Cohort(*profile) != cohort:
        raise ValidationError({field: "This student is not in this exact cohort."})
    held = current_post_of(user.pk)
    if held is not None and (own_period is None or held.pk != own_period.pk):
        raise ValidationError({field: "This student already holds a representative post."})


def _end(period, reason, actor):
    ended = Period.objects.filter(pk=period.pk)._end_current(reason=reason, ended_by=actor, ended_at=timezone.now())
    if ended != 1:
        raise ValidationError(CONCURRENT_CHANGE)


def _start(cohort, cr_id, gr_id, actor):
    try:
        with transaction.atomic():
            return Period.objects.create(cr_id=cr_id, gr_id=gr_id, started_by=actor, **cohort.filter())
    except IntegrityError as error:  # the unique indexes: the final safeguard behind the locks
        raise ValidationError(CONCURRENT_CHANGE) from error


# ---------------------------------------------------------------------------------------------
# Appointment, replacement and swap (spec 5.2)
# ---------------------------------------------------------------------------------------------

@transaction.atomic
def appoint_representatives(actor, cohort, *, cr, gr):
    """Appoint a cohort's CR and GR together, for an active cohort awaiting representatives."""
    lock_sections([cohort.section_id])
    _require_manager(actor, cohort)
    if not cohort_is_active(cohort):
        raise ValidationError(INACTIVE_COHORT)
    if current_period(cohort) is not None:
        raise ValidationError(ALREADY_REPRESENTED)
    if cr is None or gr is None:
        raise ValidationError("Choose both a CR and a GR: they are appointed together.")
    if cr.pk == gr.pk:
        raise ValidationError({"gr": "The CR and the GR must be different students."})
    users = lock_users([cr.pk, gr.pk])
    _check_candidate(users.get(cr.pk), cohort, "cr")
    _check_candidate(users.get(gr.pk), cohort, "gr")
    return _start(cohort, cr.pk, gr.pk, actor)


@transaction.atomic
def replace_representatives(actor, cohort, *, expected_period, cr=None, gr=None, swap=False):
    """Replace the CR, the GR, or both, or swap them, ending the current period and starting the
    next in one transaction. There is no removal: a post changes only to another student."""
    lock_sections([cohort.section_id])
    _require_manager(actor, cohort)
    if not cohort_is_active(cohort):
        raise ValidationError(INACTIVE_COHORT)
    period = current_period(cohort)
    if period is None or str(period.pk) != str(expected_period):
        raise ValidationError(STALE_PERIOD)
    period = lock_current_periods([period.pk]).get(period.pk)
    if period is None:
        raise ValidationError(STALE_PERIOD)
    if swap:
        new_cr, new_gr = period.gr_id, period.cr_id
    else:
        if cr is None and gr is None:
            raise ValidationError("A representative can only be replaced by another student; posts are never left vacant.")
        new_cr = cr.pk if cr is not None else period.cr_id
        new_gr = gr.pk if gr is not None else period.gr_id
    if (new_cr, new_gr) == (period.cr_id, period.gr_id):
        raise ValidationError({"cr" if cr is not None else "gr": "Choose a different student from the current one."})
    if new_cr == new_gr:
        raise ValidationError({"cr" if cr is not None else "gr": "The CR and the GR must be different students."})
    users = lock_users([new_cr, new_gr])
    _check_candidate(users.get(new_cr), cohort, "cr", own_period=period)
    _check_candidate(users.get(new_gr), cohort, "gr", own_period=period)
    changed_cr, changed_gr = new_cr != period.cr_id, new_gr != period.gr_id
    reason = Reason.BOTH_REPLACED if changed_cr and changed_gr else Reason.CR_REPLACED if changed_cr else Reason.GR_REPLACED
    _end(period, reason, actor)
    return _start(cohort, new_cr, new_gr, actor)


def swap_representatives(actor, cohort, *, expected_period):
    return replace_representatives(actor, cohort, expected_period=expected_period, swap=True)


# ---------------------------------------------------------------------------------------------
# A representative leaving (deactivation or cohort change; spec 5.4, DEC-323)
# ---------------------------------------------------------------------------------------------

def resolve_departure(user, period, *, actor, replacement, inactive_reason):
    """Called by the lifecycle services, under their locks, before the account or profile change.

    Active cohort: replace in the same transaction, refuse, or close when fewer than two active
    students would remain. Inactive cohort: the period simply ends (no new appointments there)."""
    cohort = Cohort.of(period)
    post = post_in(period, user.pk)
    if not cohort_is_active(cohort):
        if replacement is not None:
            raise ValidationError({"replacement": "This cohort is inactive: no replacement can be appointed in it."})
        _end(period, inactive_reason, actor)
        return
    remaining = active_members(cohort).exclude(pk=user.pk).count()
    if replacement is not None:
        other = period.gr_id if post == "cr" else period.cr_id
        if replacement.pk in (user.pk, other):
            raise ValidationError({"replacement": "Choose a student who isn't already this cohort's CR or GR."})
        _check_candidate(replacement, cohort, "replacement")
        _end(period, Reason.CR_REPLACED if post == "cr" else Reason.GR_REPLACED, actor)
        new_cr, new_gr = (replacement.pk, period.gr_id) if post == "cr" else (period.cr_id, replacement.pk)
        _start(cohort, new_cr, new_gr, actor)
        return
    if remaining >= 2:
        label = f"{period.batch} · {period.semester} · {period.section}"
        raise ValidationError({"replacement": (
            f"This student is the {POST_LABELS[post]} ({POST_NAMES[post]}) of {label}. "
            f"Choose a new {POST_LABELS[post]} in the same change; a representative post can't be left vacant."
        )})
    _end(period, Reason.COHORT_CLOSED, actor)  # DEC-323: fewer than two active students remain


# ---------------------------------------------------------------------------------------------
# Authority and consistency (spec 5.3)
# ---------------------------------------------------------------------------------------------

def current_representative(user):
    """The user's current period if they are a representative of their current cohort (for
    viewing representative-only areas; inactive academic entries don't matter), else None."""
    if not (user and user.is_authenticated and user.is_active and user.is_student):
        return None
    profile = StudentProfile.objects.filter(user_id=user.pk).values_list("batch_id", "semester_id", "section_id").first()
    if profile is None:
        return None
    period = current_post_of(user.pk)
    if period is None or period.cohort != tuple(profile):
        return None
    return period


def can_act_as_representative(user):
    """As current_representative, and the cohort's batch, semester and section are all active
    (for new actions, such as raising an issue)."""
    period = current_representative(user)
    if period is None or not cohort_is_active(Cohort.of(period)):
        return None
    return period


def representation_breaches():
    """Current periods of active cohorts that name an ineligible representative (inactive, not a
    student, no profile, or no longer in that exact cohort). The services never produce these;
    this makes a breach through any other path visible."""
    periods = Period.objects.current().select_related(
        "batch", "semester", "section", "cr", "gr", "cr__student_profile", "gr__student_profile"
    )
    breaches = []
    for period in periods:
        cohort = Cohort.of(period)
        if not (period.batch.is_active and period.semester.is_active and period.section.is_active):
            continue
        problems = []
        for post, person in (("cr", period.cr), ("gr", period.gr)):
            profile = getattr(person, "student_profile", None) if person.is_student else None
            if not person.is_active or not person.is_student or profile is None or Cohort.of(profile) != cohort:
                problems.append(post)
        if problems:
            breaches.append((period, problems))
    return breaches


def eligible_candidates(cohort):
    """Students who could take a post in this cohort now: active, in this exact cohort, holding
    no current post anywhere. For display only; the services re-check under their locks."""
    holders = {pk for pair in Period.objects.current().order_by().values_list("cr_id", "gr_id") for pk in pair}
    return (active_members(cohort).exclude(pk__in=holders)
            .select_related("student_profile").order_by("full_name", "email"))


def departure_needs_replacement(user):
    """(period, post, remaining_others) when deactivating or moving `user` would require a
    replacement under DEC-323 (an active, represented cohort keeping two or more other active
    students), else None. For form pre-checks only; the services decide under their locks."""
    if user is None or user.pk is None:
        return None
    period = current_post_of(user.pk)
    if period is None or not cohort_is_active(Cohort.of(period)):
        return None
    remaining = active_members(Cohort.of(period)).exclude(pk=user.pk).count()
    return (period, post_in(period, user.pk), remaining) if remaining >= 2 else None
