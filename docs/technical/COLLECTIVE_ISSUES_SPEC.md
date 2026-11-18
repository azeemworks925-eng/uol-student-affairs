# Collective Issues V1 — specification (CR/GR)

**Status:** Product decisions approved on 2026-11-18 (DEC-323 to DEC-325). **Stage CI-1 (cohort representation, section 16) is implemented on branch `feat/collective-issues-ci-1-representation`, awaiting review; CI-2 to CI-4 are not implemented.** The technical design remains a specification for implementation and review. Product requirements are authoritative as recorded in `DECISIONS.md`.
**Builds on:** `main` at `0df6dd4` (Complaints Parts 1–4, notifications, academic terms and Super Admin analytics merged).
**Governing decisions (already CONFIRMED):** DEC-016, DEC-040, DEC-205, DEC-210, DEC-212, DEC-240 to DEC-247, DEC-270, DEC-282, DEC-300 to DEC-304, DEC-307, **DEC-323** (CR/GR representation lifecycle), **DEC-324** (Collective Issues V1 product rules) and **DEC-325** (representative response notifications) in `docs/decisions/DECISIONS.md`.
**Decision traceability:** section 12 records the remaining O27 scope and the resolution of O35, O36–O55. The collective-issue portion of O27 is resolved by DEC-324; O27 remains open for Student Voice and meeting requests. Section 13 records brief differences already settled by confirmed decisions.

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
| Editing after submission | Original kept; information added | **Locked**: no edit or delete by anyone (DEC-242, DEC-324) | — |

**In V1 (product requirements confirmed):**
- management of each cohort's CR and GR, with no vacancies (DEC-016, DEC-245; section 5);
- raising an issue (DEC-040);
- the section noticeboard on the student Home (DEC-241, DEC-282, DEC-303);
- support (DEC-241);
- the Batch Advisor workspace with status and private response (DEC-243, DEC-244);
- Super Admin oversight (DEC-247);
- the DEC-270 notification "new CR/GR issue in the student's section".

**Not in V1:** section 11.

## 2. Confirmed requirements (from DECISIONS.md and the approved brief)

1. **Representatives are permissions, not accounts:** CR and GR are permissions on existing student accounts. There is no new role, account type or login (DEC-016). `User.role` is unchanged.
2. **Exactly one of each per cohort:** every section has exactly one CR and one GR (DEC-016). "Section" means the exact batch + semester + section cohort (DEC-205). **DEC-323** sets how this applies:
   - a represented cohort that remains eligible (active, with at least two active students) can never have a vacant post;
   - a cohort awaiting its first appointment, or whose representation was closed after falling below two active students, is the only permitted state without representatives ("Awaiting representatives").
3. **Identical and limited:** CR and GR have identical permissions and keep their normal student permissions. A student holds at most one representative post, for one section (DEC-240).
4. **Who appoints them:** Batch Advisors assign and replace the CR and GR of their assigned cohorts; the Super Admin can also manage them (DEC-245).
5. **Raising:** either representative can independently raise a collective issue for their own section (DEC-040).
6. **Supporting** (DEC-241):
   - the issue appears on the home page of students in that section;
   - a student can support it once, and support can't be withdrawn or changed;
   - CR/GR can support their own issue;
   - there are no student comments.
7. **Locked once published:** published issues can't be edited or deleted by CR/GR in V1 (DEC-242). The brief adds "no editing or updating" and "the original published record is preserved", and repeats "no deletion by CR/GR". Staff edit or delete is prohibited in V1 as well (DEC-324).
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
14. **Deactivation:** deactivating a student revokes their representative permissions and preserves history (DEC-212). Under DEC-016 this may not leave a post vacant: a replacement is appointed in the same transaction, or the deactivation is refused (section 5.4).
15. **Academic structure:** it is dynamic. Deactivated entries keep their historical records (DEC-020, DEC-210). Nothing assumes particular section names.
16. **Support integrity:** support uniqueness is enforced by the database. Other cohorts have no visibility or interaction. A Resolved status needs a resolution note (brief items 6, 8 and 11).

## 3. Roles and permission matrix

"Cohort" means the issue's cohort. "Current rep" means a student who passes the `current_representative` check (section 5.3). Rows that start something new also need `can_act_as_representative`, which adds that the cohort is active.

| Action | Student of the cohort | Current CR/GR of the cohort | Student of another cohort | BA assigned to the cohort | BA of other cohorts | Super Admin |
|---|---|---|---|---|---|---|
| See the cohort's noticeboard and open issue details | Yes | Yes | **No (404)** | Yes | No (404) | Yes |
| Support an issue | Yes, once, while open for support (O38) | Yes, once | No | No | No | No |
| See support count | Yes | Yes | No | Yes | No | Yes |
| See who supported | **No** (O40) | No | No | No (O40) | No | No (O40) |
| Raise an issue | No | **Yes**, for their own cohort only | No | No | No | No |
| Edit or delete a published issue | No | No (DEC-242) | No | No (DEC-324) | No | No (DEC-324) |
| See status | Only support state | Yes | No | Yes | No | Yes |
| See the official response and resolution note | **No** (DEC-243) | Yes (O37) | No | Yes | No | Yes |
| Change status and respond | No | No | No | **Yes** | No | No (DEC-324) |
| Appoint the cohort's CR and GR (both together), or replace one or both | No | No | No | **Yes** (DEC-245) | No | **Yes** (DEC-245) |

**Inactive cohorts.** In a cohort whose batch, semester or section is inactive, the rows that start something new (raise, support, appoint or replace representatives) are refused; viewing follows the rows above. See section 5.6 (O45).

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
- **Cohort representation lives in `accounts`.** CR and GR are a permission on student accounts (DEC-016), managed with other account data, and the account and profile services that must keep the posts filled are in `accounts` (section 5.4).
- **No change to `complaints`,** except that no code is shared through it.
- **No new dependency.**

### 4.2 Data model (Proposed)

All cohort references are `ForeignKey(..., on_delete=PROTECT)` to `academics.Batch`, `Semester` and `Section` (DEC-210).

**`accounts.CohortRepresentation`.** One row per **period** during which a cohort has a given CR and GR. History is kept: a period is ended, never deleted or edited. A change of CR, GR or both ends the current period and starts a new one.

| Field | Notes |
|---|---|
| `batch`, `semester`, `section` | The exact cohort |
| `cr`, `gr` | FK `User` (PROTECT), **both `NOT NULL`**. Students of that cohort when the period starts (service). |
| `is_active` | `TRUE` for the cohort's current period, `NULL` once ended (never `FALSE`) |
| `started_by`, `started_at` | Who appointed this pair, and when |
| `ended_by`, `ended_at`, `end_reason` (all nullable) | `end_reason` is one of `cr_replaced`, `gr_replaced`, `both_replaced`, `cohort_closed` (section 5.4, DEC-323), or `student_deactivated` / `cohort_changed` (inactive cohorts only, section 5.6) |

Each period names **both** posts, rather than storing one row per post: a row can't exist with only one post filled, so the database itself rules out a half-filled representation.

**Database constraints** (MySQL and SQLite):
- `cr` and `gr` are `NOT NULL`, and `CHECK (cr_id <> gr_id)`: every period has two different representatives.
- `UNIQUE (batch, semester, section, is_active)`: at most one current period per cohort.
- `UNIQUE (cr, is_active)` and `UNIQUE (gr, is_active)`: a student is CR of at most one current period, and GR of at most one.
- `CHECK (is_active IS NULL OR is_active IN (TRUE))` and `CHECK ((is_active IS NULL) = (ended_at IS NOT NULL))`.

MySQL ignores conditional unique constraints, so they are not used; this is the same nullable-marker technique `academics.AcademicTerm` uses (ACADEMIC_TERMS.md section 1).

**What the database does not guarantee.** These need the services in section 5:
- that one student is not CR in one cohort's period and GR in another's (the service checks the student is a member of exactly that cohort);
- that a represented, active cohort keeps a current period through every change (a cross-row rule);
- that every active cohort has a period at all.

**`collective_issues.CollectiveIssue`.** Write-once content.

| Field | Notes |
|---|---|
| `reference` | Unique, for example `CI-2026-00042`, generated like complaint references (O47) |
| `batch`, `semester`, `section` | The cohort, copied from the raiser's current representation period at publication; never changes |
| `raised_by` | FK `User` (PROTECT); kept even if they stop being a representative or are deactivated |
| `raised_as` | `cr` or `gr` at publication (historical label) |
| `title` | `CharField(max_length=120)`; 5–120 characters (database check below) |
| `description` | `TextField`; 20–2,000 characters (database check below; `TextField` alone sets no limit) |
| `status` | `received`, `under_review` or `resolved`, with a check constraint |
| `first_response_at` | Nullable. Set once, by the first official response or the resolution (O36); it closes the issue for support |
| `resolution_note` | `TextField`, empty until the issue is resolved; then 1–1,000 characters, written once (DEC-244). A copy of the resolving event's note, kept on the issue so the database can check it. |
| `resolved_at` | Nullable; set once, when the issue is resolved |
| `created_at`, `updated_at` | |

**`collective_issues.Support`:** `issue` (FK, PROTECT), `student` (FK `User`, PROTECT) and `created_at`, with `UNIQUE (issue, student)` in the database. Support is never withdrawn (DEC-241): the application never updates or deletes these rows. That is enforced by the ORM and the services (see "Write protection"), not by the database.

**`collective_issues.IssueEvent`.** Append-only history.

| Field | Notes |
|---|---|
| `issue` | FK |
| `kind` | `raised`, `status_changed` or `response` |
| `actor` | FK `User`, nullable for system events |
| `from_status`, `to_status` | Status-change events only |
| `message` | The response or resolution note |
| `created_at` | |

`IssueEvent` check constraints:
- a `status_changed` event to `resolved` must have a `message` of 1–1,000 characters (the resolution note);
- a `response` event must have a `message` of 1–1,000 characters;
- `raised` events and other status changes have an empty `message`.

`CollectiveIssue` check constraints. Django renders them as shown, verified with Django 5.2 against MySQL 8.0.44 and SQLite 3.50.4. Both functions count characters, not bytes:

| Name | MySQL 8.0.44 | SQLite |
|---|---|---|
| `collective_issue_title_length` | `CHAR_LENGTH(title) >= 5 AND CHAR_LENGTH(title) <= 120` | `LENGTH("title") >= 5 AND LENGTH("title") <= 120` |
| `collective_issue_description_length` | `CHAR_LENGTH(description) >= 20 AND CHAR_LENGTH(description) <= 2000` | the same with `LENGTH` |
| `collective_issue_status_valid` | `status IN ('received', 'under_review', 'resolved')` | the same |
| `collective_issue_resolution_consistent` | `(resolution_note = '' AND resolved_at IS NULL AND status IN ('received', 'under_review')) OR (resolved_at IS NOT NULL AND status = 'resolved' AND CHAR_LENGTH(resolution_note) >= 1 AND CHAR_LENGTH(resolution_note) <= 1000)` | the same with `LENGTH` |
| `collective_issue_resolved_was_answered` | `status <> 'resolved' OR first_response_at IS NOT NULL` | the same |

- **Generation:** in Django these are `CheckConstraint`s over `Length()` (with `GreaterThanOrEqual`/`LessThanOrEqual`), combined with `Q`.
- **Verified for this specification:**
  - MySQL 8.0.44 accepts `CHECK` on `TEXT` columns and enforces it on INSERT and UPDATE, so 2,001 two-byte characters are refused and 2,000 accepted;
  - a resolved row with an empty note is refused, on both databases.

  Implementation re-verifies these with `sqlmigrate` and raw-SQL tests.

**Enforcement layers.** Where each rule is guaranteed:

| Rule | Database (cannot be bypassed by ORM code) | Service, in one transaction under a row lock | Form (user feedback) |
|---|---|---|---|
| Title 5–120 and description 20–2,000 characters | Yes (checks above) | Validates trimmed values, then stores them trimmed | Yes |
| Minimum length of *meaningful* text (not only spaces) | No; the database counts stored characters | Trims before validating and storing | Yes |
| A resolved issue has a resolution note of 1–1,000 characters | **Yes**: `collective_issue_resolution_consistent` | Writes status, note and `resolved_at` in one `UPDATE` | Yes |
| A resolved issue has been answered (support closed) | Yes: `collective_issue_resolved_was_answered` | Sets `first_response_at` in the same `UPDATE` if unset | — |
| A resolved issue has its `status_changed` event carrying the same note | **No.** A cross-table rule; it needs triggers, which are not portable | **Yes**: the issue row is locked, and the issue update and the event insert commit or roll back together | — |
| Only allowed transitions, and no stale changes | No (only the status values) | Yes: transition table (section 8) and `expected_status` under the lock | Offers only allowed choices |
| One support per student per issue | Yes: `UNIQUE (issue, student)` | Savepoint, then catches the violation | — |
| One active CR and one active GR per cohort; one active post per student | Yes: unique indexes on the nullable marker | Locks rows in a fixed order | — |

So **an issue can never be stored as Resolved without a valid resolution note**, whatever ORM code runs: the database refuses it. The matching history event is guaranteed by the service transaction, not by the database. Raw SQL can bypass the service, but not the check constraints.

**Write protection** follows the complaint models. These are **application** protections (ORM and services); the database does not refuse an `UPDATE` or `DELETE` issued directly in SQL, because portable enforcement would need triggers:
- a protected queryset refuses `update()`, `bulk_update`, `delete()` and upserts on issues, support, events and representation periods;
- instance `save()` refuses changes to write-once fields (title, description, cohort, raiser, `raised_as`; the people and cohort of a representation period);
- `PROTECT` foreign keys stop a referenced user, cohort entry or issue from being deleted through the ORM;
- no route, form or admin action edits or deletes these records;
- status, `first_response_at`, `resolution_note` and `resolved_at` are changed only by services, under a row lock, and each is written once (a resolved issue never changes again);
- `Support` and `IssueEvent` are insert-only in the application, and a representation period is only ever ended (its `is_active`, `ended_*` fields), never edited otherwise;
- raw SQL or a database administrator can still modify rows; the database check and unique constraints above still apply to them.

**Indexes:**
- `CollectiveIssue (batch, semester, section, status)`;
- `CollectiveIssue (batch, semester, section, -created_at)`;
- `Support (issue)` (covered by the unique index).

**Migrations:** `accounts/000N_cohortrepresentation` (additive: a new table) and `collective_issues/0001_initial` (additive: new tables with the checks above). Neither alters an existing table or changes existing data.

## 5. Cohort representation (CR and GR)

### 5.1 The rule, and how it is kept
**Confirmed:** every section has exactly one CR and one GR (DEC-016). The owner restated on 2026-11-18 that vacant posts are not allowed. A student holds at most one post (DEC-240).

**What the system cannot do by itself.**
- **Cohorts appear one student at a time:** a cohort comes into existence when its first student self-registers (DEC-012, DEC-201), and students join one at a time.
- **Two students are needed:** a student holds one post, so a cohort can hold both posts only once it has two active students.
- **Entries are shared:** a `Batch`, `Semester` or `Section` entry is shared by many cohorts, so "activating a section" is not an event that can wait for one cohort's appointments.

So the system can neither appoint at the moment a cohort appears nor stop it from appearing.

**Confirmed rule (DEC-323, approved by the owner on 2026-11-18; it resolves O35 and O55):**
- **Represented:** a cohort is *represented* once its CR and GR have both been appointed by a Batch Advisor or the Super Admin. Both are appointed together, which needs at least two eligible active students.
- **No vacancy while eligible:** a represented cohort is *eligible* while its batch, semester and section are active and it has at least two active students. While eligible, it **always has exactly one CR and one GR**. Any representative's departure results in one of:
  - an atomic replacement;
  - refusal of the underlying change;
  - the closure case below.

  There is no "remove" operation.
- **The permitted exception, "Awaiting representatives":** a cohort with no CR or GR is allowed in exactly two situations:
  - **before its first appointment;**
  - **after a recorded closure.**

  It is shown with that label to its Batch Advisors and the Super Admin, and no collective issue can be raised in it. This is **not** a vacancy. A vacancy would be a represented, eligible cohort missing a post, and that is never permitted.
- **Closure:** a represented cohort's representation may be closed only when the cohort falls below two active students. It is recorded (`end_reason = cohort_closed`) in the same transaction as the change that causes it, and the cohort returns to Awaiting representatives.
- **Inactive cohorts** remain historical (section 5.6, O45).

| Guarantee | Database | Service (one transaction, row locks) |
|---|---|---|
| A representation period names both a CR and a GR, who are different people | **Yes**: `cr`/`gr` `NOT NULL`, `CHECK (cr_id <> gr_id)` | Also validates |
| At most one current period per cohort | **Yes**: unique index | Locks the cohort's current period |
| A student holds at most one post | **Partly**: unique indexes stop a student being CR (or GR) of two current periods | **Yes**: the student must be a member of exactly that cohort, and hold no other post |
| A represented, eligible cohort always has both posts | **No**: it spans rows and operations; it would need triggers | **Yes**: replacement in the same transaction, refusal, or recorded closure, all under the cohort lock (sections 5.2, 5.4 and 5.7) |
| Every active cohort is represented | **No** | **No**, by design: Awaiting representatives is the permitted exception (DEC-323), surfaced as a task |

### 5.2 Operations (services; one `transaction.atomic()`, rows locked)
Only the cohort's Batch Advisors and the Super Admin may run these (DEC-245). None of them is allowed in an inactive cohort (section 5.6, O45).
- **Appoint representatives:** the CR and GR are chosen together, for a cohort that is active and currently Awaiting representatives. The service takes the cohort lock (section 5.7) and then checks, under it, that there is still no current period.
  - be active students currently in that **exact** cohort;
  - be different people;
  - hold no other post.

  This creates the cohort's current period.
- **Replace the CR, the GR, or both:** the new person must meet the same rules, and may not be the other current representative unless both posts change (a swap). In one transaction:
  1. take the cohort lock (section 5.7), then lock the cohort's current period (`select_for_update`);
  2. check that it is the period the page showed (`expected_period`), so a stale page is refused;
  3. end it (`is_active = NULL`, reason `cr_replaced`, `gr_replaced` or `both_replaced`);
  4. insert the new period, keeping the unchanged representative.

  The end happens before the insert because MySQL checks unique indexes row by row. Other transactions see either the old period or the new one, never neither: the row is locked until commit, and an uncommitted change is invisible to them. If anything fails, everything rolls back and the original period stays current.
- **Remove a representative without a replacement:** **not offered, and refused by the service** (DEC-016).
- **Close representation:** no manual action. It happens only as part of section 5.4, when the cohort would fall below two active students.

**Safety net:** the unique indexes catch anything that gets past the locks; an `IntegrityError` becomes a form error, never a server error.

### 5.3 Authority checks (defence in depth)
Two checks exist, deliberately separate. Both are evaluated on every request, from the database, never from session or cached state.

- **Representative of the cohort** (`current_representative(user)`; used for *viewing* the private side, section 7.5). All of these must hold:
  - the user is active, with the student role and a student profile;
  - the user is the CR or GR of a current representation period;
  - that period's batch, semester and section **equal the user's current profile cohort**.
- **May act as representative** (`can_act_as_representative(user)`; used for *new actions*, for example raising an issue). The check above, **and** the cohort's batch, semester and section are all **active** (DEC-020, DEC-210; O45).

The checks are a backstop for section 5.4. If a future code path changed a student's activity or cohort without the services (for example, the shell), the moved or deactivated student would have no representative power. The check doesn't fill the post, however: a consistency query that lists represented, active cohorts whose current period names an ineligible student is part of the tests and of the Super Admin's CR/GR Management page (section 9.3), so any such breach is visible.

### 5.4 Lifecycle: one service boundary (DEC-212, DEC-016; DEC-021 manual promotion)
**Today** (on `main`):
- account changes are saved by `UserAdmin.save_model`, and profile changes by `StudentProfileAdmin.save_model`;
- `accounts.services.record_profile_changes()` only writes `StudentProfileChange` audit rows. It does **no** representative work;
- no other code path changes `is_active` or a student's cohort: the admin has no list-editable columns or bulk actions for them.

**Proposed** (Stage CI-1). The rules live in reusable services in `accounts.services`. Every caller uses them: the admin now, and any portal management page later.

- **`set_account_active(user, active, *, actor, replacement=None)`.** In one `transaction.atomic()`:
  1. take the cohort lock of the user's current cohort (section 5.7), then lock the current period, if any, and the user row;
  2. refuse to deactivate the last active Super Admin (the existing rule, moved from the admin form into the service);
  3. apply `is_active`.

  When deactivating a CR or GR of an active, represented cohort, step 3 is preceded by one of:
  - **with `replacement`** (an eligible student of that cohort): the post is replaced as in section 5.2, reason `cr_replaced` or `gr_replaced`;
  - **without `replacement`, while the cohort would keep at least two active students:** the operation is **refused** with a message naming the post, for example "This student is the GR of Fall 2024 · Semester 4 · Section A. Choose a new GR first, or in the same change.";
  - **without `replacement`, when the cohort would be left with fewer than two active students** (so no replacement can exist): the period ends with reason `cohort_closed` and the cohort returns to Awaiting representatives (the closure case of DEC-323).

  Reactivation sets `is_active` only and **never** restores an old post; a new appointment is needed.
- **`update_student_profile(profile, changes, *, actor, replacement=None)`.** In one `transaction.atomic()`:
  1. take the cohort locks of the old and new cohorts (section 5.7), then lock their current periods, if any, and the profile row;
  2. if the student is a CR or GR of an active, represented cohort and the batch, semester or section changes, apply the same three cases as above (replace, refuse or close) for the **old** cohort;
  3. apply and save the changes;
  4. call `record_profile_changes()` for the audit (unchanged).

  Students arriving in a cohort never change its posts.
- **Membership changes take the cohort lock:** any service that changes who belongs to a cohort takes that cohort's lock first (section 5.7), whether or not the cohort is represented yet. That covers deactivation, reactivation, a cohort change in or out, and new registration, where `register_student` gains this lock. So the "is there an eligible replacement?", "at least two students?" and "still awaiting?" checks always see a stable membership.
- **Atomicity:** each service is atomic. Inside an admin form it runs as a savepoint in the admin's transaction. Any failure rolls back the account or profile change, the audit rows and the representation change together; the original period stays current.
- **Admin wiring:** `UserAdmin.save_model` and `StudentProfileAdmin.save_model` call these services instead of saving directly. When the student holds a post in an active, represented cohort, the change form shows a **"New CR/GR for <cohort>" field**, limited to eligible students of that cohort.
  - If the field is left empty, the save is refused with the message above, except in the closure case.
  - This is the only change to existing admin behaviour, and existing account and audit tests must keep passing.
- **Promotion in practice** (DEC-021, manual):
  - moving the students of a represented cohort one by one requires replacing a representative whenever one of them moves while others remain;
  - moving them last closes the old cohort's representation when it would drop below two students;
  - the new cohort is awaiting representatives until both are appointed.

  This extra work for the person promoting is an accepted consequence of DEC-323.
- **History:** ended periods are never deleted. Issues keep `raised_by` and `raised_as` whatever happens to the account (brief A).

### 5.5 Proposed UI behaviour
Each cohort card (Batch Advisor "Representatives", Super Admin "CR/GR Management") shows:
- **Represented:** the CR and the GR by name and SAP ID, with **"Replace CR"**, **"Replace GR"** and **"Swap CR and GR"** actions. Each opens a form limited to eligible students of that exact cohort and carries `expected_period`. There is **no "Remove"** action.
- **Awaiting representatives** (the permitted state of DEC-323): a clear notice ("This cohort needs a CR and a GR") and one **"Appoint CR and GR"** form with two required choices.
  - If the cohort has fewer than two eligible students, the form explains why appointment isn't possible yet.
- **History:** a collapsible list of past periods: who, from when, until when, and why it ended.

### 5.6 Inactive academic entries: historical visibility versus new actions (DEC-324)
A cohort is **inactive** when its batch, semester or section is inactive. Records are never deleted or hidden because an entry was deactivated (DEC-210). The no-vacancy invariant applies to **active** cohorts only, and representatives are never appointed to inactive cohorts.

| | Cohort active | Cohort inactive |
|---|---|---|
| Appoint or replace representatives | Allowed (section 5.2) | **Refused** |
| A representative is deactivated or moves cohort | Replacement in the same transaction, or refused, or closure (section 5.4) | The current period ends (`student_deactivated` or `cohort_changed`); no replacement is required or possible |
| Raise an issue | Current representative | **Refused** (`can_act_as_representative` fails) |
| Support an issue | Students of the cohort, while open (O38) | **Refused**; existing support stays and still counts |
| BA: mark under review, respond, resolve | Allowed (section 8) | **Allowed**, so issues already raised can still be answered and closed |
| View issues, support counts, history | Per sections 3 and 7.1 | **Unchanged**: still readable by those with historical access (below) |
| View private responses and notes | Current representatives (O37), BAs, Super Admin | **Unchanged** while the period is current (viewing uses `current_representative`, which doesn't require active entries) |

**Reactivating an entry:** cohorts whose period is still current are represented again immediately. Cohorts whose period ended while inactive return to Awaiting representatives, the permitted state of DEC-323. Reactivation itself isn't blocked, because entries are shared by many cohorts.

**Who keeps historical access to an inactive cohort's issues:**
- the Super Admin;
- Batch Advisors whose `AdvisorAssignment` for that exact cohort still exists (deactivating an academic entry doesn't remove advisor assignments);
- students whose current profile cohort is still that cohort;
- that cohort's current representatives, for the private side.

A student moved to another cohort loses access, as in section 7.1.

### 5.7 The cohort lock (serialising every representation-related change)
**Problem.** Locking the cohort's current `CohortRepresentation` row is not enough: a cohort that is Awaiting representatives has no such row, and a missing row can't be locked. So two first appointments, or a first appointment and a registration or deactivation, could run at the same time. The unique index on the current period would stop two simultaneous appointments from both committing. It would not stop an appointment from being based on a membership count that another transaction is changing.

**Decision (Proposed): lock the cohort's `academics.Section` row**, with `Section.objects.select_for_update().get(pk=section_id)`, as the **first** statement of every representation-related transaction.
- **Always present:** every cohort references its section (`PROTECT`), and section rows are never deleted (DEC-210), so the lock target exists even before the cohort has representatives or students.
- **No creation race:** nothing has to be created before it can be locked.
- **Correctness:** every operation that can affect a cohort's representatives, its membership **or its eligibility** takes the same section row first, so those operations are serialised. That includes activating or deactivating the cohort's `Batch`, `Semester` or `Section` (below).
- **Trade-off, coarseness:**
  - the `Section` row is shared by every cohort with that section (for example "Section A" in every batch and semester), so unrelated cohorts are serialised too;
  - an admin edit of that `Section` entry also waits for, or blocks, these short transactions.

  Serialising more than necessary is never unsafe, only slower. At one department's volume, with few sections, writes that are mostly one-off administrative actions, and transactions lasting milliseconds, the contention is negligible. Registration peaks at the start of a semester are the busiest case; they stay short single-row transactions.
- **Isolation:** Django's MySQL backend runs **READ COMMITTED** (verified on this project), so the reads after the lock see the latest committed membership and periods. The lock is taken before those reads. SQLite serialises writers, and the MySQL tests are the concurrency proof.

**Fallback (if contention is ever measured):** a dedicated `accounts.CohortLock (batch, semester, section)` row with `UNIQUE (batch, semester, section)`.
- **Race-safe creation:** take it with `get_or_create` inside a savepoint; on `IntegrityError` (another transaction created it first), re-select it with `select_for_update`.
  - On MySQL, a concurrent insert of the same key waits on the unique index until the first transaction commits, so the second creator is serialised behind the first and then locks the existing row.
  - Locking a row that doesn't exist is never relied on.
- **Cost:** a new table and migration. It is not proposed for V1.

**One global lock order.** Every operation takes locks in this order, which rules out deadlocks between them:
1. **cohort locks** (the `Section` rows), in ascending section primary key, including the old and new cohorts of a cohort change. An academic-structure change takes **all** of them (below);
2. the **`Batch` or `Semester` row** whose active state is being changed (academic-structure changes only; a Section's own row is already held from step 1);
3. the **current `CohortRepresentation` rows** of those cohorts, in ascending primary key;
4. the **`User` and `StudentProfile` rows** involved, in ascending primary key.

Representation-related services never **lock** a `Batch` or `Semester` row. They only **read** its active state, with a plain read after their Section locks. So no transaction ever holds a Batch or Semester lock while waiting for a Section row: there is no reverse order, and no deadlock cycle between the two kinds of operation.

**Re-check after locking.** After taking its Section locks, every representation-related service re-reads, under them, the active state of the relevant batch, semester and section, and applies DEC-323 and O45 to that fresh state.
- **Eligibility:** appointing, replacing, raising and supporting need an active cohort.
- **Registration:** it needs active entries, as the registration form already requires.

A service that must first read a student's cohort to know which section to lock reads it, takes the lock, then **re-reads it under the lock**. If the cohort changed in between, it releases nothing early: it refuses with a conflict message ("This student's details changed at the same time. Please try again.") rather than acting on the wrong cohort.

| Operation | Locks, in order |
|---|---|
| Registration (`register_student`) | Section of the new cohort |
| First appointment | Section; then checks there is still no current period, and the candidates' membership and activity |
| Replacement or swap | Section; current period (with `expected_period`); candidate rows |
| Deactivation or reactivation (`set_account_active`) | Section of the student's cohort; current period; user row; replacement candidate |
| Cohort change (`update_student_profile`) | Sections of the old and new cohorts (ascending); their current periods; profile row; replacement candidate |
| Closure | Taken inside the deactivation or cohort change that causes it, under the same locks |
| Activate or deactivate a `Batch` or `Semester` | **All** Section rows, ascending; then that Batch or Semester row; then the update |
| Activate or deactivate one or more `Section` entries | **All** Section rows, ascending (this includes the changed ones); then the update |

**Academic-structure changes.** A cohort's eligibility depends on its `Batch` and `Semester` being active, as well as its `Section`. So changing their active state must be serialised against representation-related transactions through the same Section locks.
- **Rule:** every change to the active state of a `Batch`, `Semester` or `Section` runs in one transaction that:
  1. **first** locks **all** `Section` rows in ascending primary key (`Section.objects.select_for_update().order_by("pk")`, evaluated);
  2. then changes the entry's `is_active`, inside that same transaction.
- **Why all Section rows, not only the affected ones:**
  - the set of sections used with a batch or semester is not stored anywhere. It would be computed from cohorts (profiles, assignments, periods, complaints), and a concurrent registration could add a cohort with a section outside the computed set. Locking all of them includes every affected section by definition;
  - a list-editable admin save changes several entries in **one** transaction, in display (name) order. Locking all sections in ascending order before any change keeps the order consistent whatever rows are edited;
  - academic-structure changes are rare administrative actions, and there are few sections. A Section's own change therefore locks its own row too, as part of the full set.
- **No new product rule:** deactivating a batch, semester or section does **not** close or change representation periods. The cohort simply becomes inactive, and section 5.6 (O45) and DEC-323 apply unchanged. The lock only makes eligibility checks see a stable answer.
- **Prerequisite (does not exist today):** `academics` has no service or explicit transaction boundary for active-state changes. They are made in the Django admin (`AcademicEntryAdmin`) on the change form and through the list-editable `is_active` column. Stage CI-1 must add:
  - a service `academics.services.set_entry_active(entry, active, *, actor)` that takes the Section locks above and then saves;
  - wiring `AcademicEntryAdmin.save_model` to it. Both the change form and the list-editable save call `save_model` inside Django's own `transaction.atomic()`, so the locks and the change share one transaction. Locking all sections on every call is idempotent within that transaction.

**How the races resolve:**
- **Two simultaneous first appointments:** both block on the section row. The second runs after the first commits, sees a current period, and is refused ("This cohort's representatives were just appointed"). The unique index on the current period is the database backstop.
- **First appointment against a registration:** whichever runs second sees the other's committed result. A registration never affects existing posts.
- **First appointment against the deactivation of a candidate:**
  - if the deactivation commits first, the appointment's re-validation finds the candidate inactive and refuses;
  - if the appointment commits first, the deactivation finds a represented, eligible cohort and needs a replacement, or is refused, or closes (fewer than two students).
- **Two replacements of the same post:** serialised; the second is refused as stale (`expected_period`).
- **First appointment against a `Batch` or `Semester` deactivation:**
  - **if the appointment wins** (it holds the cohort's Section lock first): the deactivation waits for that lock and proceeds after the appointment commits. The cohort is then represented and inactive. Its period stays (section 5.6), and no new actions are allowed.
  - **if the deactivation wins** (it holds all Section locks and commits first): the appointment acquires its Section lock afterwards, re-reads the batch and semester, finds the cohort inactive, and is refused.
- **Appointment against a `Section` deactivation:** the same, with the Section row itself as the shared lock.
- **Registration or cohort change against a deactivation:** the same serialisation. If the deactivation commits first, the registration or cohort change re-reads the entries under its lock and refuses an inactive target, exactly as the registration form already refuses inactive entries.

**Database versus services.** The database guarantees the per-row rules in section 4.2. The cohort lock and the service checks guarantee the cross-row rules: no vacancy in a represented, eligible cohort, and every check seeing a stable membership.

## 6. Raising an issue (DEC-040, DEC-242)

**Who:** the cohort's current CR or GR (section 5.3). The issue's cohort is always taken from the representative's current period and never from request data.

**Fields:**

| Field | Required | Rule |
|---|---|---|
| Title | Yes | 5–120 characters after trimming. Shown on the noticeboard and in notifications. |
| Description | Yes | 20–2,000 characters. Plain text with line breaks; no HTML or Markdown rendering. |
| Category | — | **None in V1** (O42). Complaint categories describe individual problems and are managed for complaints (DEC-220); reusing them would couple two workflows. |

The minimum lengths prevent accidental empty or one-word issues. The form and the service validate the **trimmed** text; the database checks the stored length (section 4.2, "Enforcement layers").

**Publication** (O41). There are no drafts. Submitting shows a **review step**:
- the exact title and description;
- the statement "Once published, this issue can't be edited or removed. Every student in <cohort> will see it and can support it.";
- a required confirmation checkbox and a "Publish issue" button (the one Forest primary on the page).

The review step re-posts the same fields and keeps no server-side draft. Publishing creates the issue, sets status `received` and records a `raised` event in one transaction. It then queues the DEC-270 notifications after commit (section 10) and redirects to the issue (PRG). The submit button is disabled after the first click.

**Duplicates** (O43). Nothing is blocked; separate issues may be similar. The form shows the cohort's issues that are still open for support (reference and title) as a non-blocking notice: "Your section already has these open issues. Supporting one may be better than raising another." This mirrors DEC-225's spirit for complaints. A per-representative rate limit is not proposed (O48).

**Locked after publication.** There is no edit or delete route for any role (DEC-242, DEC-324). The issue page says: "Published issues are locked: they can't be edited or removed." Corrections are made by raising a new issue.

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
- **Empty state:** "No open issues in your section." It explains that the CR or GR raises issues for the cohort (the existing text). If the cohort is awaiting representatives, it says instead: "Your section's CR and GR haven't been appointed yet. Collective issues start once they are."
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
  - "Support is closed for this issue." for a POST after closure, or in an inactive cohort (section 5.6).
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
  - separate panels for the three actions of the table below (no combined form; O53).
- **Actions** (DEC-243, DEC-244, DEC-324). The approved workflow has three separate actions, and every one is private to the cohort's representatives, BAs and the Super Admin:

  | Action | Allowed from | Input | Effect, in one transaction with the issue row locked | Closes support? |
  |---|---|---|---|---|
  | **Mark under review** | Received | Nothing; no response is needed | Status becomes Under Review; `status_changed` event | No |
  | **Send official response** | Received, Under Review | Response of 1–1,000 characters (required) | Status unchanged; `response` event; sets `first_response_at` if unset | **Yes**, on the first response (O36) |
  | **Resolve** | Received, Under Review | Resolution note of 1–1,000 characters (required) | Status becomes Resolved; `resolution_note`, `resolved_at` and, if unset, `first_response_at` in one `UPDATE`; `status_changed` event with the same note | **Yes** (if not already closed) |
  | Any action | Resolved | — | Refused: Resolved is final in V1, with no reopening (O49) | — |

- **The direct questions:**
  - **Under Review without a response:** yes. Marking under review needs no response and does not close support.
  - **A response without a status change:** yes. A response never changes the status, as for complaints (DEC-305's principle). More than one response is allowed until the issue is resolved (O53).
  - **Does the first response always close support:** yes, the first response or the resolution, whichever comes first (O36). Later responses don't change it.
  - **Does a resolution note count as the official response:** yes. Representatives see it labelled "Resolution note", and it closes support if nothing has yet.
- **Concurrent actions by two BAs.** Every action locks the issue row with `select_for_update`, so actions on one issue are serialised:
  - **status actions** (Mark under review, Resolve) carry an `expected_status` from the page the BA saw, as in complaints (P3-6). If the status changed in the meantime, the action is refused with an explanation and nothing changes;
  - **Send official response** re-checks under the lock that the issue is not Resolved. Two responses sent at once are both recorded in commit order; the first sets `first_response_at`;
  - **support against closure:** the support service also locks the issue row and checks `first_response_at` under the lock. A support committed after the closing action is therefore refused, and the frozen count is exact.
- **No Rejected status** (DEC-244 lists three statuses).
- **No delete or edit actions.**
- **All BAs assigned to the exact cohort** see and can act on its issues (DEC-324). There is no owner designation for collective issues.

## 9. Super Admin oversight (DEC-247)

### 9.1 Collective issues
`/super-admin/collective-issues/` is a department-wide list and issue view, read-only in V1 (DEC-324).
- **Filters:** cohort, status, current academic term (reusing `term_window()`), and search.
- **Issue view:** content, support count and the full history, including private responses (oversight).
- **No editing or deletion** (immutability).
- **No moderation or hiding action in V1** (DEC-324). This is an accepted V1 limitation and risk: abusive or incorrect published content cannot be withdrawn from view.

### 9.2 Representatives (Batch Advisor)
`/advisor/representatives/` shows the advisor's assigned cohorts and their CR/GR posts (section 5.5).

### 9.3 CR/GR Management (Super Admin)
`/super-admin/representatives/` covers every cohort, with filters for batch, semester, section and **awaiting representatives**. It uses the same actions and history as section 5.5, and also lists any represented, active cohort whose current period names an ineligible student (the consistency check of section 5.3), which should never happen.

All three destinations already exist in the navigation as unavailable entries ("Collective Issues", "Representatives", "CR/GR Management"; `accounts/navigation.py`). Implementation enables them.

## 10. Notifications

- **Confirmed** (DEC-270): "New CR/GR issue in your section".
  - **Recipients:** every **active** student whose current profile cohort is the issue's cohort, **except the raiser**.
  - **Content:** title "New issue in your section: <title>" (truncated); destination: the issue page.
  - **Delivery:** created after the publishing transaction commits, through `notifications.services.notify` (one row per recipient; the existing unique constraint per recipient and source prevents duplicates).
  - **Scale:** for one section, a single post-commit loop is enough; a bulk helper may be added to `notifications.services` if it measurably helps.
- **Confirmed (DEC-325):** "Response to your section's issue" goes to the cohort's **current** CR and GR when a BA sends an official response or resolves an issue. The response is private and the issue leaves the noticeboard after the first response (DEC-243), so this notification alerts the representatives. A resolution sends one notification for that BA action, not a duplicate response notification.
- **Not proposed:**
  - notifications to BAs or the Super Admin for new issues or support (the workspaces show them, consistent with complaints);
  - notifications for each support;
  - notifications for representative changes.

## 11. Explicit exclusions (V1)

- Comments, discussion or chat (DEC-241, DEC-052).
- Editing or deleting a published issue by anyone (DEC-242, DEC-324); drafts stored on the server.
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

## 12. Decision traceability

The following collective-issue product questions were approved by the owner on 2026-11-18 and are recorded as confirmed decisions in `DECISIONS.md`:

| Item | Approved outcome | Decision |
|---|---|---|
| O27 (collective issues only) | All BAs assigned to the exact cohort can see and act on collective issues; no designated owner. O27 remains open for Student Voice and meeting requests. | DEC-324 |
| O35, O55 | The permitted Awaiting representatives states and no-vacancy lifecycle. | DEC-323 |
| O36 | First official BA response or resolution note closes support; Under Review alone does not. | DEC-324 |
| O37 | Current CR and GR see the cohort's full issue and response history, including predecessor issues; former representatives lose representative-only access. | DEC-324 |
| O38 | Support stops after closure; the count freezes. | DEC-324 |
| O39 | Non-representative students see only Open for support / Support closed, not detailed status or private responses. | DEC-324 |
| O40 | Supporter identities are never shown in the interface; counts only. | DEC-324 |
| O41–O43 | No stored drafts; mandatory review/lock confirmation; no categories; non-blocking duplicate notice. | DEC-324 |
| O44 | Super Admin oversight is read-only in V1. | DEC-324 |
| O45 | Inactive cohorts accept no new appointments, issues or support; historical records remain accessible; BAs may still act on existing issues. | DEC-324 |
| O46 | Representative workflows are reached from Home and section issue pages; no new phone destination. | DEC-324 |
| O47 | References use `CI-<year>-<5 digits>`. | DEC-324 |
| O48 | No representative issue-raising limit in V1. | DEC-324 |
| O49 | No Rejected status or reopening; Resolved is final. | DEC-324 |
| O50 | No moderation or withdrawal-from-view action in V1; this is an accepted risk. | DEC-324 |
| O51 | Notify current CR and GR when a BA sends an official response or resolves an issue. | DEC-325 |
| O52 | GR means Girls Representative, per DEC-016; no gender data is recorded or checked. | DEC-324 |
| O53 | BA actions are separate—Mark Under Review; Send Official Response (status unchanged, repeatable until resolved); Resolve (mandatory note, counts as a response). | DEC-324 |
| O54 | No role may edit or delete a published issue in V1. | DEC-324 |

## 13. Conflicts between the brief and confirmed decisions

These differences between the original brief and confirmed decisions are settled. The specification follows the confirmed decisions; they must not be reopened without a new owner decision.
1. **"General Representative" vs DEC-016 "Girls Representative".** DEC-016 and DEC-324 retain "Girls Representative".
2. **Who assigns representatives.** The brief asks how the *Super Admin* assigns CR/GR. DEC-245 also gives this to **Batch Advisors** for their assigned cohorts, and this specification includes both.
3. **Support removal.** The brief asks about "Support and remove-support behaviour, if removal is appropriate". DEC-241 forbids withdrawal, so there is none.
4. **Scope of the lock.** DEC-242 forbids editing and deletion by CR/GR; DEC-324 confirms that no role may edit or delete a published issue in V1.

## 14. Security and integrity

- **Exact cohort isolation:**
  - every query starts from `visible_issues(user)`;
  - every action re-checks scope in its service;
  - a cohort is never accepted from request data: issue creation uses the representative's current period, and filters only narrow the scoped set (forged cohort values are ignored, as in the complaint workspaces).
- **IDOR:** references are looked up only within the visible set, so an unknown reference and one out of scope give the same 404.
- **Methods:** state changes are POST with CSRF; GET never changes data. Every page requires login, and inactive users are signed out by the existing backend.
- **Concurrency:**
  - **Support:** inserted in a savepoint and caught on the `UNIQUE (issue, student)` violation, so a double click or two tabs record one row and report "already supported".
  - **Status and response:** they lock the issue row; status actions use `expected_status`, and responses re-check that the issue is not Resolved (section 8).
  - **Support against closure:** support also locks the issue row and checks `first_response_at` under the lock, so no support lands after closure.
  - **Representation:** every representation-related change, and every change to a Batch, Semester or Section's active state, takes the Section-row locks first (academic-structure changes take all of them, in ascending order). Then come the Batch or Semester row being changed, the current period, and the user and profile rows, in one global order (section 5.7). Representation services only read Batch and Semester states after locking. Concurrent first appointments, replacements, membership changes and academic deactivations are serialised; neither a duplicate nor a missing CR or GR can result.
  - **Tests:** MySQL concurrency tests use separate connections, as for academic terms.
- **Immutability** (application-level; see "Write protection" in section 4.2 for exactly what the database does and does not enforce):
  - protected querysets and instance guards on write-once fields;
  - insert-only `Support` and `IssueEvent`;
  - no delete permission in any admin;
  - `PROTECT` foreign keys throughout.
- **Database guarantees versus service guarantees:** see "Enforcement layers" (section 4.2). In particular, a resolved issue always has a resolution note (database check). The matching event is guaranteed by the service transaction.
- **Lifecycle, DEC-016 and DEC-323:** the `set_account_active` and `update_student_profile` services (section 5.4) keep both posts filled in a represented, eligible cohort: replacement in the same transaction, refusal, or recorded closure below two students. The two authority checks (section 5.3) are the backstop. Inactive cohorts allow no new actions and keep their history readable (section 5.6).
- **Privacy:**
  - responses and resolution notes never appear in student pages or student notifications;
  - supporter identities never appear;
  - CR/GR gain no access to complaints, Student Voice or meetings (DEC-246).

## 15. Test strategy

- **Models and migrations:**
  - each check verified with raw SQL on MySQL and SQLite: a representation period can't lack a CR or a GR, or name the same student twice; one current period per cohort; a student can't be CR (or GR) of two current periods; unique support; title and description lengths (including multibyte text at the limits); resolution consistency; resolved-was-answered; and the event message checks;
  - protected querysets;
  - migrations reverse and re-apply.
- **Services:**
  - **no vacancy, ever:**
    - appointing requires both posts in one action, for an active cohort awaiting representatives;
    - replacing a CR, a GR, both, or swapping is atomic: no read, from another connection, can observe the cohort without its current period;
    - removing without a replacement is refused;
    - every eligibility rule (active student, exact cohort, no other post, different people);
  - **lifecycle:**
    - deactivating a CR or GR without a replacement is refused, and with a valid replacement both happen together;
    - the same for a cohort change;
    - closure, recorded, only when the cohort would fall below two active students;
    - in inactive cohorts the period ends without a replacement;
  - **rollback:** a failure injected after the old period ends, after the new period is inserted, and after the profile is saved leaves the original CR and GR current, and the account, profile and audit rows unchanged;
  - reactivation never restores a post;
  - history: every ended period remains, with its people, dates and reason;
  - the last-active-Super-Admin rule still holds;
  - the admin forms use the services, and existing account and audit tests still pass;
  - both authority checks when the services are bypassed (raw update of `is_active` or the profile cohort);
  - inactive cohorts: appointing, replacing, raising and support are refused; BA actions are allowed; history stays readable (section 5.6);
  - raising: the cohort comes from the current period; validation; the lock; refused in cohorts awaiting representatives;
  - support: once, closed after the first response, idempotent repeats;
  - the section 8 action table, row by row: Mark under review, responses (several, status unchanged, the first closes support), Resolve (note required, counts as a response); stale and post-resolution actions are refused; Resolved is final.
- **Permissions:** the full matrix of section 3, for every route. Includes forged references, forged cohort filters and IDOR attempts, other cohorts, other BAs, inactive users and former representatives.
- **Concurrency (MySQL only, separate connections):**
  - simultaneous support by one student;
  - simultaneous replacement of the same post (exactly one succeeds; the other is refused as stale; never two or zero CRs);
  - a replacement against the deactivation of the replacement candidate;
  - a deactivation against a registration into the same cohort (the fewer-than-two check sees a stable membership);
  - **first appointment with no representation row:**
    - two simultaneous first appointments for the same Awaiting cohort: exactly one commits, the other is refused, and there is never more than one current period;
    - a first appointment against a registration into that cohort;
    - a first appointment against the deactivation of one of its candidates, in both commit orders;
    - a first appointment against a cohort change moving a candidate out;
  - the lock order holds: a cohort change between two sections running against the opposite change finishes without deadlock;
  - **academic-structure changes** (section 5.7):
    - first appointment against `Batch` deactivation, in both commit orders: either represented then inactive, or refused;
    - first appointment against `Semester` deactivation, in both commit orders;
    - appointment (first appointment and replacement) against `Section` deactivation, in both commit orders;
    - registration, and a cohort change, against the deactivation of the target batch, semester or section: refused if the deactivation commits first, otherwise completed before it;
    - **no deadlock:** a `Batch` deactivation, a `Semester` deactivation and a list-editable save of several `Section` rows run together with two-section cohort changes, and all finish;
    - deactivating a batch or semester leaves existing representation periods unchanged (no closure; O45 and DEC-323 unchanged);
  - two BAs acting on one issue (status against status, response against resolve);
  - support against the closing response.
- **Notifications:** one per current CR/GR for each BA official-response or resolution action (DEC-325); never to the raiser solely by virtue of raising the issue, other cohorts or inactive students; none if the transaction rolls back. Test that a resolution emits one notification, not duplicate response and resolution notifications.
- **Privacy:** response text, resolution notes and supporter identities are absent from every student page, the student response context and student notifications.
- **Frontend:**
  - every page and state at 1280×590, 1232×590, 1100×590, 1600×740, 1440×800 and 360px (DEC-307);
  - keyboard focus and 44px touch targets;
  - long titles and names;
  - empty and error states.
- **Regression:** complaints, analytics and existing navigation are unchanged.

## 16. Implementation plan (PR-sized stages)

1. **Stage CI-1: cohort representation.**
   - **Contents:**
     - the `accounts.CohortRepresentation` model and its migration;
     - the appoint and replace services (no remove);
     - `set_account_active` and `update_student_profile` with replacement, refusal and closure, and the cohort lock (section 5.7) added to them and to `register_student`;
     - the two admin `save_model` methods rewired to them, with the replacement field;
     - the authority checks and the consistency check;
     - **prerequisite:** `academics.services.set_entry_active`, with `AcademicEntryAdmin.save_model` (change form and list-editable saves) rewired to it, so academic active-state changes take the Section locks (section 5.7). There is no model or migration change.
     - the BA "Representatives" and Super Admin "CR/GR Management" pages.
   - **Needs:** DEC-323 and DEC-324; representation lifecycle and inactive-cohort rules are settled.
   - **Independently useful:** representatives are recorded before issues exist.
2. **Stage CI-2: raising, the noticeboard and support.**
   - **Contents:** the `collective_issues` app with models, the migration, `visible_issues`, the raise flow with review step, the Home noticeboard, the section issues list and issue pages, support, and the DEC-270 notification.
   - **Needs:** CI-1; raising, noticeboard and support rules are settled by DEC-324.
3. **Stage CI-3: Batch Advisor workspace and Super Admin oversight.**
   - **Contents:** respond, status with resolution note, the representatives' private views, Super Admin read-only oversight, and the approved representative response notifications (DEC-325).
   - **Needs:** CI-2; routing, staff permissions, moderation scope and response notifications are settled by DEC-324 and DEC-325.
4. **Stage CI-4: acceptance and documentation.** Full regression on both databases, browser acceptance and technical notes.

Each stage adds only additive migrations and changes no existing data. Complaint behaviour is untouched throughout.

## 17. Decision record (approved; implementation pending)

All product decisions formerly listed as open in this specification are recorded in `DECISIONS.md`: DEC-323 (representation lifecycle; O35 and O55), DEC-324 (collective-issue routing and product rules; O27 for collective issues and O36–O50, O52–O54), and DEC-325 (representative response notifications; O51). O27 remains open only for BA routing in Student Voice and meeting requests. The technical design remains subject to implementation review; product approval does not mean the feature has been implemented.
