# Complaints — technical notes

**Status:** Part 1 (backend) merged in PR #7. Part 2 (student pages) on branch `feat/student-complaints-frontend`. Parts 3–4 (Batch Advisor and Super Admin screens, category management, notifications and analytics) are not built.
**Decisions:** DEC-030, DEC-031, DEC-220 to DEC-230 in `docs/decisions/DECISIONS.md`. Open: O27, O28, O33.

## 1. Backend (`complaints/`)

| Module | Responsibility |
|---|---|
| `models.py` | `ComplaintCategory`, `ComplaintSubcategory`, `Complaint`, `ComplaintEvent`. The cohort (batch + semester + section) is stored at submission. History is insert-only. Bulk updates and deletes are refused (`ProtectedQuerySet`). |
| `services.py` | Every state change: `submit_complaint`, `change_status`, `respond`, `mark_still_not_resolved`, `add_further_information`, `request_cancellation`, `assign_responsible`, plus the `possible_duplicates` helper. Each runs in a transaction, checks permission and records an event. |
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

## 3. Known limitations

- **O27, O28, O33 are open.** No responsible owner is assigned automatically and the owner is not shown to students. A cancellation request is recorded only. No event is classified as needing a response.
- **Cancellation display.** Offering cancellation only for open complaints, and only once, is a presentation choice; the service itself accepts a request in any state.
- **Student home.** "Your latest updates" (DEC-282, DEC-303) does not yet list complaint activity: it needs seen/unseen tracking, which is not built.
- **Double submission.** This is prevented in the browser and by Post/Redirect/Get, not by a server-side token. Duplicates are allowed by DEC-225 in any case.
- **Theme.** Only Forest Light is implemented (Forest Dark is approved but not built; O34 open).
