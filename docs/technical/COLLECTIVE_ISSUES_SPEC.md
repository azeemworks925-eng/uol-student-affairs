# Collective Issues V1 — specification (CR/GR)

**Status:** Draft for review. **Not approved, not implemented.** Nothing in this document is a product decision until the owner approves it.
**Builds on:** `main` at `0df6dd4` (Complaints Parts 1–4, notifications, academic terms and Super Admin analytics merged).
**Governing decisions (already CONFIRMED):** DEC-016, DEC-040, DEC-205, DEC-210, DEC-212, DEC-240 to DEC-247, DEC-270, DEC-282, DEC-300 to DEC-304, DEC-307 in `docs/decisions/DECISIONS.md`.
**Open decisions:** section 12 (registered as O35 to O52 in `DECISIONS.md`). Section 13 lists conflicts between this task's brief and confirmed decisions.

Labels used below:
- **Confirmed (DEC-n):** an approved decision; it must be implemented as written.
- **Proposed:** this specification's recommendation; it needs approval.
- **Open (On):** a question with a recommended default; it needs an answer before the stage that depends on it.

---

## 1. Purpose and scope

A **collective issue** is a concern raised on behalf of a whole section by its Class Representative (CR) or Girls Representative (GR) (DEC-016, DEC-040). Students of that exact cohort can support it once (DEC-241). The cohort's Batch Advisors receive it, update its status and answer it privately to the representatives (DEC-243, DEC-244). The Super Admin has department-wide oversight (DEC-247).

**How it differs from the other two student workflows.** These differences are why this module is separate from the complaints code (section 4.1):

| | Individual complaint | Collective issue | Student Voice |
|---|---|---|---|
| Raised by | Any student, about themselves | Only the cohort's current CR or GR | Any student |
| Who sees it | The student, the cohort's BAs, Super Admin | Every student of the cohort, the cohort's BAs, Super Admin | The student, the relevant BA, Super Admin |
| Student interaction | Add information, "Still not resolved", cancellation request | **Support once**, never withdrawn | None |
| Staff answer visible to | The student | **The cohort's representatives only** | The student |
| Statuses | Received, Under Review, Resolved, Rejected | Received, Under Review, Resolved | Not specified |
| Editing after submission | Original kept; information added | **Locked**: no edit, no delete | — |

**In V1 (all Confirmed unless marked):**
- representative assignment management (DEC-245);
- raising an issue (DEC-040);
- the section noticeboard on the student Home (DEC-241, DEC-282, DEC-303);
- support (DEC-241);
- the Batch Advisor workspace with status and private response (DEC-243, DEC-244);
- Super Admin oversight (DEC-247);
- the DEC-270 notification "new CR/GR issue in the student's section".

**Not in V1:** section 11.

## 2. Confirmed requirements (from DECISIONS.md and the approved brief)

1. **Representatives are permissions, not accounts:** CR and GR are permissions on existing student accounts. There is no new role, account type or login (DEC-016). `User.role` is unchanged.
2. **Exactly one of each per cohort:** every section has exactly one CR and one GR (DEC-016). "Section" means the exact batch + semester + section cohort (DEC-205).
3. **Identical and limited:** CR and GR have identical permissions and keep their normal student permissions. A student holds at most one representative assignment, for one section (DEC-240).
4. **Who appoints them:** Batch Advisors assign and replace the CR and GR of their assigned cohorts; the Super Admin can also manage them (DEC-245).
5. **Raising:** either representative can independently raise a collective issue for their own section (DEC-040).
6. **Supporting** (DEC-241):
   - the issue appears on the home page of students in that section;
   - a student can support it once, and support can't be withdrawn or changed;
   - CR/GR can support their own issue;
   - there are no student comments.
7. **Locked once published:** published issues can't be edited or deleted by CR/GR in V1 (DEC-242). The brief strengthens this: no editing or deletion by anyone, and the original record is preserved.
8. **The private response** (DEC-243):
   - the BA receives the issue and responds privately to the CR/GR; other students can't see the response;
   - after the advisor responds, the issue disappears from student home pages;
   - the CR/GR keep the issue and the private response in their dashboard;
   - the record and the support count are preserved.
9. **Statuses** (DEC-244): Received, Under Review and Resolved. The BA updates the status and provides a short official response. A resolution note is mandatory and private to the CR/GR.
10. **CR/GR limits:** they can't see individual complaints, private Student Voice submissions or other students' meeting details (DEC-246).
11. **Oversight:** the Super Admin has department-wide oversight of collective issues (DEC-247).
12. **Notification:** a new CR/GR issue in the student's section is a notification event, linking to the record (DEC-270).
13. **Student Home** (DEC-282, DEC-303):
    - "Section Updates" shows active CR/GR issues awaiting student support;
    - before supporting, the page shows "Support can't be withdrawn." and the button "Support this issue"; afterwards, "You support this";
    - representatives are shown by name and role only;
    - collective issues are not part of the personal summary.
14. **Deactivation:** deactivating a student revokes their representative permissions and preserves history (DEC-212).
15. **Academic structure:** it is dynamic. Deactivated entries keep their historical records (DEC-020, DEC-210). Nothing assumes particular section names.
16. **Support integrity:** support uniqueness is enforced by the database. Other cohorts have no visibility or interaction. A Resolved status needs a resolution note (brief items 6, 8 and 11).

## 3. Roles and permission matrix

"Cohort" means the issue's cohort. "Current rep" means a student with an **active** representative assignment for that cohort who passes the authority check in section 5.3.

| Action | Student of the cohort | Current CR/GR of the cohort | Student of another cohort | BA assigned to the cohort | BA of other cohorts | Super Admin |
|---|---|---|---|---|---|---|
| See the cohort's noticeboard and open issue details | Yes | Yes | **No (404)** | Yes | No (404) | Yes |
| Support an issue | Yes, once, while open for support (O38) | Yes, once | No | No | No | No |
| See support count | Yes | Yes | No | Yes | No | Yes |
| See who supported | **No** (O40) | No | No | No (O40) | No | No (O40) |
| Raise an issue | No | **Yes**, for their own cohort only | No | No | No | No |
| Edit or delete a published issue | No | No | No | No | No | **No** (DEC-242, brief item 10) |
| See status | O39 | Yes | No | Yes | No | Yes |
| See the official response and resolution note | **No** (DEC-243) | Yes (O37) | No | Yes | No | Yes |
| Change status and respond | No | No | No | **Yes** | No | O44 (default: no) |
| Assign or replace the cohort's CR/GR | No | No | No | **Yes** (DEC-245) | No | **Yes** (DEC-245) |

**Every row is enforced on the server.** Querysets start from a permission-scoped function (section 7.1), and every action is re-checked in the service layer.

## 4. Architecture

### 4.1 Placement
- **A new Django app, `collective_issues`.** It holds the issue, support and event models, services, permissions, views, URLs and templates. The workflow differs from complaints in visibility, interaction, statuses and privacy of the response (section 1). It **reuses patterns, not code paths**:
  - append-only events;
  - `transaction.atomic` services with row locks;
  - permission-scoped querysets with 404 for anything out of scope;
  - POST/Redirect/GET;
  - `AccessibleErrorsMixin`;
  - the shared workspace layout CSS.
- **Representative assignments live in `accounts`.** They are a permission on a student account (DEC-016), they are managed with other account data, and the deactivation and cohort-change hooks are in `accounts` (section 5.4).
- **No change to `complaints`,** except that no code is shared through it.
- **No new dependency.**

### 4.2 Data model (Proposed)

All cohort references are `ForeignKey(..., on_delete=PROTECT)` to `academics.Batch`, `Semester` and `Section` (DEC-210).

**`accounts.RepresentativeAssignment`.** History is kept: an assignment is ended, never deleted.

| Field | Notes |
|---|---|
| `student` | FK `User` (PROTECT). The role must be student (model `clean()` and service). |
| `batch`, `semester`, `section` | The exact cohort the student represents |
| `kind` | `cr` or `gr` |
| `is_active` | `TRUE` while in force, `NULL` once ended (never `FALSE`; see constraints) |
| `assigned_by`, `assigned_at` | Who appointed the student, and when |
| `ended_by` (nullable), `ended_at` (nullable), `end_reason` (nullable) | `end_reason` is one of `replaced`, `removed`, `student_deactivated`, `cohort_changed` |

**Database constraints:**
- `UNIQUE (batch, semester, section, kind, is_active)`: at most one active CR and one active GR per cohort.
- `UNIQUE (student, is_active)`: at most one active assignment per student (DEC-240).
- `CHECK (is_active IS NULL OR is_active IN (TRUE))`.
- `CHECK ((is_active IS NULL) = (ended_at IS NOT NULL))`.

MySQL ignores conditional unique constraints, so they are not used; this is the same nullable-marker technique `academics.AcademicTerm` uses (ACADEMIC_TERMS.md section 1).

**`collective_issues.CollectiveIssue`.** Write-once content.

| Field | Notes |
|---|---|
| `reference` | Unique, for example `CI-2026-00042`, generated like complaint references (O47) |
| `batch`, `semester`, `section` | The cohort, copied from the raiser's assignment at publication; never changes |
| `raised_by` | FK `User` (PROTECT); kept even if they stop being a representative or are deactivated |
| `raised_as` | `cr` or `gr` at publication (historical label) |
| `title` | `CharField(120)` |
| `description` | `TextField`, at most 2,000 characters (section 6) |
| `status` | `received`, `under_review` or `resolved`, with a check constraint |
| `first_response_at` | Nullable. Set once, by the first official response or the resolution (O36); it closes the issue on the noticeboard |
| `created_at`, `updated_at` | |

**`collective_issues.Support`:** `issue` (FK, PROTECT), `student` (FK `User`, PROTECT) and `created_at`, with `UNIQUE (issue, student)`. **Insert-only.** Rows can't be deleted or updated (DEC-241: no withdrawal).

**`collective_issues.IssueEvent`.** Append-only history.

| Field | Notes |
|---|---|
| `issue` | FK |
| `kind` | `raised`, `status_changed` or `response` |
| `actor` | FK `User`, nullable for system events |
| `from_status`, `to_status` | Status-change events only |
| `message` | The response or resolution note |
| `created_at` | |

Check constraints:
- a `status_changed` event to `resolved` must have a non-empty `message` (the resolution note);
- a `response` event must have a non-empty `message`;
- `raised` events have no message.

**Write protection.** It follows the complaint models:
- a protected queryset refuses `update()`, `bulk_update`, `delete()` and upserts;
- instance `save()` refuses changes to write-once fields (title, description, cohort, raiser, `raised_as`);
- status and `first_response_at` are changed only by services, under a row lock;
- `Support` and `IssueEvent` are insert-only;
- raw SQL is outside what the ORM can protect.

**Indexes:**
- `CollectiveIssue (batch, semester, section, status)`;
- `CollectiveIssue (batch, semester, section, -created_at)`;
- `Support (issue)` (covered by the unique index).

**Migrations:** `accounts/000N_representativeassignment` (additive) and `collective_issues/0001_initial` (additive). Neither changes existing data.

## 5. Representative assignments

### 5.1 Who manages them (DEC-245)
- **A Batch Advisor:** for each **exact** cohort they are assigned to (DEC-205), on a portal page (section 9.2, "Representatives").
- **The Super Admin:** for any cohort, on the "CR/GR Management" page (section 9.3).
- **Never:** students, BAs of other cohorts and inactive users.

### 5.2 Rules (services, under row locks)
- **Assign:** the student must be:
  - an active user with the student role and a student profile;
  - currently in that **exact** cohort;
  - free of any other active assignment (DEC-240).
- **Replace:** assigning a new CR (or GR) to a cohort that has one ends the old assignment (`replaced`) and creates the new one, in one transaction. The service locks the cohort's active assignment rows (`SELECT … FOR UPDATE`, in a fixed order) and the student's own. The two unique indexes are the final safeguard; an `IntegrityError` becomes a form error, never a 500.
- **Remove:** ends the assignment (`removed`) and leaves the post vacant. Vacancies are allowed (O35), because the system can't create a representative where none has been chosen.
- **Moving one student between posts:** the same student can't be CR and GR at once, or represent two cohorts. To move a student from CR to GR, end the first assignment.

### 5.3 Authority check (defence in depth)
A student acts as a representative only if all of these hold:
- the student is active;
- they have an active assignment;
- the assignment's cohort **equals their current profile cohort**.

This check runs on every representative action. So even if a hook in section 5.4 were missed (for example, a change made in the shell), a moved or deactivated student has no representative power.

### 5.4 Lifecycle hooks (DEC-212; DEC-021 manual promotion)
- **Deactivated student:** `UserAdmin.save_model` (or the service it calls) ends the assignment with reason `student_deactivated`, in the same transaction (DEC-212). Reactivating the student does **not** restore it.
- **Changed cohort:** when the Super Admin changes a student's batch, semester or section (`StudentProfileAdmin.save_model` → `record_profile_changes`), any active assignment ends with reason `cohort_changed`. Every semester promotion therefore leaves the posts vacant until a BA or the Super Admin appoints again (O35 and O46).
- **Deactivated academic entries:** existing issues, support and history keep their references. No new assignment or issue is created for a cohort containing an inactive batch, semester or section (O45).
- **History:** ended assignments remain as history. Issues keep `raised_by` and `raised_as` (brief A).

### 5.5 Proposed UI behaviour
Each cohort card shows its two posts: CR and GR, each with a name or "Vacant".
- **Assign:** a select listing only the eligible students of that exact cohort, by name and SAP ID.
- **Ending a post:** "Replace" and "Remove" actions. Removal is confirmed before it takes effect.
- **History:** a collapsible list of past assignments.

## 6. Raising an issue (DEC-040, DEC-242)

**Who:** the cohort's current CR or GR (section 5.3). The issue's cohort is always taken from the assignment and never from request data.

**Fields:**

| Field | Required | Rule |
|---|---|---|
| Title | Yes | 5–120 characters after trimming. Shown on the noticeboard and in notifications. |
| Description | Yes | 20–2,000 characters. Plain text with line breaks; no HTML or Markdown rendering. |
| Category | — | **None in V1** (O42). Complaint categories describe individual problems and are managed for complaints (DEC-220); reusing them would couple two workflows. |

The minimum lengths prevent accidental empty or one-word issues. Limits are enforced by the form, the service and the database.

**Publication** (O41). There are no drafts. Submitting shows a **review step**:
- the exact title and description;
- the statement "Once published, this issue can't be edited or removed. Every student in <cohort> will see it and can support it.";
- a required confirmation checkbox and a "Publish issue" button (the one Forest primary on the page).

The review step re-posts the same fields and keeps no server-side draft. Publishing creates the issue, sets status `received` and records a `raised` event in one transaction. It then queues the DEC-270 notifications after commit (section 10) and redirects to the issue (PRG). The submit button is disabled after the first click.

**Duplicates** (O43). Nothing is blocked; separate issues may be similar. The form shows the cohort's issues that are still open for support (reference and title) as a non-blocking notice: "Your section already has these open issues. Supporting one may be better than raising another." This mirrors DEC-225's spirit for complaints. A per-representative rate limit is not proposed (O48).

**Locked after publication.** There is no edit or delete route for anyone. The issue page says: "Published issues are locked: they can't be edited or removed." Corrections are made by raising a new issue.

## 7. Student experience

### 7.1 Visibility
- `visible_issues(user)` is the only entry point for queries:
  - **student:** issues whose cohort equals their **current** profile cohort;
  - **BA:** `assigned_cohort_filter`;
  - **Super Admin:** everything;
  - **anyone else, or an inactive user:** none.
- `get_visible_issue(user, reference)` returns 404 for an unknown reference and for one out of scope alike.
- A student who moves cohort no longer sees the old cohort's issues. Their support records remain and still count (DEC-243: support count preserved).

### 7.2 Section noticeboard (Home, DEC-282 "Section Updates", DEC-303)
- **What it lists:** the cohort's issues that are **open for support** (no official response yet; O36), newest first. Each card shows the title, a description excerpt, the raiser's name and role ("Ayesha Khan · CR"; DEC-303), the date and the support count.
- **Support:** "Support can't be withdrawn." appears before the button "Support this issue" (a POST). Afterwards, "You support this" is shown, with no undo.
- **Empty state:** "No open issues in your section." It explains that the CR or GR raises issues for the cohort (the existing text).
- **Excluded:** collective issues are not part of the personal summary (DEC-303).

### 7.3 Issue page, for every student of the cohort (`/student/section-issues/<reference>/`)
- **Contents:** title, description, raised by (name and role), date, support count, and the support action while open.
- **Locked notice:** "Published issues are locked: they can't be edited or removed."
- **After the first response,** the support action is replaced by "Support is closed: your representatives have received a response." (O38). The status and the response are **not** shown to non-representatives (DEC-243; O39).

### 7.4 Section issues list (`/student/section-issues/`)
All of the cohort's issues, newest first:
- open ones with their support state;
- closed ones marked "Support closed".

It is reached from the Home noticeboard ("All section issues"). No fifth phone destination is added (DEC-304; O46 for representatives).

### 7.5 Representative view (current CR/GR of the cohort)
- **On the Home noticeboard:** a "Raise an issue" action.
- **On the list and issue pages:** each issue's status and the private history, which includes the official responses and the resolution note.
  - This covers **every** issue of the cohort, including those raised by the other representative or by a predecessor (O37).
  - The private parts carry a clear label: "Visible to your section's CR and GR only."

### 7.6 States and feedback
- **Messages:**
  - "Your support has been recorded.";
  - "You already support this issue." for a repeat POST, idempotent with no error page;
  - "Support is closed for this issue." for a POST after closure.
- **Validation errors:** linked to their fields, as on the complaint form.
- **Out of scope:** forged references or cohorts give the same 404.
- **Empty states:** every list has one.
- **Loading:** pages are server-rendered with no client-side loading states. Buttons disable after the first click.

## 8. Batch Advisor workspace

The page lives at `/advisor/collective-issues/` and uses the same split-pane layout as the complaints workspace (DEC-302), with separate views and templates.
- **List:**
  - issues of the advisor's **exact** cohorts only;
  - the cohort filter defaults to all assigned cohorts (DEC-283);
  - a status filter;
  - search by reference or title;
  - rows show the reference, status, title, cohort, raiser (name and role), support count and date.
- **Issue:**
  - the full content and the support count (no supporter identities; O40);
  - the history, newest first;
  - two separate panels, as for complaints (DEC-305).
- **Respond** (DEC-243, DEC-244):
  - a short official response of up to 1,000 characters, private to the cohort's representatives;
  - it records a `response` event, and the first one sets `first_response_at`.
- **Update status:**

  | From | To | Requirement |
  |---|---|---|
  | Received | Under Review | — |
  | Received | Resolved | Resolution note (mandatory; DEC-244) |
  | Under Review | Resolved | Resolution note (mandatory) |
  | Resolved | — | None. Resolved is final in V1; **no reopening** (O49) |

  Every change sends an `expected_status` stale-page guard, as in complaints (P3-6). The service locks the row and refuses stale changes. A resolution note is also an official response: it sets `first_response_at` if that is still unset.
- **No Rejected status** (DEC-244 lists three statuses).
- **No delete or edit actions.**
- **All BAs of the cohort** see and can act on its issues (O27 default; section 12). There is no owner designation for collective issues.

## 9. Super Admin oversight (DEC-247)

### 9.1 Collective issues
`/super-admin/collective-issues/` is a department-wide list and issue view, read-only by default (O44).
- **Filters:** cohort, status, current academic term (reusing `term_window()`), and search.
- **Issue view:** content, support count and the full history, including private responses (oversight).
- **No editing or deletion** (immutability).
- **No moderation or hiding action in V1** (O50).

### 9.2 Representatives (Batch Advisor)
`/advisor/representatives/` shows the advisor's assigned cohorts and their CR/GR posts (section 5.5).

### 9.3 CR/GR Management (Super Admin)
`/super-admin/representatives/` covers every cohort, with filters for batch, semester, section and vacancies. It uses the same actions and history as section 5.5.

All three destinations already exist in the navigation as unavailable entries ("Collective Issues", "Representatives", "CR/GR Management"; `accounts/navigation.py`). Implementation enables them.

## 10. Notifications

- **Confirmed** (DEC-270): "New CR/GR issue in your section".
  - **Recipients:** every **active** student whose current profile cohort is the issue's cohort, **except the raiser**.
  - **Content:** title "New issue in your section: <title>" (truncated); destination: the issue page.
  - **Delivery:** created after the publishing transaction commits, through `notifications.services.notify` (one row per recipient; the existing unique constraint per recipient and source prevents duplicates).
  - **Scale:** for one section, a single post-commit loop is enough; a bulk helper may be added to `notifications.services` if it measurably helps.
- **Proposed, needs approval** (O51): "Response to your section's issue". It would go to the cohort's **current** CR and GR when a BA records a response or resolves an issue. Reason: the issue leaves the noticeboard after a response (DEC-243), and the response is private, so the representatives otherwise have no prompt to look. DEC-270's list doesn't include this event; the default is **not** to add it unless approved.
- **Not proposed:**
  - notifications to BAs or the Super Admin for new issues or support (the workspaces show them, consistent with complaints);
  - notifications for each support;
  - notifications for assignment changes.

## 11. Explicit exclusions (V1)

- Comments, discussion or chat (DEC-241, DEC-052).
- Editing or deleting a published issue by anyone; drafts stored on the server.
- Withdrawing or changing support (DEC-241). The brief asked "if removal is appropriate"; it isn't.
- Showing supporter identities.
- Visibility for, or interaction from, other cohorts.
- Attachments (DEC-080).
- Categories (O42).
- Rejected status or reopening (O49).
- Anonymous issues.
- Email or external notifications (DEC-070).
- Analytics for collective issues: not in DEC-281.
- Showing the official response to non-representatives (DEC-243).
- Automatic semester promotion of representatives (DEC-021).
- Changes to complaint behaviour.

## 12. Open decisions

Each is registered in `DECISIONS.md` section 5.2. For each, the recommended default is given; none is assumed approved.

| ID | Question | Impact | Recommended default |
|---|---|---|---|
| O27 (existing) | Which BA handles a cohort's collective issues when several are assigned? | Routing and responsibility | **All BAs of the exact cohort** see and act on its issues, with no owner designation. This matches DEC-310's principle that all of a cohort's advisors keep their rights. |
| O35 | DEC-016 says "exactly one CR and one GR". May a post be vacant? | Every promotion and every removal | **Yes.** The database enforces *at most* one per post; vacancies are shown as "Vacant" and can only be filled by a person. |
| O36 | What closes an issue for support and takes it off home pages ("after the advisor responds", DEC-243)? | Noticeboard, support window | **The first official response or the resolution note,** whichever comes first. A status change to Under Review alone does not close it. |
| O37 | Do the CR and GR of a cohort see each other's issues and responses, and those raised by a predecessor? Does a former representative keep access? | Privacy of responses | **The current CR and GR see all of the cohort's issues and responses.** Access follows the *current* assignment; a former representative becomes a normal student again. |
| O38 | Can students support after the issue is closed for support? | Support counts | **No.** Support is accepted only while the issue is open for support; the count then stays frozen. |
| O39 | Do non-representative students see the issue's status (Received, Under Review or Resolved)? | Transparency versus DEC-243's privacy | **No.** Students see only "Open for support" or "Support closed". Status, response and note are for the representatives, the cohort's BAs and the Super Admin. |
| O40 | Who may see *who* supported an issue? | Student privacy | **Nobody in the interface.** Counts only, for everyone. Support rows exist for integrity and are visible to database administrators only. |
| O41 | Drafts or immediate publication? | Raising experience | **No stored drafts.** A review step with a required confirmation of the lock, then immediate publication. |
| O42 | Categories for collective issues? | Form, filters | **None in V1.** Title and description only. |
| O43 | Duplicate handling | Noise on the noticeboard | **A non-blocking notice** listing the cohort's open issues; never block. |
| O44 | May the Super Admin respond or change status, as for complaints (DEC-228)? | Oversight scope | **Read-only in V1.** DEC-247 grants oversight; DEC-228's power to act is complaint-specific. |
| O45 | May issues or assignments be created for a cohort containing an inactive batch, semester or section? | Historical cohorts | **No new assignments or issues.** Existing records remain readable. |
| O46 | Where do representatives find their raise and private views, given DEC-304's four phone destinations? | Navigation | **Inside Home** (noticeboard actions) and the section issues pages reached from it. No new destination. |
| O47 | Reference format | Support and oversight | **`CI-<year>-<5 digits>`,** like complaints. |
| O48 | A limit on how many issues a representative can raise | Spam versus legitimate use | **None in V1;** revisit if misuse appears. |
| O49 | Reopening a Resolved issue, or a Rejected status | Workflow | **Neither in V1** (DEC-244 lists three statuses; DEC-242 locks content). |
| O50 | Moderation of abusive or wrong content, given that nobody can edit or delete | Safety; immutability | **No moderation action in V1.** Record it as a risk. If the owner wants one, it should be a Super Admin "withdraw from view" flag that keeps the record, which is a new decision. |
| O51 | Notify the current CR/GR when a BA responds or resolves? | Representatives learning of private responses | **Yes, if approved;** otherwise not implemented (section 10). |
| O52 | "GR" meaning (section 13) | Labels throughout the interface | **Keep DEC-016: Girls Representative.** The interface shows "CR" and "GR" with that expansion in help text. No gender data is recorded or checked; appointing the GR is an administrative judgement. |

## 13. Conflicts between the brief and confirmed decisions

These are reported, not resolved. The specification follows the confirmed decisions until the owner decides otherwise.
1. **"General Representative" vs DEC-016 "Girls Representative".** The brief's title uses "General Representative" (O52).
2. **Who assigns representatives.** The brief asks how the *Super Admin* assigns CR/GR. DEC-245 also gives this to **Batch Advisors** for their assigned cohorts, and this specification includes both.
3. **Support removal.** The brief asks about "Support and remove-support behaviour, if removal is appropriate". DEC-241 forbids withdrawal, so there is none.
4. **Deletion "by CR/GR" vs by anyone.** DEC-242 forbids editing and deletion *by CR/GR*; the brief extends it to "permanently locked". This specification applies it to everyone (no edit or delete route exists). This is consistent with, and stricter than, DEC-242.

## 14. Security and integrity

- **Exact cohort isolation:**
  - every query starts from `visible_issues(user)`;
  - every action re-checks scope in its service;
  - a cohort is never accepted from request data: issue creation uses the assignment, and filters only narrow the scoped set (forged cohort values are ignored, as in the complaint workspaces).
- **IDOR:** references are looked up only within the visible set, so an unknown reference and one out of scope give the same 404.
- **Methods:** state changes are POST with CSRF; GET never changes data. Every page requires login, and inactive users are signed out by the existing backend.
- **Concurrency:**
  - **Support:** inserted in a savepoint and caught on the `UNIQUE (issue, student)` violation, so a double click or two tabs record one row and report "already supported".
  - **Status and response:** they lock the issue row and use `expected_status`.
  - **Assignments:** they lock the affected rows, in a fixed order.
  - **Tests:** MySQL concurrency tests use separate connections, as for academic terms.
- **Immutability:**
  - protected querysets and instance guards on write-once fields;
  - insert-only `Support` and `IssueEvent`;
  - no delete permission in any admin;
  - `PROTECT` foreign keys throughout.
- **Lifecycle:** the authority check (section 5.3) and the hooks (section 5.4). Deactivated academic entries keep their history.
- **Privacy:**
  - responses and resolution notes never appear in student pages or student notifications;
  - supporter identities never appear;
  - CR/GR gain no access to complaints, Student Voice or meetings (DEC-246).

## 15. Test strategy

- **Models and migrations:**
  - each constraint verified with raw SQL on MySQL and SQLite: one active CR/GR per cohort, one active assignment per student, unique support, the resolution-note check;
  - protected querysets;
  - migrations reverse and re-apply.
- **Services:**
  - assign, replace and remove, with every eligibility rule;
  - the deactivation and cohort-change hooks;
  - the authority check when a hook is bypassed;
  - raising: the cohort comes from the assignment, validation, the lock;
  - support: once, closed after the first response, idempotent repeats;
  - status transitions: the note is required, stale changes are refused, Resolved is final.
- **Permissions:** the full matrix of section 3, for every route. Includes forged references, forged cohort filters and IDOR attempts, other cohorts, other BAs, inactive users and former representatives.
- **Concurrency (MySQL only, separate connections):**
  - simultaneous support by one student;
  - simultaneous replacement of the same post;
  - status change against response.
- **Notifications:** one per eligible student; not to the raiser, other cohorts or inactive students; none if the transaction rolls back; O51 tests only if approved.
- **Privacy:** response text, resolution notes and supporter identities are absent from every student page, the student response context and student notifications.
- **Frontend:**
  - every page and state at 1280×590, 1232×590, 1100×590, 1600×740, 1440×800 and 360px (DEC-307);
  - keyboard focus and 44px touch targets;
  - long titles and names;
  - empty and error states.
- **Regression:** complaints, analytics and existing navigation are unchanged.

## 16. Implementation plan (PR-sized stages)

1. **Stage CI-1: representative assignments.**
   - **Contents:** the `accounts.RepresentativeAssignment` model, its migration, services, the authority check, the deactivation and cohort-change hooks, and the BA "Representatives" and Super Admin "CR/GR Management" pages.
   - **Needs:** O35, O45, O52.
   - **Independently useful:** representatives are recorded before issues exist.
2. **Stage CI-2: raising, the noticeboard and support.**
   - **Contents:** the `collective_issues` app with models, the migration, `visible_issues`, the raise flow with review step, the Home noticeboard, the section issues list and issue pages, support, and the DEC-270 notification.
   - **Needs:** CI-1, plus O36 to O43, O46 and O47.
3. **Stage CI-3: Batch Advisor workspace and Super Admin oversight.**
   - **Contents:** respond, status with resolution note, the representatives' private views, the Super Admin read-only oversight, and O51 if approved.
   - **Needs:** CI-2, plus O27, O44, O49, O50 and O51.
4. **Stage CI-4: acceptance and documentation.** Full regression on both databases, browser acceptance and technical notes.

Each stage adds only additive migrations and changes no existing data. Complaint behaviour is untouched throughout.

## 17. Proposed decision entries (for DECISIONS.md, after approval)

**Not approved.** If the owner approves this specification, these become CONFIRMED entries with new DEC numbers. Until then they are tracked as the open items above.
- **Placement:** representative assignments are history-keeping records in `accounts`. At most one active CR and one active GR per cohort and one active assignment per student, enforced by the database. Vacancies are allowed. An assignment ends automatically when the student is deactivated or changes cohort (O35, O45).
- **Visibility:** collective issues are visible to the issue's exact cohort, its BAs and the Super Admin. Students see title, description, raiser (name and role), date, support count and the support state; status, responses and notes are for representatives, BAs and the Super Admin (O37, O39).
- **Support:** support is accepted while an issue is open for support, until the first official response or resolution note (O36, O38). Counts only; supporter identities are never shown (O40).
- **Raising:** a review step with a required lock confirmation, no stored drafts, no categories, and a non-blocking duplicate notice (O41 to O43).
- **Statuses:** Received → Under Review → Resolved, or Received → Resolved. A resolution note is required, and Resolved is final (O49).
- **Super Admin:** read-only oversight in V1 (O44).
