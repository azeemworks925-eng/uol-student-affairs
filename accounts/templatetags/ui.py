"""Small display helpers shared by the design-system partials in templates/includes/ui/."""

from urllib.parse import urlencode

from django import template
from django.utils import timezone

register = template.Library()


@register.filter
def initials(name):
    """Up to two initials: "Ali Khan" -> "AK". Titles such as "Dr." are skipped."""
    words = [word for word in str(name or "").split() if not word.endswith(".")]
    if not words:
        return "?"
    picked = [words[0], words[-1]] if len(words) > 1 else words
    return "".join(word[0] for word in picked).upper()


@register.filter
def cohort_short(record):
    """The short cohort chip text: "DEMO-A · S4"."""
    return f"{record.section.name} · S{record.semester.number}"


@register.filter
def cohort_full(record):
    """The exact cohort, for the chip's tooltip: "Fall 2026 · Semester 4 · Section A"."""
    return f"{record.batch} · {record.semester} · {record.section}"


@register.filter
def ago(moment):
    """A short relative time: "just now", "5m ago", "3h ago", "2d ago", then the date."""
    if not moment:
        return ""
    seconds = int((timezone.now() - moment).total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    if seconds < 86400 * 14:
        return f"{seconds // 86400}d ago"
    local = timezone.localtime(moment)
    return f"{local.day} {local:%b %Y}"


@register.simple_tag(takes_context=True)
def filter_url(context, param, value=""):
    """This page's query with one filter set (or cleared when empty), back on the first page.
    Only the page's own parameters (`list_keys`) are carried, so nothing leaks between roles."""
    request = context["request"]
    allowed = context.get("list_keys")
    keys = list(allowed) if allowed is not None else list(request.GET)
    if param not in keys:
        keys.append(param)
    values = {key: request.GET[key] for key in keys if request.GET.get(key)}
    values.pop("page", None)
    if value in ("", None):
        values.pop(param, None)
    else:
        values[param] = str(value)
    encoded = urlencode([(key, values[key]) for key in keys if key in values])  # a stable order
    if param == "page":
        return f"?{encoded}"
    return f"{request.path}?{encoded}" if encoded else request.path
