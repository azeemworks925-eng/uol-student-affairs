# Complaints Part 3 — Batch Advisor Complaints Workspace: specification

**Status:** Proposed. For technical-lead review before any implementation.
**Builds on:** `main` at `0cc2013`: Part 1 backend (PR #7) and Part 2 student pages (PR #8).
**Decisions:** DEC-205, DEC-221, DEC-222, DEC-224 to DEC-229, DEC-283, DEC-300, DEC-301, DEC-302, DEC-305, DEC-307; design plan section 5 (Batch Advisor Complaints) and section 8 (Mobile).
**Open, and not decided here:** O27 (responsible owner), O28 (cancellation handling), O33 (which events need a response).

---

## 1. Scope

One workspace where a Batch Advisor finds, reads and acts on the complaints of their assigned cohorts.

**In scope**
- A complaint list with a headline sentence, search, filters and pagination.
- A selected case: details, status journey, history, response composer and status controls.
- A context panel: the student's identity, the exact cohort and the advisors assigned to it.
- Two actions, both through the existing services: **Respond** (`services.respond`) and **Update status** (`services.change_status`).
- Linking the Batch Advisor "Complaints" navigation item to the workspace.
- Responsive behaviour: a three-pane laptop workspace, and list → case → back on phones (360px).

**Out of scope (Part 4 or later)**
- The Super Admin's complaint oversight, reassignment and take-over (DEC-228).
- Category management and notifications (DEC-070, DEC-270).
- Statistics (DEC-280) and analytics (DEC-281).
- Seen/unseen tracking.
- Any change to the backend's business rules.

## 2. Rules the workspace must keep

| Rule | Source | How the workspace keeps it |
|---|---|---|
| Advisors see only complaints whose stored cohort exactly matches one of their assignments. | DEC-205, DEC-229 | Every query starts from `permissions.visible_complaints(user)`. Every case is loaded with `permissions.get_visible_complaint(user, reference)`, which returns 404, never 403. Filters only narrow this set. |
| Advisors sharing a cohort get the same access. | DEC-204, DEC-205 | No per-advisor filtering of the list. |
| Respond and Update status are separate; a response never changes the status. | DEC-305 | Two forms posting to two views, calling `respond` and `change_status` respectively. |
| A rejection reason and a resolution note are mandatory, and visible to the student. | DEC-221 | The status form requires a note for Resolved and Rejected; the service and database checks enforce it again. The UI states "Visible to the student". |
| Status transitions are the service's: Received → Under Review / Resolved / Rejected; Under Review → Resolved / Rejected. Resolved and Rejected are closing states for staff. | `services.STAFF_TRANSITIONS` | The control offers only `STAFF_TRANSITIONS[current]`. For a closed complaint, the status control is replaced by a sentence ("This complaint is resolved. Only the student can reopen it with 'Still not resolved'."). |
| No automatic responsible owner; the owner is not shown or assumed. | DEC-227, O27; design plan 5 | No owner field, label or filter. Owner-change events are hidden in the advisor timeline too, as on the student page. Every advisor of the cohort can act, as the service allows. |
| A cancellation request is recorded only. | DEC-224, O28 | Shown in the history and as a factual list flag. No approve, decline or cancel controls, and no special status. The advisor responds or updates the status as for any complaint. |
| No "Waiting for you" queue and no response-required classification. | O33; DEC-226 | No grouping, sorting or badge that implies an advisor must act. Sort orders are factual (latest activity, newest submitted). |
| "Other complaints from this student" is not shown. | DEC-305 | The context panel has no such list. A name search in the list is still allowed (design plan 5). |
| Staff get workspaces, not dashboards; no invented figures. | DEC-300, DEC-226 | The only figures are true counts in the headline sentence. |

## 3. Routes and views

The same view and template serve every state of the workspace; the URL decides whether a case is selected, and CSS decides the layout. There is no separate desktop page.

| Route | Name | Method | Purpose |
|---|---|---|---|
| `/advisor/complaints/` | `advisor_complaints` | GET | The workspace with no case selected. Laptop: list plus an empty "Choose a complaint" pane. Phone: the list. |
| `/advisor/complaints/<reference>/` | `advisor_complaint_detail` | GET | The workspace with this case selected. Laptop: list, case and context. Phone: the case only, with a "Back to complaints" link that keeps the filters. |
| `/advisor/complaints/<reference>/respond/` | `advisor_complaint_respond` | POST | `services.respond(user, complaint, message)` |
| `/advisor/complaints/<reference>/status/` | `advisor_complaint_status` | POST | `services.change_status(user, complaint, new_status, note)` |

- **Prefix.** These routes sit next to the existing `/advisor/` home in `accounts.urls`, and are mounted from `complaints` like the student routes (`path("advisor/complaints/", include("complaints.advisor_urls"))`, or one `urls.py` with both sets).
- **Decorators and loading.** Every view is `@batch_advisor_required`, and every case is loaded with `get_visible_complaint`. POST views also use `@require_POST`.
- **Filters in the URL.** The list's filters and page live in the query string, and are preserved in every list link, the selected-case links, the Back link and the post-action redirects. A helper builds this "list state" querystring.
- **After an action.** On success, redirect (Post/Redirect/Get) to `advisor_complaint_detail` with the same list state and a success message. On a validation error, re-render the workspace with HTTP 400, the bound form and its panel open, as in Part 2.
- **Errors not tied to a field.** If the service refuses because of the complaint's state (for example, a colleague closed it meanwhile), show the service's message and redirect back to the case, so the advisor sees the current state.
- **Reuse for the Super Admin.** The view functions take the user and use `visible_complaints`/`can_manage_complaint`, so Part 4 can reuse them for the Super Admin by changing only the decorator and route. Nothing is generalised now.

## 4. Left pane: the complaint list

**Headline sentence.** Calculated from the visible set before filters, using true counts only. For example: "Your cohorts have 7 open complaints: 3 received and 4 under review." With none: "There are no open complaints in your cohorts." Nothing says or implies "waiting for you".

**Search (`q`).**
- It runs only within `visible_complaints(user)`.
- It matches the reference (case-insensitive contains, so "00042" finds "CMP-2026-00042"), the student's full name (case-insensitive contains) and the SAP ID (exact or prefix; see decision P3-3).
- Search text is limited to 100 characters.

**Filters.**
- **Cohort (`cohort`):** the advisor's own assignments only, in academic order (batch, then semester number, then section name). It defaults to **All assigned cohorts** (DEC-283).
  - The value encodes the exact three-part cohort; it is not a free-text or partial filter.
  - An unknown or non-assigned value is ignored, so the filter only ever narrows.
  - Show the cohort filter only if the advisor has more than one assignment.
- **Status (`status`):** All, Received, Under Review, Resolved or Rejected. It defaults to All; see decision P3-4 for an "Open" default.
- **Category (`category`):** categories that appear on the advisor's visible complaints, including inactive ones (so old complaints stay filterable).

**Sort (`sort`).** Latest activity (default) or newest submitted. Latest activity is `Max(events__created_at)`, as on My Submissions. Both orders are factual. There is no priority or age-based ordering (DEC-226).

**Rows** (design plan 5):
- the reference (monospace), title and **full student name** (never truncated; it wraps);
- the cohort chip (exact cohort at submission) and status pill;
- the last activity date;
- **factual flags** only (see decision P3-2):
  - "Cancellation requested", when such an event exists;
  - "Reopened by student", when a "Still not resolved" event exists.

The selected row is marked with `aria-current="true"` and the ink indicator, never the Forest tint (DEC-301).

**Pagination.** 20 per page. Filters persist.

**Empty states.**
- **No assignments:** "No cohorts are assigned to you yet." (the existing overview wording).
- **No complaints:** "There are no complaints in your cohorts."
- **No matches:** "No complaints match these filters." with a "Clear filters" link.

## 5. Centre pane: the selected case

- **Header.**
  - The reference and status pill.
  - The title as the one display-size moment.
  - Facts: student, cohort chip, category · subcategory, and submitted date and time.
  - The status journey (Received → Under Review → Resolved or Rejected), reusing `presentation.status_journey`.
- **Original description,** labelled "Student's original complaint", read-only. Reuse the `.sa-original` block.
- **History, newest first** (design plan 5), via a staff variant of the Part 2 timeline helper:
  - **Actors:** staff are shown by name and role (staff are internal to each other), and the student by name.
  - **Labels:**
    - Submitted;
    - Status changed to X, with "Resolution note", "Reason for rejection" or "Note";
    - Response from <name>;
    - Further information from the student;
    - Student marked as still not resolved (returned to Under Review);
    - Student asked to cancel.
  - **Hidden:** owner changes (O27, as on the student page).
- **Composer and status controls, at the end of the history** (design plan 5), as two clearly separated panels:
  1. **Respond.**
     - A textarea, "Response to the student", with a 5000-character limit.
     - A "Send response" button.
     - The helper text says it is visible to the student and does not change the status.
  2. **Update status.**
     - Radio buttons for the statuses allowed from the current one.
     - A note textarea whose label follows the choice: "Resolution note (required)", "Reason for rejection (required)" or "Note to the student (optional)" for Under Review.
     - An "Update status" button.
     - The helper text says the note is visible to the student. Without JavaScript, the label reads "Note (required for Resolved and Rejected)".
- **Laptop scrolling.** The centre pane scrolls independently, with the list and context panes alongside (section 7).
- **Empty state.** With no case selected (laptop only): "Choose a complaint from the list." It also shows a one-line reminder of the cohorts in view.

## 6. Right pane: the context panel

- **Student:**
  - full name and SAP ID;
  - email: see decision P3-1;
  - the cohort **at submission** (the complaint's stored cohort).
  - The student's current profile cohort is not shown if different (see decision P3-5).
- **Cohort:**
  - the exact batch + semester + section;
  - the Batch Advisors assigned to that exact cohort, by name (from `AdvisorAssignment`, including the current user, marked "You").
  - No responsible owner is shown (O27).
- **Not shown:**
  - the student's other complaints (DEC-305);
  - any data from outside the cohort;
  - the internal user ID.
- **Placement.** Below about 1360px wide, this panel becomes a compact strip under the case header (design plan 5). On phones, it sits below the case content.

## 7. Layout and responsive behaviour

| Width | Layout |
|---|---|
| ≥ 1360px | Rail 72px · list about 360px · case (flexible) · context about 300px. Each pane scrolls on its own within the viewport height (`height: 100dvh`, `overflow: auto`), so the composer stays reachable at 1280×590 without scrolling the whole page. |
| 992–1359px, including the **1280×590 reference laptop** (DEC-307) | Rail · list about 320–340px · case. The context becomes a compact strip under the case header. The case header, status and start of the history must be visible above the fold at 1280×590 and 1100×590. |
| 768–991px | Rail · list or case, one at a time: the URL selects it (as on phones), with more horizontal room. |
| < 768px, down to **360px** | Mobile header and drawer (existing staff shell). `/advisor/complaints/` shows the list; a selected case shows the case alone with "← Complaints" (keeping the filters) and the context below the content. A **sticky action bar** at the bottom offers "Respond" and "Update status", which jump to and open the matching panel. The composer stays at the end of the history and never floats over it. `interactive-widget=resizes-content` is already set in `base.html`. |

- **One template.** A modifier class on the workspace root (`sa-workspace--has-case`) lets CSS hide the list or the case below 992px. No duplicate templates or pages.
- **Filters on phones.** They collapse into a `<details>` "Filters" disclosure, so the list starts near the top.
- **Touch targets** are at least 44px on phones. There is no horizontal page scroll at 360px. Long names and references wrap.
- **Browser checks.** The same acceptance run as Parts 1–2: 1280×590, 1232×590, 1100×590, 1600×740, 1440×800 and 360px, each for the list, the selected case, a long history, the form errors and a closed complaint. The probe checks overflow, clipped and covered content, fonts, outside requests, touch targets and focus.

## 8. Accessibility

- **Landmarks and headings.**
  - The workspace is `<main>` with three labelled regions (`<section aria-labelledby>`): "Complaints", "Case" and "Context".
  - Headings: the page heading for the list (visually small), `h1` for the case title, and `h2` for History, Respond, Update status and Context.
  - The list is a `<ul>` of links. The selected row has `aria-current="true"`.
- **Forms.** They reuse `AccessibleErrorsMixin` and `includes/form_field.html`, so errors are linked with `aria-describedby`. The status choice is a `<fieldset>` with a `<legend>`, and the required-note state is announced through the label text.
- **Focus.**
  - After a validation error, focus moves to the error summary of the open panel.
  - After a successful action, the page loads with the message in the existing `role="status"` list.
  - The sticky phone action bar's buttons are real links to the panel IDs.
- **No colour-only meaning.** Status pills have text, and flags are text.

## 9. Concurrency between advisors sharing a cohort

The services lock the complaint row and validate the transition against the **current** status. If another advisor closes the complaint first, a stale "Under Review" choice is refused with a clear message, and the page reloads with the current state.

One gap remains: from Received, advisor A moves the complaint to Under Review while advisor B's open page still shows Received. B can then choose Rejected, which is a valid transition from Under Review too, and it goes through. That is acceptable under the current rules, because both transitions are allowed, but the history would show B acting on a state they had not seen. See decision P3-6 for an optional `expected_status` check.

## 10. Files and components likely to change

**New**
- `complaints/advisor_views.py` (or a section of `complaints/views.py`): the workspace, respond and status views, and the list-state helper.
- `complaints/advisor_forms.py` (or `complaints/forms.py`):
  - `AdvisorResponseForm (message)`;
  - `StatusUpdateForm (new_status, note)`, with its choices limited to `STAFF_TRANSITIONS[current]` and a `clean()` requiring the note for Resolved and Rejected (the service re-checks);
  - `ComplaintListFilterForm (q, cohort, status, category, sort)`, validating the cohort against the user's assignments.
- `templates/complaints/advisor/workspace.html`, plus partials `_list.html`, `_case.html`, `_context.html` and `_status_form.html`.
- `complaints/tests/test_advisor_workspace.py`.

**Changed**
- `complaints/urls.py` / `config/urls.py`: advisor routes.
- `complaints/presentation.py`: a staff timeline variant (newest first, names and roles) sharing code with `student_timeline`, and a factual-flags helper.
- `complaints/services.py`: **only if** decision P3-6 is accepted (an optional `expected_status` argument to `change_status`). Otherwise unchanged.
- `accounts/navigation.py`: Batch Advisor "Complaints" → `advisor_complaints`, with `also_current` for the case and action views.
- `templates/accounts/advisor_home.html`: optionally, each assigned-cohort card links to the workspace filtered to that exact cohort (a small, factual link).
- `static/css/app.css`: workspace grid and panes, the selected-row indicator, the compact context strip, the sticky phone action bar, and the filter disclosure. Existing tokens only.
- `static/js/complaints.js`: progressive enhancement only — the note label following the chosen status, the once-only submit (existing), and opening the panel targeted by the sticky bar.
- `docs/technical/COMPLAINTS.md` and `docs/DEVELOPMENT_LOG.md`.

**Unchanged:** models and migrations, permissions, the student pages, and the Part 1 business rules.

## 11. Tests (planned)

- **Access:**
  - Anonymous visitors are sent to sign-in.
  - Students and Super Admins get 403 on advisor routes. (The Super Admin version comes in Part 4.)
  - A deactivated advisor loses access.
  - An advisor with no assignments sees the empty state.
- **Exact cohort:**
  - The list shows only exactly assigned cohorts.
  - The same semester and section in another batch is excluded.
  - Partial-match advisors see nothing.
  - Advisors sharing a cohort see the same list.
  - Out-of-cohort references return the same 404 as unknown references, on GET and on both POST routes.
  - A non-assigned `cohort` filter value does not widen the list.
- **Search and filters:**
  - by reference, by name and by SAP ID;
  - search cannot reach other cohorts;
  - status, category and sort;
  - pagination preserving filters.
- **Respond:**
  - Creates a RESPONSE event and leaves the status unchanged.
  - An empty response gives a field error and HTTP 400.
  - The panel stays open after an error.
- **Update status:**
  - Only the allowed choices are offered for each current status.
  - Resolved without a note and Rejected without a reason give field errors.
  - Valid changes create events.
  - A closed complaint shows no status control, and a forged POST is refused with a message.
  - A concurrent close is refused with a message.
- **History and context:**
  - Newest first; staff names shown; owner changes hidden; cancellation and "Still not resolved" events shown.
  - The context lists the exact cohort's advisors and no other complaints of the student.
- **Navigation:** the advisor's "Complaints" item links to the workspace and stays current on the case views.
- **Invariants:**
  - No "Waiting for you" text or grouping.
  - No owner shown.
  - No approve or cancel controls.
- **Full suites:** MySQL (twice with `--keepdb`) and SQLite, `check`, `makemigrations --check --dry-run` and `migrate --check`, plus the browser acceptance run in section 7.

## 12. Decisions needed before or during implementation

| ID | Question | Recommendation |
|---|---|---|
| P3-1 | Show the student's **email** in the context panel? Advisors can already see student records; there are no email notifications (DEC-070), but advisors may need to contact a student. | Show name and SAP ID only in V1. Add email only if the owner confirms advisors should contact students outside the portal. |
| P3-2 | List **flags**: are "Cancellation requested" and "Reopened by student" acceptable as factual labels, given O33? | Yes. They state recorded facts and do not sort, group or claim that a response is needed. Do not add "New information" or "Unanswered" flags; those are O33 territory. |
| P3-3 | Search by **SAP ID** as well as reference and name? The design plan names reference and student name only. | Yes, exact or prefix match, because staff commonly identify students by SAP ID. Reviewer to confirm. |
| P3-4 | Default status filter: **All** or **Open** (Received + Under Review)? | All, with "Open" as an additional filter option. An "Open" default is reasonable, but it starts to resemble a queue (O33). |
| P3-5 | If a student's profile cohort changed after submitting, show the **current cohort** too? Access stays with the cohort at submission. | No. Show only the cohort at submission; a current cohort would reveal data about another cohort. |
| P3-6 | Add an optional **`expected_status`** argument to `services.change_status`, so a status change based on a stale page is refused atomically (section 9)? This is a concurrency safeguard, not a new business rule; without it, both transitions are already allowed. | Yes, as a small, tested service change. If not accepted, keep the current behaviour and rely on the history. |
| P3-7 | History order: the design plan says **newest first** for advisors, while the student page shows oldest first. | Follow the design plan (newest first) for advisors, and keep students oldest first. Reviewer to confirm the difference is intended. |
| P3-8 | Should the advisor overview's cohort cards link to the workspace filtered by cohort? | Yes. It is a small, factual navigation aid with no new figures. |

Product decisions that stay open and are **not** needed for Part 3: O27 (no owner is shown or assigned), O28 (requests are only displayed) and O33 (no queue). The workspace is designed so that each can be added later without restructuring: the owner in the context panel, request handling in the status panel, and a grouping in the list.
