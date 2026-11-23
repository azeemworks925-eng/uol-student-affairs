"""
Quick search in the top bar. It adds no permission path: every result comes from
visible_complaints / visible_submissions for the signed-in user.

- A complaint reference jumps straight to the complaint (hash table, ordering.find_visible).
- Staff: names and SAP IDs match students behind their visible records (trie).
- Students: only their own complaints and Student Voice submissions, never other people.
"""

from dataclasses import dataclass, field

from django.db.models import Q
from django.urls import reverse

from complaints import ordering
from complaints.permissions import visible_complaints
from complaints.presentation import status_tone
from voice.permissions import visible_submissions
from voice.presentation import add_tones

from .models import User

MAX_QUERY = 60
RESULT_LIMIT = 8
COMPLAINT_DETAIL = {
    User.Role.STUDENT: "student_complaint_detail",
    User.Role.BATCH_ADVISOR: "advisor_complaint_detail",
    User.Role.SUPER_ADMIN: "super_admin_complaint_detail",
}
COMPLAINT_LIST = {User.Role.BATCH_ADVISOR: "advisor_complaints", User.Role.SUPER_ADMIN: "super_admin_complaints"}
VOICE_DETAIL = {
    User.Role.STUDENT: "student_voice_detail",
    User.Role.BATCH_ADVISOR: "advisor_voice_detail",
    User.Role.SUPER_ADMIN: "super_admin_voice_detail",
}


@dataclass
class SearchResults:
    query: str = ""
    jump_url: str = ""
    complaints: list = field(default_factory=list)
    students: list = field(default_factory=list)
    submissions: list = field(default_factory=list)

    @property
    def total(self):
        return len(self.complaints) + len(self.students) + len(self.submissions)


def clean_query(text):
    return " ".join((text or "").split())[:MAX_QUERY]


def quick_search(user, text):
    query = clean_query(text)
    results = SearchResults(query=query)
    if not query:
        return results

    complaints = visible_complaints(user)
    submissions = visible_submissions(user)
    if ordering.normalise_reference(query).startswith("CMP-"):
        found = ordering.find_visible(complaints, query)
        if found is not None:
            results.jump_url = reverse(COMPLAINT_DETAIL[user.role], args=[found.reference])
            return results

    if user.is_student:
        matches = complaints.filter(Q(reference__icontains=query) | Q(title__icontains=query))
        voice = submissions.filter(text__icontains=query)
    else:
        student_ids = {*ordering.matching_student_ids(complaints, query),
                       *ordering.matching_student_ids(submissions, query)}
        search = Q(reference__icontains=query) | Q(student_id__in=student_ids)
        if user.is_super_admin:  # the same fields as the Super Admin's complaint list search
            search |= Q(title__icontains=query)
        matches = complaints.filter(search)
        voice = submissions.filter(student_id__in=student_ids)
        people = (User.objects.filter(pk__in=student_ids).select_related("student_profile")
                  .order_by("full_name", "pk")[:RESULT_LIMIT])
        list_url = reverse(COMPLAINT_LIST[user.role])
        for person in people:
            profile = getattr(person, "student_profile", None)
            sap_id = profile.sap_id if profile else ""
            results.students.append({"name": person.get_full_name(), "sap_id": sap_id,
                                     "url": f"{list_url}?{_q(sap_id or person.get_full_name())}"})

    for complaint in matches.order_by("-created_at", "-pk")[:RESULT_LIMIT]:
        complaint.tone = status_tone(complaint.status)
        complaint.url = reverse(COMPLAINT_DETAIL[user.role], args=[complaint.reference])
        results.complaints.append(complaint)
    rows = list(voice.order_by("-created_at", "-pk")[:RESULT_LIMIT])
    add_tones(rows)
    for submission in rows:
        submission.url = reverse(VOICE_DETAIL[user.role], args=[submission.pk])
    results.submissions = rows
    return results


def _q(value):
    from urllib.parse import urlencode

    return urlencode({"q": value})
