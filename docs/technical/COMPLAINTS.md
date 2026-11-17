# Complaints — technical notes

**Status:** Parts 1–3 are merged into main (PRs #7–#11). Part 4 is specified in COMPLAINTS_PART4_SPEC.md (merged in PR #12). Part 4 Stage 1 (Super Admin complaint workspace and owner assignment) is merged through PR #14. Part 4 Stage 2 (category and subcategory management, section 6) is merged through PR #15. Part 4 Stage 3 (in-app notifications, section 7) is merged through PR #16 (`d857d27`). Part 4 Stage 4a (academic terms and the Super Admin term filter, section 8) is on branch `feat/academic-term`, awaiting review. Stage 4b (analytics) and Stage 5 (final acceptance) are not implemented.
**Decisions:** DEC-030, DEC-031, DEC-220 to DEC-230, and DEC-310 to DEC-315 in docs/decisions/DECISIONS.md. Complaint-specific portions of O27, O28 and O33 are resolved; see the decision register for remaining open items.

## 1. Backend (`complaints/`)

| Module | Responsibility |
|---|---|
| `models.py` | `ComplaintCategory`, `ComplaintSubcategory`, `Complaint`, `ComplaintEvent`. The cohort (batch + semester + section) is stored at submission. History is insert-only. Bulk updates and deletes are refused (`ProtectedQuerySet`). |
| `services.py` | Every state change: `submit_complaint`, `change_status` (with an optional `expected_status` safeguard, P3-6), `respond`, `mark_still_not_resolved`, `add_further_information`, `request_cancellation`, `assign_responsible`, plus the `possible_duplicates` helper. Each runs in a transaction, checks permission and records an event. |
| `permissions.py` | `visible_complaints(user)`, `get_visible_complaint(user, reference)` (404 when out of scope), `can_view_complaint`, `can_manage_complaint`, `is_complaint_owner`. Students see only their own complaints; Batch Advisors see exact assigned cohorts; Super Admins see everything. |

Views must load complaints through `permissions` and change them only through `services`.

## 2. Student pages (Part 2)

| Route | Name | Page |
|---|---|---|
| `/student/complaints/` | `student_complaints` | My Submissions (DEC-031): the student's own complaints, newest first, 10 per page, with a status filter (`?status=received`, `under_review`, `resolved`, `rejected`). |
| `/student/complaints/new/` | `student_complaint_new` | Submit a complaint. |
| `/student/complaints/<reference>/` | `student_complaint_detail` | Details, original description, history and actions. |
| `/student/complaints/<reference>/information/` (POST) | `student_complaint_add_information` | `services.add_further_information` |
| `/student/complaints/<reference>/still-not-resolved/` (POST) | `student_complaint_still_not_resolved` | `services.mark_still_not_resolved` |
| `/student/complaints/<reference>/cancellation/` (POST) | `student_complaint_request_cancellation` | `services.request_cancellation` |

Code: `complaints/views.py`, `forms.py`, `presentation.py`, `urls.py`; templates in `templates/complaints/student/`; `static/js/complaints.js` for progressive enhancement.

### Access

- Every view uses `student_required`: a signed-in, active student. Other roles get 403, anonymous visitors are sent to sign-in, and unregistered students are sent to registration by `StudentRegistrationMiddleware`.
- A complaint is always loaded with `get_visible_complaint(request.user, reference)`. Someone else's reference and a reference that does not exist return the same 404.
- Actions are POST-only and CSRF-protected. The services re-check ownership and the complaint's state.

### Submission

- The form has category, optional subcategory, title and description. It has no student or cohort fields; `submit_complaint` takes the cohort from the student's registered profile and ignores anything else posted.
- **Choices.** Only active categories, and active subcategories of active categories, are offered. Subcategories are grouped by category, so the list is understandable without JavaScript; with JavaScript, only the chosen category's subcategories are shown. The form rejects a subcategory from another category, and the service checks again.
- **Duplicate warning (DEC-225).** The page embeds the student's own open complaints per active category (reference and title only, from `possible_duplicates`). When the student picks a category with open complaints, a notice links to them. It never blocks submission.
- **After submitting.** On success the browser is redirected to the new complaint (Post/Redirect/Get), and a message gives the reference. The submit button is disabled after the first click to prevent double submission.
- **Errors.** On a validation error the values are kept, and each error is linked to its field with `aria-describedby`.

### Details

- The page shows the reference, status, title, category and subcategory, submission time, and the cohort at submission (the student's own). It shows the status journey (Received → Under Review → Resolved or Rejected) and the original description, labelled as such and read-only.
- **History (`presentation.student_timeline`).** Recorded events only, oldest first, with plain labels. A rejection reason and a resolution note are shown with their labels. Staff appear by role (for example, "Batch Advisor"), never by name or email. Responsible-owner changes are not shown to students while O27 is open.
- **Actions:**
  - *Add further information:* always available. It adds an event; the original never changes.
  - *Still not resolved:* shown only when the status is Resolved. It returns the complaint to Under Review.
  - *Request cancellation:* shown for open complaints (Received, Under Review) until a request is recorded. It only records the request; the status does not change and nothing is cancelled or deleted (O28).
  - If a posted action is not allowed in the complaint's current state, the service's reason is shown as a message and nothing changes.

## 3. Batch Advisor workspace (Part 3)

Specification: `docs/technical/COMPLAINTS_PART3_SPEC.md` (approved in PR #10, decisions P3-1 to P3-8).

| Route | Name | Purpose |
|---|---|---|
| `/advisor/complaints/` | `advisor_complaints` | The workspace with no case selected (laptop: list plus "Choose a complaint"; phone: the list). |
| `/advisor/complaints/<reference>/` | `advisor_complaint_detail` | The same workspace with the case selected (phone: the case alone, with a back link). |
| `/advisor/complaints/<reference>/respond/` (POST) | `advisor_complaint_respond` | `services.respond`: never changes the status (DEC-305). |
| `/advisor/complaints/<reference>/status/` (POST) | `advisor_complaint_status` | `services.change_status(..., expected_status=...)`. |

Code: the shared engine `complaints/workspace.py` (configured by `ADVISOR`), the thin views `complaints/advisor_views.py`, `advisor_urls.py`, the workspace forms in `forms.py`, `presentation.staff_timeline`, and `templates/complaints/workspace/` (`workspace.html` with `_list`, `_case`, `_context` and `_status_form` partials, shared with the Super Admin workspace in section 5).

### Access

- Every view is `batch_advisor_required`.
- The list starts from `visible_complaints(user)`: exact batch + semester + section assignments only. Advisors sharing a cohort see the same list.
- Every case, on GET and on both POST routes, is loaded with `get_visible_complaint`, so an out-of-cohort reference returns the same 404 as an unknown one.
- The cohort filter accepts only the advisor's own assignments (an exact `batch.semester.section` value). Any other value is ignored, so filters can only narrow the list.

### List

- **Headline:** a sentence with true counts, for example "Your cohorts have 3 open complaints: 2 received and 1 under review."
- **Search** by reference (contains), student name (contains) or SAP ID (prefix; P3-3). Search never reaches outside the visible set.
- **Filters:** cohort (shown only to advisors with several cohorts; defaults to all assigned cohorts, DEC-283), status (All by default, P3-4; or Open, Received, Under Review, Resolved, Rejected) and category (only categories used by visible complaints).
- **Sort:** latest activity (default) or newest submitted. Both are factual; there is no priority or age ordering.
- **Pages and state:** 20 per page. The search, filters, sort and page are kept in every link, form action and redirect.
- **Rows:** reference, status, title, full student name, cohort at submission, last activity date, and the factual labels "Cancellation requested" and "Reopened by student" (P3-2). The selected row has `aria-current="true"` and the ink indicator.

### Case

- **Header and context:**
  - The header shows the reference, status, title, category, submission time and status journey.
  - The context shows the student's name and SAP ID (no email, P3-1), the **cohort recorded at submission only** (P3-5), and the active Batch Advisors of that exact cohort, with "(you)".
  - No responsible owner is shown (O27), and not the student's other complaints (DEC-305).
- **History:** newest first (P3-7), with names and roles. Owner changes are hidden (O27). Cancellation requests and "Still not resolved" appear as events, with no controls (O28).
- **Respond:** a separate form. Its text is visible to the student, and it never changes the status.
- **Update status:**
  - It offers only `STAFF_TRANSITIONS` from the status the advisor saw.
  - A note is required for Resolved and Rejected; the form, the service and the database checks all enforce this. The note label follows the chosen status with JavaScript.
  - A hidden `expected_status` field carries the status the advisor saw. The service compares it under the row lock and refuses a stale change atomically, and the page explains what changed.
  - A Resolved or Rejected complaint shows a sentence instead of the form.

### Layout

| Width | Layout |
|---|---|
| ≥ 1360px | The list and case side by side, each scrolling within the viewport. The context is a sticky column beside the case. |
| 992–1359px, including the 1280×590 reference laptop | The list and case side by side. The context is a strip under the case header. |
| < 992px | The list, or the selected case alone, with a back link (keeping the list state) and a sticky Respond / Update status bar. |

One template serves every state; CSS decides the layout from `sa-workspace--has-case`. Filters collapse into a "Filters and sort" disclosure. Touch targets are at least 44px below 992px.

## 4. Known limitations

- **Owner/cancellation/queue behaviour (DEC-310 to DEC-312).** The Super Admin designates the owner manually (section 5); cancellation requests are record-only; no response-required queue exists. Student-facing owner identity and history remain hidden. The Batch Advisor workspace is unchanged from Part 3: it does not show the owner or owner-change events (see section 5, "Batch Advisor workspace").
- **Advisor workspace.** It has no seen/unseen tracking, and no notifications for status changes and responses (DEC-270); notifications are Part 4 Stage 3.
- **Cancellation display.** Offering cancellation only for open complaints, and only once, is a presentation choice; the service itself accepts a request in any state.
- **Student home.** "Your latest updates" (DEC-282, DEC-303) does not yet list complaint activity: it needs seen/unseen tracking, which is not built.
- **Double submission.** This is prevented in the browser and by Post/Redirect/Get, not by a server-side token. Duplicates are allowed by DEC-225 in any case.
- **Theme.** Only Forest Light is implemented (Forest Dark is approved but not built; O34 open).


## Part 4 overview (Super Admin oversight)

Specification: COMPLAINTS_PART4_SPEC.md (owner-approved scope and decisions; submitted for review).

Part 4 covers the department-wide Super Admin complaint workspace with manual owner assignment (DEC-228, DEC-310); category/subcategory management with deactivation rather than deletion (DEC-220); a reusable in-app notification foundation and approved student complaint events (DEC-070, DEC-270); and the three complaint analytics on the existing Super Admin Overview (DEC-280, DEC-281, DEC-306), using the academic-term window and privacy rules (DEC-313 to DEC-315).

Cancellation requests remain record-only (DEC-311). There is no response-required classification or “Waiting for you” queue (DEC-312). Student-facing owner identities and owner-change events remain hidden. Student Voice, meetings and collective issues are not implemented by this complaints part; the notification foundation is designed to support their already-approved events when those modules are built.

The specification was merged in PR #12. Stage 1 is described in section 5, Stage 2 in section 6, Stage 3 in section 7 and Stage 4a (under review) in section 8; Stage 4b and Stage 5 are not implemented.

## 5. Super Admin complaint workspace and owner assignment (Part 4 Stage 1)

Specification: COMPLAINTS_PART4_SPEC.md section 3. Issue #13. Decisions DEC-228, DEC-310 to DEC-312. **No migrations:** `Complaint.responsible`, the `RESPONSIBLE_CHANGED` event and `services.assign_responsible` already existed from Part 1.

| Route | Name | Purpose |
|---|---|---|
| `/super-admin/complaints/` | `super_admin_complaints` | Department-wide workspace, no case selected |
| `/super-admin/complaints/<reference>/` | `super_admin_complaint_detail` | The same workspace with the case selected |
| `…/respond/` (POST) | `super_admin_complaint_respond` | `services.respond` |
| `…/status/` (POST) | `super_admin_complaint_status` | `services.change_status(..., expected_status=...)` |
| `…/owner/` (POST) | `super_admin_complaint_owner` | `services.assign_responsible` |

Code: `complaints/admin_views.py` and `admin_urls.py` (thin views over `complaints/workspace.py`, configured by `SUPER_ADMIN`), `ResponsibleOwnerForm` in `forms.py`, and the shared `templates/complaints/workspace/` templates with `_owner_form.html`.

### Access

- Every route is `super_admin_required`. The role comes from the signed-in account; students, Batch Advisors, inactive users and anonymous visitors are refused.
- The list starts from `visible_complaints(user)`, which is every complaint for a Super Admin, and filters only narrow it. Cases are loaded with `get_visible_complaint` on GET and POST.

### List

- **Search** by reference, **title**, student name or SAP ID.
- **Filters:**
  - exact cohort: every known cohort, from advisor assignments, student registrations and complaints, so an empty real cohort can be chosen; forged values are ignored;
  - status: All (default), Received, Under Review, Resolved, Rejected — no "Open" option, per the spec;
  - category: including inactive categories on records;
  - responsible owner: Any, Unassigned, or each current owner, shown by name and role.
- **Sort:** latest activity (default) or newest submitted. The list state is kept across case links, Back and POST redirects.
- **Rows:** reference, status, title, student name and SAP ID, the cohort at submission, category, last activity, owner (or "Unassigned"), and the factual Part 3 labels.
- **Empty states:** no complaints, no filter matches, and "No complaints have been submitted in <cohort>." for an empty selected cohort.

### Case and owner

- **Content:** the same case pane as Part 3 — original complaint, cohort at submission, category, journey, separate Respond and Update status, allowed transitions, required notes and stale-status protection. Super Admin actions go through the same services.
- **History:** newest first, and **includes owner changes**: "Responsible owner set to <name (role)>" or "<name> took over this complaint".
- **Context:** student name and SAP ID (no email), cohort at submission, the cohort's active Batch Advisors, and the **responsible owner** or "Unassigned". If the owner no longer meets DEC-310 (deactivated or reassigned off the cohort), a factual note says so.
- **Owner panel:** a choice of the active Batch Advisors of the exact cohort, or "Take it over yourself".
  - The rule lives in one place, `services.is_eligible_owner`, used by the service; the form offers `services.eligible_advisors` plus the acting Super Admin.
  - Choosing the current owner is a no-op: no event, and a "No change" message. A real change creates exactly one immutable `RESPONSIBLE_CHANGED` event.
  - Opening a complaint never assigns it. There is no automatic assignment, round-robin or unassign action.
- **The owner grants no access** (DEC-310). Every Batch Advisor of the exact cohort keeps their visibility and actions, and the owner gains nothing outside their cohorts.

### Privacy

Students never see the owner, owner-change events or owner controls: the student pages and `student_timeline` are unchanged.

**Batch Advisor workspace:** unchanged from Part 3. It shows no owner and no owner-change events. The spec says BAs "may" see owner-change events, while Issue #13 says existing Batch Advisor behaviour stays intact, so Stage 1 adds them only to the Super Admin workspace. Showing them to Batch Advisors would be a one-line change (`include_owner_changes`), if the owner wants it.

### Layout

The same three-pane responsive layout as Part 3, beside the Super Admin sidebar. On phones the sticky action bar adds an "Owner" shortcut.

## 6. Category and subcategory management (Part 4 Stage 2)

Specification: COMPLAINTS_PART4_SPEC.md section 4, with the owner's decisions recorded below. **No migrations.**

### Routes

All under `/super-admin/complaint-categories/`. This is a separate prefix, because the workspace route `/super-admin/complaints/<reference>/` would capture `categories/`.

| Route | Name | Method |
|---|---|---|
| `/` | `super_admin_categories` | GET: index |
| `new/` | `super_admin_category_create` | POST |
| `<pk>/` | `super_admin_category_detail` | GET: category page |
| `<pk>/rename/`, `active/`, `move/` | `super_admin_category_rename`, `…_active`, `…_move` | POST |
| `<pk>/subcategories/new/` | `super_admin_subcategory_create` | POST |
| `<pk>/subcategories/<sub_pk>/rename/`, `active/`, `move/` | `super_admin_subcategory_rename`, `…_active`, `…_move` | POST |

Code: `complaints/category_services.py`, `category_views.py`, `category_urls.py`, the name forms in `forms.py`, and `templates/complaints/categories/`.

### Pages

- **Index:** the number of categories and how many are active; an add form; the ordered list with an Active/Inactive label (a neutral style, never a complaint status colour), subcategory and complaint counts, Up/Down (disabled at either end) and Open.
- **Category page:**
  - rename;
  - activate or deactivate, with an explanation of the effect, and for the last active category a note instead of the button;
  - its subcategories, each with rename, activate/deactivate and Up/Down, and an add form.
- **Never present:** a delete control, a parent-editing control or a position field.

### Rules

All rules are in the services. Every service re-checks that the actor is an active Super Admin.

- **Names:**
  - trimmed, with internal whitespace collapsed; empty names refused; at most 80 characters;
  - category names unique overall, subcategory names unique within their parent, **including inactive records**;
  - duplicates compared without case or accents, matching MySQL's `utf8mb4_0900_ai_ci`, so behaviour is the same on SQLite;
  - a duplicate only the database catches (`IntegrityError`) becomes the same field error.
- **Order:**
  - new records go last;
  - Up/Down locks the siblings (`select_for_update`) and renumbers them 1..n before swapping, so tied positions can't block a move;
  - moving past either end changes nothing.
- **Activation:**
  - Deactivating a category doesn't change its subcategories' flags. While the category is inactive, none of its subcategories are offered to students or accepted by `submit_complaint`, whatever their own flag.
  - The **last active category cannot be deactivated**; every active row is locked during the check.
  - A subcategory may be created under an inactive category.
- **History:**
  - Renaming or deactivating never touches complaints. They keep their foreign keys, and **historical complaints show the current name**; there are no name snapshots.
  - There is no audit history of category changes in this stage.
- **No hard deletion** (models):
  - `ComplaintCategory.delete()`, `ComplaintSubcategory.delete()` and queryset `delete()` raise `ProtectedRecordError`, even for unreferenced rows;
  - `update()` and `.active()` are unchanged, and `PROTECT` foreign keys still apply.
- **A subcategory's parent is fixed**, on every ordinary ORM path; each raises `ProtectedRecordError`:
  - instance `save()`, compared with the stored row (this also covers `update_or_create` and `add(bulk=False)`);
  - `SubcategoryQuerySet.update()` / `bulk_update()` naming `category` or `category_id`, and an upserting `bulk_create()` with `category` in `update_fields`;
  - the reverse manager `category.subcategories.add()` / `set()`. In bulk mode these update through the model's base manager and would bypass both of the above, so a guarded reverse descriptor refuses them for subcategories of another category.

  The descriptor is used instead of `Meta.base_manager_name`, which would need a migration. Updates to other fields (`name`, `position`, `is_active`) and inserts are unaffected. Raw SQL and Django's private APIs stay outside what the ORM can protect.

### Security

- Every route is `super_admin_required`.
- Every change is POST and CSRF-protected, with Post/Redirect/Get.
- Lookups use `get_object_or_404`. Subcategories are looked up through their parent, so a forged category/subcategory pairing returns 404.
- Field errors re-render the page with HTTP 400 and linked, focused messages. Rule refusals become a message, and malformed values change nothing.
- These models are not registered in Django admin.

### Staff labels

Staff case details (Batch Advisor and Super Admin), staff category filters and Super Admin list rows show "(inactive)" after an inactive category or subcategory. Student pages show the current name with no marker.

### Navigation

The Super Admin "Complaint Categories" item (Configuration) links to the index and stays current on every category page. This also adds it to the Overview's Manage links.

## 7. Complaint notifications (Part 4 Stage 3)

Specification: COMPLAINTS_PART4_SPEC.md section 5.2; DEC-270. The shared foundation (model, registry, services, pages, header) is described in `docs/technical/NOTIFICATIONS.md`. **Migrations:** only `notifications/0001_initial`; no complaint migration.

### Producers

`complaints/notifications.notify_student(event)` runs inside the existing atomic transactions:
- `services.change_status()` captures the `ComplaintEvent` returned by `_record()` and passes that exact event.
- `services.respond()` passes the event it returns.

So a rolled-back action leaves no notification, and a failed notification rolls the action back.

| Event | Recipient | Title | Body | Destination |
|---|---|---|---|---|
| A Batch Advisor or Super Admin changes the status (`STATUS_CHANGED`) | The student who submitted the complaint | "<reference> is now <status>" | The complaint's own title. **Never** the resolution note or rejection reason. | `student_complaint_detail` |
| A Batch Advisor or Super Admin responds (`RESPONSE`) | The same student | "New response on <reference>" | "<role>: " plus the staff text, truncated to 140 characters | `student_complaint_detail` |

- **Exactly one per event:** each qualifying event creates one notification (the unique constraint makes repeated calls harmless).
- **Never the actor:** the person who acted is never notified (a guard; only staff can perform these actions).
- **Only these two events notify.** Submission, further information, "Still not resolved", cancellation requests and owner changes notify nobody.
- **Only the student receives them:** no Batch Advisor (including others sharing the cohort), Super Admin or other student.
- **Response attribution is by role only** ("Batch Advisor" or "Super Admin"), matching the student history; no account name or email is added. Text the staff member wrote, including any names in it, is kept as written; the full response stays on the complaint page.

### Known limitations

- The student home's "Your latest updates" (DEC-303) still awaits seen/unseen tracking. Notification read state is separate, and Stage 3 does not change the student home.
- There is no retention or clean-up of old notifications.

## 8. Academic-term filter on the Super Admin list (Part 4 Stage 4a)

Academic terms, the current-term services and the reporting window are described in `docs/technical/ACADEMIC_TERMS.md`. This section covers only the complaint list.

- **Filter:** the Super Admin list has an "Academic term" filter: "Any term" (the default) or each term, listed newest first, with its exact dates. The current term is marked ", current".
  - A chosen term keeps complaints **submitted** within its reporting window: `created_at >= start 00:00 Asia/Karachi` and `< the day after the end date at 00:00 Asia/Karachi`. The window comes from `academics.models.term_window`, the only place it is calculated.
  - It combines with search, cohort, status, category, owner and sort.
  - It only narrows `visible_complaints(user)`; access rules are unchanged.
- **Invalid values:** a malformed or unknown `term` value, or the ID of a term that does not exist, is ignored like any other invalid filter. The list is then unfiltered, with no chip.
- **Chip:** when a term is applied, a neutral chip above the rows reads "Submitted in <term> <start> – <end>".
  - **Remove:** its "Remove" link (accessible name "Remove the academic term filter (<term>)") clears only the term and keeps the other filters and sort.
  - **Clear filters:** this also clears the term.
  - The chip never uses a status colour.
- **List state:** `term` is part of the Super Admin list state (`SUPER_ADMIN_LIST_PARAMS`), so it is kept across pagination, case links, Back and POST redirects.
- **Batch Advisor list unchanged:** it still uses `LIST_PARAMS` and `FILTER_PARAMS`. It has no term field; a forged `term` parameter is neither applied nor carried in links or redirects, and its SQL queries are identical with or without one. Student pages don't read `term`.
- **No migration** in the complaints app: the filter uses the existing `created_at` column.
