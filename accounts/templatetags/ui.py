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


# --- The status colour map (accounts.tones) ------------------------------------------------------

@register.filter
def tone(value, domain=None):
    """`{{ complaint.status|tone }}` -> "review". Unknown values are "neutral"."""
    from accounts import tones
    return tones.tone(value, domain)


@register.filter
def detail_doodle(tone_name):
    """The detail hero's corner doodle for a tone: "resolved" -> "landed"."""
    from accounts import tones
    return tones.detail_doodle(tone_name)


@register.filter
def pastel(tone_name):
    """The pastel family a tone is drawn in: "review" -> "amber"."""
    from accounts import tones
    return tones.TONE_PASTEL.get(tone_name, tone_name if tone_name in tones.PASTELS else "sand")


@register.filter
def voice_type_pastel(value):
    from accounts import tones
    return tones.voice_type_pastel(value)


@register.filter
def category_pastel(category):
    from accounts import tones
    return tones.category_pastel(category)


@register.filter
def notification_tone(notification):
    from accounts import tones
    return tones.notification_tone(getattr(notification, "event_type", notification))


@register.filter
def notification_icon(notification):
    from accounts import tones
    return tones.notification_icon(getattr(notification, "event_type", notification))


AVATAR_PASTELS = ("mint", "sky", "lavender", "peach", "amber", "rose")


@register.filter
def avatar_pastel(name):
    """A stable pastel for a person's avatar circle, from their name (never random per page)."""
    text = str(name or "")
    return AVATAR_PASTELS[sum(ord(ch) for ch in text) % len(AVATAR_PASTELS)] if text else "sand"


@register.simple_tag(takes_context=True)
def active_filter_count(context, defaults=None):
    """How many of the page's filters, search and sort are not at their default: drives the
    "Reset · N" pill. `list_keys` names the page's parameters; `list_defaults` (or `defaults`)
    maps a key to its default value (for example {"sort": "newest"}). The page number never counts."""
    request = context.get("request")
    if request is None:
        return 0
    keys = context.get("list_keys")
    keys = list(keys) if keys is not None else list(request.GET)
    defaults = defaults if defaults is not None else (context.get("list_defaults") or {})
    count = 0
    for key in keys:
        if key == "page":
            continue
        value = request.GET.get(key, "")
        if value and str(value) != str(defaults.get(key, "")):
            count += 1
    return count


@register.simple_tag
def tone_for(status=None, domain=None, known=None):
    """`{% tone_for status domain tone as t %}`: the known tone when given, else the status's.
    A simple tag, so an unset `domain` or `tone` in an include is simply empty."""
    from accounts import tones
    if known:
        return known
    return tones.tone(status, domain or None)


# --- List pages (Polish v2 P2a) ------------------------------------------------------------------

@register.simple_tag(takes_context=True)
def stat_tab_url(context, param, value, current):
    """A stat card used as a filter tab: {"url", "selected"}. Clicking the selected card clears it;
    the page's other filters are kept (filter_url)."""
    selected = str((current or {}).get(param, "") or "") == str(value)
    return {"url": filter_url(context, param, "" if selected else value), "selected": selected}


@register.simple_tag(takes_context=True)
def active_filters(context, specs):
    """The active filters as removable pills: [{"label", "url", "tip"}]. specs: [(param, label, choices)]
    or (param, label, choices, tips), tips mapping a value to a tooltip (for example a term's dates);
    choices None means a free-text value (the search). Only a value that is one of the choices shows."""
    request = context["request"]
    pills = []
    for param, label, choices, *rest in specs or ():
        tips = rest[0] if rest else {}
        value = request.GET.get(param, "")
        if not value:
            continue
        if choices is None:
            text = value
        else:
            text = dict((str(k), v) for k, v in choices).get(value)
            if not text or value == "":
                continue
        pills.append({"label": f"{label}: {text}", "url": filter_url(context, param, ""), "tip": tips.get(value, "")})
    return pills
