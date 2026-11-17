"""
Complaint category and subcategory management (Complaints Part 4 Stage 2; spec section 4).

Every operation requires an active Super Admin (checked here, not only in the views), runs in
a transaction and raises:
- django.core.exceptions.PermissionDenied: the actor may not manage categories;
- django.core.exceptions.ValidationError: invalid input or a rule refused the change, keyed by
  field ("name") or, for state rules, a plain message.

Rules:
- Names are trimmed, internal whitespace is collapsed, empty names are refused and the limit is
  80 characters. Duplicates are refused, including inactive records: category names are unique
  overall, subcategory names within their parent. Comparison ignores case and accents, matching
  the MySQL collation (utf8mb4_0900_ai_ci) so behaviour does not depend on the database; any
  duplicate the database still catches (IntegrityError) becomes the same error.
- New records go to the end of their list. Reordering is one step up or down: siblings are
  locked and renumbered 1..n first, so tied positions cannot block a move; a move past either
  end is a no-op.
- Deactivating a category never changes its subcategories' flags (a subcategory under an
  inactive category is unavailable for new complaints regardless). The last active category
  cannot be deactivated. A subcategory may be created under an inactive category.
- Renaming or deactivating never touches complaints: they keep their foreign keys and show
  the current name. Nothing is deleted, and a subcategory's parent never changes.
"""

import unicodedata

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from .models import ComplaintCategory, ComplaintSubcategory

NAME_LIMIT = ComplaintCategory._meta.get_field("name").max_length  # 80, the same for subcategories
UP, DOWN = "up", "down"


def _require_super_admin(actor):
    if not (actor and actor.is_authenticated and actor.is_active and actor.is_super_admin):
        raise PermissionDenied("Only an active Super Admin can manage complaint categories.")


def normalize_name(name):
    """Trim and collapse whitespace; refuse empty or over-long names."""
    cleaned = " ".join((name or "").split())
    if not cleaned:
        raise ValidationError({"name": "Enter a name."})
    if len(cleaned) > NAME_LIMIT:
        raise ValidationError({"name": f"Use at most {NAME_LIMIT} characters (this name has {len(cleaned)})."})
    return cleaned


def name_key(name):
    """Comparison key ignoring case and accents, like MySQL's utf8mb4_0900_ai_ci."""
    decomposed = unicodedata.normalize("NFKD", name)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()


def _refuse_duplicate(siblings, name, message, exclude_pk=None):
    key = name_key(name)
    for pk, existing in siblings.values_list("pk", "name"):
        if pk != exclude_pk and name_key(existing) == key:
            raise ValidationError({"name": message.format(existing=existing)})


def _save_name(record, message, **save_kwargs):
    """Save in a savepoint so a duplicate caught by the database becomes a field error."""
    try:
        with transaction.atomic():
            record.save(**save_kwargs)
    except IntegrityError:
        raise ValidationError({"name": message.format(existing=record.name)}) from None


def _next_position(siblings):
    """One past the highest position, with the siblings locked."""
    return max(siblings.select_for_update().values_list("position", flat=True), default=0) + 1


def _move(siblings, record, direction):
    if direction not in (UP, DOWN):
        raise ValidationError("Choose to move up or down.")
    rows = list(siblings.select_for_update().order_by("position", "name", "pk"))
    for number, row in enumerate(rows, start=1):  # renumber so ties cannot block a move
        if row.position != number:
            row.position = number
            row.save(update_fields=["position"])
    index = next(i for i, row in enumerate(rows) if row.pk == record.pk)
    other = index - 1 if direction == UP else index + 1
    if not 0 <= other < len(rows):
        return rows[index]  # already first or last: no-op
    rows[index].position, rows[other].position = rows[other].position, rows[index].position
    rows[index].save(update_fields=["position"])
    rows[other].save(update_fields=["position"])
    return rows[index]


# ---------- Categories ----------

CATEGORY_DUPLICATE = "A category named “{existing}” already exists. Names must be unique, including inactive categories."


@transaction.atomic
def create_category(actor, name):
    _require_super_admin(actor)
    name = normalize_name(name)
    _refuse_duplicate(ComplaintCategory.objects.all(), name, CATEGORY_DUPLICATE)
    category = ComplaintCategory(name=name, position=_next_position(ComplaintCategory.objects.all()))
    _save_name(category, CATEGORY_DUPLICATE)
    return category


@transaction.atomic
def rename_category(actor, category, name):
    _require_super_admin(actor)
    name = normalize_name(name)
    category = ComplaintCategory.objects.select_for_update().get(pk=category.pk)
    if category.name == name:
        return category
    _refuse_duplicate(ComplaintCategory.objects.all(), name, CATEGORY_DUPLICATE, exclude_pk=category.pk)
    category.name = name
    _save_name(category, CATEGORY_DUPLICATE, update_fields=["name"])
    return category


@transaction.atomic
def set_category_active(actor, category, active):
    _require_super_admin(actor)
    if not active:
        # Lock every active category so two deactivations cannot both pass the check.
        active_pks = list(ComplaintCategory.objects.select_for_update().filter(is_active=True).values_list("pk", flat=True))
        if active_pks == [category.pk]:
            raise ValidationError(
                "This is the only active category. Students need at least one, so activate another "
                "category before deactivating this one.",
                code="last_active_category",
            )
    category = ComplaintCategory.objects.select_for_update().get(pk=category.pk)
    if category.is_active != active:
        category.is_active = active
        category.save(update_fields=["is_active"])
    return category


@transaction.atomic
def move_category(actor, category, direction):
    _require_super_admin(actor)
    return _move(ComplaintCategory.objects.all(), category, direction)


# ---------- Subcategories ----------

SUBCATEGORY_DUPLICATE = (
    "This category already has a subcategory named “{existing}”. Names must be unique within a "
    "category, including inactive subcategories."
)


@transaction.atomic
def create_subcategory(actor, category, name):
    """Allowed under an inactive category; it stays unavailable to students until the
    category is active again."""
    _require_super_admin(actor)
    name = normalize_name(name)
    category = ComplaintCategory.objects.select_for_update().get(pk=category.pk)
    siblings = ComplaintSubcategory.objects.filter(category=category)
    _refuse_duplicate(siblings, name, SUBCATEGORY_DUPLICATE)
    subcategory = ComplaintSubcategory(category=category, name=name, position=_next_position(siblings))
    _save_name(subcategory, SUBCATEGORY_DUPLICATE)
    return subcategory


@transaction.atomic
def rename_subcategory(actor, subcategory, name):
    _require_super_admin(actor)
    name = normalize_name(name)
    subcategory = ComplaintSubcategory.objects.select_for_update().get(pk=subcategory.pk)
    if subcategory.name == name:
        return subcategory
    siblings = ComplaintSubcategory.objects.filter(category_id=subcategory.category_id)
    _refuse_duplicate(siblings, name, SUBCATEGORY_DUPLICATE, exclude_pk=subcategory.pk)
    subcategory.name = name
    _save_name(subcategory, SUBCATEGORY_DUPLICATE, update_fields=["name"])
    return subcategory


@transaction.atomic
def set_subcategory_active(actor, subcategory, active):
    _require_super_admin(actor)
    subcategory = ComplaintSubcategory.objects.select_for_update().get(pk=subcategory.pk)
    if subcategory.is_active != active:
        subcategory.is_active = active
        subcategory.save(update_fields=["is_active"])
    return subcategory


@transaction.atomic
def move_subcategory(actor, subcategory, direction):
    _require_super_admin(actor)
    return _move(ComplaintSubcategory.objects.filter(category_id=subcategory.category_id), subcategory, direction)
