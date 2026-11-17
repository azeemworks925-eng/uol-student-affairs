# UOL Student Affairs — Development Log

**Purpose:** A dated record of what was done and decided in each working session.
**Canonical location:** This file in the GitHub repository.

Rules:

- Newest entry first.
- Record what actually happened. Do not record plans as completed work.
- Decisions are recorded in full in `DECISIONS.md`; entries here refer to them by ID.
- Dates use the owner's local time (Asia/Karachi).

---

## Status at a glance (2026-11-17)

| Area | Status |
|---|---|
| V1 product workflows | Confirmed in `DECISIONS.md`. |
| Django foundation | Complete and verified locally. Merged into `main` through PR #1 (merge commit `a1ed704`). |
| Authentication and account foundation | Merged into `main` through PR #3 (merge commit `df47133`). Google sign-in is tested with simulated Google responses only; it has **not** been verified with a real UOL Google account. |
| Design | Forest palette (Light and Dark) and Design D approved (DEC-300 to DEC-308). Written specification: `docs/design/DESIGN_PLAN.md`. Open: O30 and O34; O25 is resolved by DEC-315. |
| Production frontend | Milestone 1 (application shell, role navigation, role home pages, sign-in pages) merged into `main` through PR #6 (merge commit `c9a4cd3`). Verified locally only; not deployed. |
| Complaints | Parts 1–3 merged into main through PRs #7–#11. Part 4 specification merged through PR #12 (`4348b15`); Stage 1 (Super Admin workspace and owner assignment) through PR #14 (`5bed61e`); Stage 2 (category management) through PR #15 (`b30d29d`); Stage 3 (in-app notifications) through PR #16 (`d857d27`). Stage 4a (academic terms and the Super Admin term filter) on branch `feat/academic-term`, awaiting review. Stage 4b (analytics) and Stage 5 (final acceptance) are not implemented. |
| Other product features | Student Voice, meetings, collective issues and the Super Admin analytics are not implemented. |
| Deployment | Not done. Production static-file serving and HTTPS settings are not configured. |

---

## 2026-11-17 — Complaints Part 4 Stage 4a: academic terms (awaiting review)

Branch `feat/academic-term`, created from `main` at `290250a`. This entry records the work and its local verification. **It is not merged.** Technical notes: `docs/technical/ACADEMIC_TERMS.md` and `COMPLAINTS.md` section 8.

- **Model:** `academics.AcademicTerm`, with a name, start and end dates and a current flag (`TRUE` or `NULL`).
  - **One current term:** a plain unique index on the nullable flag allows at most one current term on both MySQL and SQLite. A check constraint allows only `NULL` or `TRUE`. The check is written as an explicit `IN (TRUE)` comparison: SQLite compiled the first version to a bare truthiness test, which accepted `2` beside `1` (two current terms). The SQLite test run found this and it was fixed before commit; a regression test covers it.
  - **Dates:** a second check requires `end_date >= start_date`.
  - **Names:** duplicates are refused ignoring case and accents.
  - **Never deleted;** the ORM refuses writes to the current flag outside the services.
- **Migration** `academics/0002_academicterm`:
  - additive and reversible;
  - a test reverses and re-applies it on both databases;
  - **not applied** to the owner's development database.
- **Services:** `set_current_term`, `clear_current_term(expected=...)` and `current_term`.
  - Every term row is locked in primary-key order, and the current term is re-read under the locks.
  - The old term is cleared before the new one is set.
  - An `IntegrityError` is converted after the atomic block rolls back.
- **Reporting window:** `term_window()`, from the start date 00:00 Asia/Karachi (inclusive) to the day after the end date at 00:00 (exclusive). Validation keeps dates between 1900 and 9998 so the boundaries stay representable in UTC.
- **Admin:** term management under Academic Structure, with no deletion and a read-only current flag. The "Make current term" action requires exactly one term. The "Clear current term" action requires the current term alone and refuses if another Super Admin changed it in the meantime. Integrity errors are shown as messages, not server errors.
- **Complaint list:**
  - The Super Admin list gains an "Academic term" filter with a chip showing the name and exact dates; the chip's "Remove" link clears only the term.
  - `term` is carried in the Super Admin list state only.
  - The Batch Advisor list ignores a forged `term`, and its queries are unchanged.
  - Student pages are unchanged.
- **Not in this stage:** analytics, suppression or Overview changes. Those are Stage 4b, whose privacy plan is reviewed separately. The allauth W036 warning is untouched.
- **Mutation checks** (each change made temporarily, then restored), all caught by the tests:
  - an inclusive end boundary;
  - a missing term filter;
  - the term carried in Batch Advisor links;
  - the row lock removed;
  - the stored-row guard skipped for new instances.
- **Verification** (local runs; the repository has no hosted CI):
  - **Focused tests on MySQL 8.0.44:** academics 63/63; term filter 21/21.
  - **Full suite on MySQL:** 546/546 in two consecutive `--keepdb` runs.
  - **SQLite:** 546 with 10 MySQL-only skips (the 5 new term concurrency tests and 5 existing ones). Focused: 84, with 5 skips.
  - **Checks:** `check`: no issues. `makemigrations --check --dry-run`: no changes. `compileall` and `git diff --check`: clean.
  - **`migrate --check`:** exits 1, because `academics.0002_academicterm` is unapplied on the development database, as instructed.
- **Browser acceptance** (headless Chrome; 7 states × 6 viewports: 1280×590, 1232×590, 1100×590, 1600×740, 1440×800 and 360px):
  - No horizontal overflow, clipping or covered content.
  - Visible 2px focus on the chip's Remove link and on the term select.
  - The Remove target is at least 44px tall at 360px.
  - **Fix made during testing:** the chip first sat below the open filter panel, under the fold at 1280×590. It was moved above the panel.
  - **Pre-existing:** the only small targets at 360px are the skip link and the wordmark.

---

## 2026-11-17 — Complaints Part 4 Stage 3 merged (PR #16)

- PR #16 (in-app notification foundation and complaint producers) was squash-merged into `main` on 2026-11-17 at 15:19 Asia/Karachi (10:19 UTC) as merge commit `d857d276f94c38bc081e7b86bf9a3205ddc16dee`. Its final PR head was `fd046a1`.
- **Final change before merge:** the review's source-validation correction. `notify()` accepts only a persisted source record: a Django model instance of the type's declared model, not marked as new, with a pk and database alias, whose row exists on that alias. It has regression tests for:
  - an unsaved source with an unused explicit pk, and one with the pk of an existing row;
  - a stale source whose row was removed with raw SQL;
  - a normal persisted source;
  - `None` and non-model objects, an unsaved instance carrying an alias, a forged instance with no alias;
  - the alias used by the existence check.

  The details are in the Stage 3 entry below.
- **Final verification reported by Claude Code (local runs, not hosted CI; the repository has no CI workflow):**
  - 462/462 tests on MySQL 8.0.44 in two consecutive `--keepdb` runs;
  - 462 on SQLite with 5 MySQL-only skips;
  - the 64 focused notification tests passed on MySQL, and 61 ran successfully on SQLite with 3 MySQL-only skips.
- **After the merge,** the owner applied `notifications.0001_initial` to the local development database, confirmed it with `showmigrations notifications` (`[X] 0001_initial`), and ran `migrate --check` successfully, with no unapplied migrations.
- **Status:** Stage 3 is complete. Stage 4 (academic-term configuration and privacy-safe complaint analytics on the Super Admin Overview) is not implemented. Its implementation plan is being prepared for review.

---

## 2026-11-17 — Complaints Part 4 Stage 3: in-app notifications

**Context**

- Branch `feat/notification-foundation` from `main` at `b30d29d` (Stage 2 merged, PR #15). Implements COMPLAINTS_PART4_SPEC.md section 5 with the reviewed plan and its refinements:
  - write-once notifications on every ORM path;
  - producers allowed for inactive recipients, while user-facing access requires an active user;
  - role-only attribution in response previews;
  - a registry that declares each type's source model and destinations;
  - `change_status()` passing its exact `ComplaintEvent`.
- No product decision changed; no documentation drift was found.

**What was done**

- **New `notifications` app** (`docs/technical/NOTIFICATIONS.md`):
  - **Model:** `Notification` with the unique key (recipient, source_type, source_id), plus unread and recent indexes.
  - **Write-once content:** `update()` and `bulk_update()` accept only `read_at`; upserts are refused; instance `save()` only inserts or updates `read_at`; a newly built object with an existing primary key is refused.
  - **Registry:** source model and allowed destinations per type.
  - **`notify()`:** validated, deduplicated with `get_or_create`, and run inside the caller's transaction.
  - **User-facing services:** scoped to the active user.
  - **Pages:** `/notifications/` (list), POST `open` (marks read, then a 303 redirect to a registry-built destination) and POST `read-all`.
  - **Header entry point for every role:** a sidebar row, a rail bell and a phone-header bell, with an ink badge and a lazy count. It sits outside the role navigation.
- **Complaint producers** (`complaints/notifications.py`, `COMPLAINTS.md` section 7): `change_status()` and `respond()` notify the submitting student inside the same transaction, using that exact event. Status notifications carry the new status (never the note or reason); responses carry a role-only, truncated preview. No other event, and no other recipient.
- **Migration:** `notifications/0001_initial` only (reversible). No complaint migration.

**Verification**

- **Tests:** 56 new tests.
  - **`notifications/tests/test_foundation.py` (23):**
    - every protection path;
    - the database constraint;
    - `notify` validation (type, source model, saved source, destination) and deduplication;
    - inactive recipients receive notifications and keep them after reactivation;
    - user scoping, and tampered destinations;
    - migration reversal on both databases;
    - MySQL concurrency: duplicate `notify`, concurrent `mark_read`.
  - **`complaints/tests/test_notifications.py` (15):**
    - one notification per status change and response;
    - no notes or reasons in status notifications;
    - role-only attribution, with no account identity added and staff-written names kept;
    - exclusions, single recipient, the actor guard and idempotence;
    - rollback both ways, and the workspace flow;
    - the MySQL stale-status race giving exactly one notification.
  - **`notifications/tests/test_views.py` (18):**
    - anonymous, inactive and per-role access, and the registration redirect;
    - 405 on GET, CSRF, and cross-user 404s identical to missing ones;
    - open/read and the 303 redirect; tampered destinations (raw SQL); no access granted to the linked record;
    - the list, marking all read, empty states and pagination;
    - the header label, badge cap and `aria-current`, and the entry point absent from the bottom bar and Overview links;
    - the lazy context processor.
- **Mutation checks:**
  - removing the producer call from `change_status`, or attributing responses by name, fails the producer tests;
  - removing recipient scoping from `mark_read`, or removing the destination allowlist, fails the view and foundation tests.
- **Results:**
  - 454/454 on MySQL 8.0.44 in two consecutive `--keepdb` runs; the 56 Stage 3 tests pass on MySQL.
  - 454 on SQLite with 5 skipped (MySQL-only concurrency tests: `test_only_one_stale_status_change_succeeds`, `test_only_one_notification_for_the_successful_change`, `test_concurrent_submissions_get_distinct_references`, `test_concurrent_mark_read_keeps_one_timestamp`, `test_concurrent_notify_for_one_source_creates_one_row`).
  - `check`: no issues. `makemigrations --check --dry-run`: no changes. `compileall`: exit 0. `git diff --check`: clean.
  - `migrate --check` against the **development** database exits 1 only because `notifications.0001_initial` is not applied there yet; it is left for the owner's approval. The migration is applied by every test run and reversed and re-applied by `MigrationTests` on MySQL and SQLite.
- **Browser:** headless Chrome at 100% zoom, 9 notification states × 6 viewports (1280×590, 1232×590, 1100×590, 1600×740, 1440×800, 360px). States: the student home with a few and with 9+ unread, the list mixed, partly read and paged, keyboard focus, the staff empty state, and the advisor and Super Admin homes.
  - 52/54 clean. The 2 flags are the student home's Quick Access description truncated at 360px, which a render of `origin/main` confirms is pre-existing and unrelated.
  - Re-checked: student complaint pages 66/66, Batch Advisor workspace 60/60, Super Admin workspace 48/48, category pages 48/48.
  - Found and fixed: a duplicate hairline above the list.

**Review follow-up: source validation (PR #16 review)**

- **Found:** `notify()` treated a non-NULL pk plus a matching model label as proof that the source was saved. A probe on a test database created notifications for:
  - an unsaved `ComplaintEvent` with an explicit unused pk;
  - an unsaved one whose pk matched an existing row;
  - a saved one whose row had been removed with raw SQL.
- **Fixed** (`notifications/services._persisted_source_type`): the source must be a Django model instance of the declared model, not marked as new (`_state.adding`), with a pk and a database alias (`_state.db`), and its row must exist on that alias (`_base_manager.using(source._state.db)`). Producers, recipients, attribution, destinations, transactions, immutability and the UI are unchanged. No migration.
- **Tests:** 8 new tests in `NotifyValidationTests`:
  - the four requested cases (unused explicit pk, pk of an existing row, stale row removed by raw SQL inside the test transaction, normal persisted source);
  - `None` and non-model objects;
  - an unsaved instance that carries an alias;
  - a forged instance with no alias;
  - the existence query running on the source's own alias.

  Against the previous implementation, every new test fails except the persisted-source case.
- **Results after the follow-up:**
  - 462/462 on MySQL 8.0.44 in two consecutive `--keepdb` runs; 462 on SQLite with the same 5 MySQL-only skips; the 64 focused notification tests pass on MySQL (61 run and 3 skipped on SQLite).
  - `check`, `makemigrations --check --dry-run`, `compileall` and `git diff --check`: clean.
  - The development database still has `notifications.0001_initial` unapplied, as agreed.

**Not changed / limitations**

- The student home's "Your latest updates" (DEC-303) still awaits seen/unseen tracking.
- There is no retention or clean-up of notifications.
- No other DEC-270 producers yet.
- Notifications reference their source by model label and pk, not a database foreign key. `notify()` verifies that the source row exists when it creates the notification; complaint events are insert-only and cannot be deleted through the ORM.

---

## 2026-11-17 — Complaints Part 4 Stage 2: category and subcategory management

**Context**

- Branch `feat/complaint-category-management` from `main` at `5bed61e` (Stage 1 merged, PR #14). The investigation report's assumptions were confirmed against that commit.
- Owner decisions:
  - historical complaints show the current name, with no snapshots;
  - management lives on portal pages, not Django admin;
  - the last active category can't be deactivated;
  - subcategories may be created under an inactive category;
  - no audit history;
  - complaint usage counts on the index;
  - "(inactive)" shown to staff only;
  - no migration;
  - duplicates treated like MySQL's case- and accent-insensitive collation;
  - a subcategory's parent can't change;
  - no hard deletion of either model.
- **No migrations.**

**What was done**

- **Models:** `CategoryQuerySet` refuses queryset `delete()`, and both models refuse instance `delete()` (`ProtectedRecordError`), even when unreferenced; `update()` is unchanged. `ComplaintSubcategory.save()` refuses a parent change, checked against the stored row.
- **`complaints/category_services.py`:** create, rename, activate/deactivate and move for categories and subcategories. Each operation:
  - re-checks for an active Super Admin and runs in a transaction;
  - normalises names and checks duplicates ignoring case and accents, including inactive records, converting `IntegrityError` into the same field error;
  - appends new records, and for moves locks and renumbers siblings so ties can't block them;
  - never cascades deactivation to subcategory flags, and refuses to deactivate the last active category.
- **Pages:**
  - `/super-admin/complaint-categories/`: index and category pages, every change POST + CSRF with Post/Redirect/Get, subcategory lookups through their parent, no delete route.
  - The "Complaint Categories" navigation item now links here, which also adds it to the Overview's Manage links.
- **Staff labels:** "(inactive)" in staff case details, staff category filters and Super Admin rows; student pages are unchanged.
- **Accessibility fix (shared):** `AccessibleErrorsMixin` now also marks fields when an error is added later with `add_error()`. Service-raised field errors, such as duplicates, previously showed their message but left the input unmarked; this also covers the existing complaint forms. On the category pages, an invalid field is scrolled into view and focused.
- **Two existing tests adapted** to "no hard deletion":
  - the seed-migration test no longer clears the table with `delete()`;
  - category deletion now expects `ProtectedRecordError`.

**Verification**

- Tests: 44 in `complaints/tests/test_category_management.py`, covering:
  - model guards: delete refused, `update()` kept, parent fixed;
  - services: permissions for every operation, normalisation, duplicates (case, accents, inactive, per parent), `IntegrityError`, ordering (ties, boundaries, per parent, student-form order), activation (no cascade, last active, inactive parent, reactivation), historical integrity;
  - pages: access by role and state, 405 on GET, CSRF, 404 for unknown ids and forged pairings, forged values, no delete route, counts, order and disabled boundary moves, page flows, accessible errors including service-raised ones, navigation and the Overview link;
  - staff labels, filtering by an inactive category, and students seeing the current name without the marker.
- **Mutation checks:**
  - disabling the service permission check fails the permission test for every operation and actor;
  - disabling the last-active rule fails both last-active tests;
  - removing the `add_error()` marking fails the service-error assertion.
- **Review follow-up: subcategory parent bypasses.**
  - **Found:** `ComplaintSubcategory.save()` guarded only instance saves. A probe on a test database moved a subcategory to another category through seven paths:
    - `update(category=…)` and `update(category_id=…)`, including through `category.subcategories.update()`;
    - `bulk_update([...], ["category"])`;
    - `other.subcategories.add(sub)` and `.set([sub])`, which in bulk mode update through the base manager;
    - an upserting `bulk_create(update_conflicts=True, update_fields=["category"])`.
  - **Fixed:**
    - `SubcategoryQuerySet` refuses `update()` / `bulk_update()` naming `category` or `category_id`, and upserts that update `category`. Other fields, and inserts, are unaffected.
    - A guarded reverse descriptor on `ComplaintCategory.subcategories` refuses `add()` / `set()` when they would move an existing subcategory of another category. It is used instead of `Meta.base_manager_name`, which would need a migration.
    - **No migration.**
  - **Tests:** 6 new model tests covering each path, plus non-parent updates and legitimate creation still working, and historical complaints keeping their category and subcategory. Against the previous model, the 5 bypass tests fail.
- Results:
  - **After the follow-up:** 398/398 on MySQL 8.0.44 in two consecutive `--keepdb` runs; 398 on SQLite with the same 2 MySQL-only skips; the 50 Stage 2 tests pass on MySQL.
  - **Before the follow-up:** 392/392 on MySQL 8.0.44 in two consecutive `--keepdb` runs; the 44 Stage 2 tests passed on MySQL and SQLite.
  - 392 on SQLite with 2 skipped (MySQL-only: `test_only_one_stale_status_change_succeeds`, `test_concurrent_submissions_get_distinct_references`).
  - `check`: no issues. `makemigrations --check --dry-run`: no changes. `migrate --check`: exit 0. `compileall`: exit 0. `git diff --check`: clean.
- Browser: headless Chrome at 100% zoom, 8 category-page states × 6 viewports (1280×590, 1232×590, 1100×590, 1600×740, 1440×800, 360px) = 48/48 clean. The states were: the index, an active category, a long-named category, an inactive category, the last active category, a create error, a subcategory error and keyboard focus.
  - Re-checked: student complaint pages 66/66, Batch Advisor workspace 60/60, Super Admin workspace 48/48.
  - Found and fixed during the checks: name links under 44px on phones, inline buttons misaligned beside an error, errors below the fold not brought into view, and the unmarked service-raised field errors.

---

## 2026-11-17 — Complaints Part 4 Stage 1: Super Admin workspace and owner assignment

**Context**

- Issue #13; branch `feat/super-admin-complaints-workspace` from `main` at `4348b15` (Part 4 specification, PR #12). Stage 1 only: no categories, notifications, analytics or academic terms.
- **No migrations.** `Complaint.responsible`, the `RESPONSIBLE_CHANGED` event and `services.assign_responsible` already existed from Part 1.

**What was done**

- A department-wide Super Admin complaints workspace at `/super-admin/complaints/`, with Respond, Update status and owner actions. Details are in `docs/technical/COMPLAINTS.md` section 5.
- **List:**
  - search by reference, title, student name or SAP ID;
  - exact-cohort (every known cohort), status (the spec's list, All by default), category (including inactive) and owner (Any, Unassigned, current owners) filters;
  - a factual sort, pagination, and the list state kept across links and redirects;
  - three distinct empty states: no complaints, no matches and an empty selected cohort.
- **Case:** the Part 3 case pane, plus the responsible owner in the context, staff history including owner changes, and an owner panel. The panel offers the active Batch Advisors of the exact cohort or "Take it over yourself"; choosing the current owner is a no-op with a message.
- **Owner eligibility:** the rule is now one function, `services.is_eligible_owner`, used by `assign_responsible` (behaviour unchanged). `services.eligible_advisors` feeds the form.
- **Shared engine:** the Part 3 workspace was generalised into `complaints/workspace.py` (a `Workspace` configuration per role) with thin `advisor_views.py` and `admin_views.py`. Templates moved to `templates/complaints/workspace/`. Batch Advisor behaviour is unchanged, and all Part 3 tests pass without modification.
- The Super Admin "Complaints" navigation item links to the workspace.

**Interpretations to confirm (consistent with both the spec and Issue #13)**

- **Batch Advisor history:** owner-change history appears in the **Super Admin** workspace only. The spec says BAs "may" see it; the issue says existing BA behaviour stays intact. Enabling it for BAs is a one-line change.
- **Take-over:** the owner form offers eligible BAs and taking it over yourself (DEC-310 "a Super Admin taking it over"), not assignment to another Super Admin. The service still accepts any active Super Admin, as before.
- **Status filter:** All, Received, Under Review, Resolved and Rejected, as listed in spec section 3.1. The BA workspace keeps its additional "Open" option.

**Verification**

- Tests: 34 new tests in `complaints/tests/test_super_admin_workspace.py`, covering:
  - access by role and state, POST-only actions and unknown references;
  - navigation, department-wide listing, rows, search including title and SAP ID;
  - exact cohort filter and choices, forged values, the empty cohort and empty department;
  - status, inactive-category and owner filters; sort, pagination and list state;
  - full staff history with owner changes, unassigned state, Super Admin respond/status, stale status and untouched originals;
  - eligible choices, one event per real change, the same-owner no-op, reassign and take-over;
  - wrong-cohort, student, inactive and other-Super-Admin rejection, and the service-level rejection;
  - the no-longer-eligible label, non-owner advisors keeping their actions, owners gaining nothing outside their cohort, and BA and student views unchanged;
  - no queue or priority language.
- **Mutation check:** forcing owner changes into every staff history fails both the new BA-unchanged test and the existing Part 3 history test.
- Results:
  - 348/348 on MySQL 8.0.44 in two consecutive `--keepdb` runs; the 34 Stage 1 tests pass on MySQL and SQLite.
  - 348 on SQLite with 2 skipped (MySQL-only: `test_only_one_stale_status_change_succeeds`, `test_concurrent_submissions_get_distinct_references`).
  - `check`: no issues. `makemigrations --check --dry-run`: no changes. `migrate --check`: exit 0. `compileall`: exit 0. `git diff --check`: clean.
- Browser: headless Chrome at 100% zoom, 8 Super Admin states × 6 viewports (1280×590, 1232×590, 1100×590, 1600×740, 1440×800, 360px) = 48/48 clean. The states were: the list, filtered list, empty cohort, owned case, unassigned case, closed case, owner error and owner-select focus. The checks covered overflow, clipped or covered content, fonts, outside requests, touch targets and focus. The 10 Part 3 Batch Advisor states, re-run after the template move: 60/60 clean.

---

## 2026-11-17 — Complaints Part 4: scope and specification

**Owner-approved decisions**

- O27 (complaint owner): manual designation by a Super Admin; no automatic assignment. Eligible owners are active advisors assigned to the exact cohort, or a Super Admin taking over. Existing cohort-advisor access remains unchanged (DEC-310). The separate BA-routing question for collective issues, Student Voice and meetings remains open.
- O28: cancellation requests remain record-only; no status change or approval/decline workflow (DEC-311).
- O33: no response-required classification or “Waiting for you” queue (DEC-312).
- O31: resolved vs not resolved classification is fixed, with rejected complaints separately identified (DEC-313).
- O32: one academic-term reporting window, using submission date and explicit displayed dates (DEC-314).
- O25: suppress cohort breakdowns below five active students and apply complementary suppression (DEC-315).

**Specification**

- Added COMPLAINTS_PART4_SPEC.md covering Super Admin complaint oversight, category management, in-app notifications, privacy-safe analytics, permissions, tests and implementation sequence.
- Corrected the status at a glance: Part 3 was merged through PR #11; it is not awaiting review.
- No Part 4 implementation has started. The specification must be reviewed and merged before Claude Code receives the implementation task.

---

## 2026-11-17 — Complaints Part 3: Batch Advisor complaints workspace

**Context**

- Branch `feat/advisor-complaints-workspace` from `main` at `ca07b44`, which includes the registration fix (PR #9, `28bfd1e`) and the approved specification (PR #10, `ca07b44`).
- Implements `docs/technical/COMPLAINTS_PART3_SPEC.md` with the owner-approved decisions P3-1 to P3-8. There are no model or migration changes.

**What was done**

- One responsive workspace for Batch Advisors at `/advisor/complaints/` and `/advisor/complaints/<reference>/`, with POST routes for Respond and Update status. Details are in `docs/technical/COMPLAINTS.md` section 3.
- **Access:** `batch_advisor_required` on every view. The list starts from `visible_complaints` (exact cohorts); every case, on GET and POST, is loaded with `get_visible_complaint` (the same 404 for an out-of-cohort reference as for an unknown one). The cohort filter accepts only the advisor's own assignments.
- **List:**
  - a true-count headline;
  - search by reference, student name or SAP ID (P3-3);
  - cohort, status (All by default, P3-4) and category filters, and a sort by latest activity or newest submitted;
  - 20 per page, with the list state kept across links and redirects;
  - factual "Cancellation requested" and "Reopened by student" labels (P3-2).
- **Case:**
  - Header, status journey and the student's original complaint.
  - History newest first, with names and roles (P3-7; students keep oldest first). Owner changes are hidden (O27).
  - Context: name and SAP ID, no email (P3-1); the cohort at submission only (P3-5); and the active advisors of that exact cohort.
  - Separate Respond and Update status forms (DEC-305). The status form offers only the allowed transitions, requires a resolution note or rejection reason, and sends the status the advisor saw.
- **`services.change_status(..., expected_status=None)` (P3-6):** if given, it is compared under the existing row lock, and a stale change is refused with code `stale_status`. Existing callers are unchanged.
- **Navigation and overview:** the Batch Advisor "Complaints" rail and drawer item links to the workspace and stays current on its sub-pages. Each assigned-cohort card on the advisor overview opens the workspace filtered to that exact cohort (P3-8).
- **Presentation:** `student_timeline` and the new `staff_timeline` share one event mapping; the student output is unchanged.
- **Accessibility fixes found during this work:**
  - The shared field include rendered help text with an id that did not match the `aria-describedby="<id>_helptext"` Django adds, and on errors the mixin replaced that reference. Help text is now linked, and stays linked alongside the error.
  - Radio buttons had no visible keyboard focus, because Bootstrap's `.form-check-input:focus` removed the outline. Restored.
  - Two Part 2 assertions were updated to the stricter, correct `aria-describedby` value.

**Verification**

- Tests: 45 new tests in `complaints/tests/test_advisor_workspace.py`, covering:
  - access by role and state, and exact-cohort and cross-batch isolation;
  - shared cohorts, and out-of-cohort references returning the same 404 on GET and both POSTs;
  - forged cohort filters, search, filters, sorting, pagination and the list state;
  - responses, allowed transitions and mandatory notes;
  - stale `expected_status` in the view and the service;
  - history order, hidden owner changes and the context panel;
  - navigation and cohort links, and the absence of a queue, owner or cancellation controls;
  - a real two-connection stale-status race on MySQL.

  With the safeguard disabled, the four stale-status tests fail, including the MySQL race.
- Results:
  - 314/314 on MySQL 8.0.44 in two consecutive `--keepdb` runs; the focused advisor tests pass 45/45 on MySQL.
  - 314 on SQLite with 2 skipped (the MySQL-only concurrency tests); 45 advisor tests, with 1 skipped.
  - `check`: no issues. `makemigrations --check --dry-run`: no changes. `migrate --check`: exit 0. `compileall`: OK. `git diff --check`: clean.
- Browser: headless Chrome at 100% zoom, 10 workspace states × 6 viewports (1280×590, 1232×590, 1100×590, 1600×740, 1440×800, 360px) = 60/60 clean. The states were: the list, filters, case, cancellation case, closed case, both error states, keyboard focus, the advisor overview and no assignments. The checks covered overflow, clipped or covered content, fonts, outside requests, touch targets and focus.
  - Part 2 student pages re-checked: 66/66 clean.
  - Found and fixed: missing radio focus, truncated filter selects and search placeholder in the narrow list pane, the student name repeated in the header and context, and 41px buttons on phones.

**Limitations**

- O27, O28 and O33 remain open, as specified.
- No seen/unseen tracking and no notifications (DEC-270).
- Super Admin complaint oversight is Part 4.

---

## 2026-11-17 — Complaints Part 2: student pages

**Context**

- Branch `feat/student-complaints-frontend` from `main` at `06bbc2a` (PR #7 merged). Built on the PR #6 shell and the Part 1 services; no model or migration changes.
- The repository has no `AGENTS.md`; the decision register, design plan and this log were followed. DEC-031 names the student list "My Submissions", so the page uses that name; the navigation item stays "Complaints" (DEC-304).

**What was done**

- Three student pages under `/student/complaints/`: My Submissions (list), Submit a complaint, and Complaint details, plus POST actions for further information, "Still not resolved" and a cancellation request. Routes and behaviour are documented in `docs/technical/COMPLAINTS.md`.
- **Access:** `student_required` on every view, and `get_visible_complaint` for every complaint, so another student's reference returns the same 404 as an unknown one. Every change goes through `complaints.services`. The form has no student or cohort fields.
- **Submission:**
  - Active categories and their active subcategories only, grouped so the list works without JavaScript, with the cross-category check repeated in the form.
  - A non-blocking duplicate notice built from the student's own open complaints (`possible_duplicates`).
  - Post/Redirect/Get to the new complaint, a message giving its reference, and the button disabled after the first click.
- **Details:**
  - Reference, status, category, submission time, the cohort at submission, the status journey, and the original description shown read-only.
  - History in plain language, with staff shown by role only and owner changes hidden from students (O27).
  - Actions: further information is always available; "Still not resolved" appears only when Resolved; a cancellation request is offered for open complaints until one is recorded, and only records it (O28). If the service refuses an action because of the complaint's state, it is explained in a message and nothing changes.
- **Integration:** the student "Complaints" navigation item and the "Submit a complaint" Quick Access action now link to these pages; Complaints stays marked as current on its sub-pages. `AccessibleErrorsMixin` was extracted from the registration form so both forms share the ARIA error handling.
- **Styles:** new components in `static/css/app.css` built from the existing tokens: filter chips with the ink selection, hairline list rows, status journey, original-description block, timeline and action panels. `static/js/complaints.js` provides progressive enhancement only.

**Verification**

- Tests: 32 new tests in `complaints/tests/test_student_views.py`, covering:
  - access by role, anonymous, deactivated and unregistered users;
  - another student's reference, and POST-only actions;
  - submission, cohort from the profile, inactive categories, mismatched or unknown subcategories, an entirely empty POST, kept values and ARIA errors, overlong input, and the duplicate notice;
  - list, filter, pagination and empty states;
  - details, timeline privacy and the three actions, including refused actions;
  - navigation integration.
- Two PR #6 tests that asserted "Complaints" and "Submit a complaint" were not yet links were updated to the new behaviour; Student Voice and Meetings are still checked as unavailable.
- Review fix: an entirely empty POST to the submission page created an unbound form (an empty `QueryDict` is falsey), so the blank form came back without errors. The form is now bound on every POST, and a regression test covers it.
- Results: 268/268 on MySQL 8.0.44 in two consecutive `--keepdb` runs, and 268 on SQLite with 1 skipped (the MySQL-only concurrency test). `check`: no issues. `makemigrations --check --dry-run`: no changes. `migrate --check`: exit 0.
- Browser: headless Chrome at 100% zoom at 1280×590 (DEC-307), 1232×590, 1100×590, 1600×740, 1440×800 and 360px. 11 page states (empty, filtered and full lists; the form, its errors and the duplicate notice; received, resolved, cancellation-requested, error and keyboard-focus details) × 6 viewports = 66 combinations. All have no horizontal overflow, no clipped or covered content, local fonts, no outside requests, and touch targets of at least 44px on phones.
  - Found and fixed during the checks: status filter chips scrolling out of view at 360px (now wrap), dates breaking mid-date, a dangling journey connector on small phones, and controls under 44px on phones.

**Limitations**

- O27, O28 and O33 remain open; see `docs/technical/COMPLAINTS.md` section 3.
- The student home's "Your latest updates" does not yet list complaint activity (needs seen/unseen tracking, DEC-303).
- Batch Advisor and Super Admin complaint screens, category management, notifications and analytics are Parts 3–4.

---

## 2026-11-17 — Complaints Part 1: backend foundation

**Context**

- Branch `feat/complaints-foundation`, from `main` at `5b87417` (after PR #5). Backend only: no views, URLs, templates or admin screens.
- Implements DEC-030, DEC-031 and DEC-220 to DEC-230 within the exact-cohort rules of DEC-020, DEC-204, DEC-205 and DEC-210.

**What was done**

- New `complaints` app.
  - `ComplaintCategory` and `ComplaintSubcategory`: database-managed and deactivated rather than deleted (DEC-220). Migration `0002_initial_categories` adds Academic, Non-academic, Personal/Wellbeing and Other as ordinary rows; no code depends on those names.
  - `Complaint`:
    - the submitting student;
    - the exact cohort at submission (batch, semester and section foreign keys, kept if the student's profile later changes);
    - category, optional subcategory, title, original description and status;
    - an optional responsible owner;
    - timestamps.
  - Reference IDs such as `CMP-2026-00042` are derived from the primary key inside the submission transaction, so concurrent submissions cannot collide, and the column is unique.
  - Statuses: Received, Under Review, Resolved and Rejected (DEC-221), with a database check. There are no priority or overdue states (DEC-226).
  - `ComplaintEvent`: an immutable history entry for submission, status changes, "Still not resolved", responses, further information, cancellation requests and changes of responsible owner. Database checks require a rejection reason and a resolution note, text on responses and further information, and both ends of every status change.
  - Every foreign key uses PROTECT, and complaints and events refuse `save` edits and `delete`. Deactivating academic structure or a category keeps every complaint and its history (DEC-210).
- `complaints.services`: every state change runs in a transaction, locks the complaint row, checks permission and records an event.
  - Submission takes the cohort from the student's own registered profile, never from the request, and requires it to be active. The category and subcategory must be active.
  - Status changes by a cohort Batch Advisor or the Super Admin: Received → Under Review, Resolved or Rejected; Under Review → Resolved or Rejected.
  - Responses never change the status.
  - The student's "Still not resolved" returns a resolved complaint to Under Review (DEC-222).
  - Further information keeps the original description (DEC-223).
  - A cancellation request is recorded only (DEC-224, O28).
  - The Super Admin can assign, reassign or take over the responsible owner (DEC-227, DEC-228).
  - Possible duplicates are the student's own open complaints in the same category. They are a warning only and never block a submission (DEC-225).
- `complaints.permissions` (DEC-229, DEC-205):
  - **Students:** only the complaints they submitted.
  - **Batch Advisors:** only complaints whose stored cohort exactly matches one of their assignments, so shared cohorts work and partial matches grant nothing.
  - **Super Admins:** everything.
  - **Inactive users:** nothing.
  - `get_visible_complaint` returns 404 for anything outside the user's scope.
- `accounts.permissions`: the exact-cohort filter is now public (`assigned_cohort_filter`) so complaints reuse it rather than duplicate it.

**Tests**

- 46 new tests in `complaints/tests/`:
  - submission and validation;
  - reference uniqueness, including 8 concurrent submissions on separate MySQL connections;
  - exact-cohort access, including the same semester and section in another batch, partial matches, shared cohorts and unassigned advisors;
  - changing a reference to reach another student's complaint;
  - the status rules and mandatory notes, "Still not resolved", further information and immutable history;
  - cancellation requests, and the responsible owner;
  - deactivated structure and categories.
- Results: 216/216 on MySQL 8.0.44 (`manage.py test --keepdb`) and 216 on SQLite with 1 skipped (the concurrency test needs row locking, which SQLite lacks).
- `manage.py check`: no issues. `makemigrations --check --dry-run`: no changes. `migrate --check`: exit 0, with only the known allauth W036 warning.

**Review follow-up: bulk ORM operations (2026-11-17)**

- Found: the instance-level `save()`/`delete()` guards did not cover Django's bulk paths. A probe on a test database confirmed that these went through:
  - `QuerySet.update()`, including through `complaint.events`;
  - `bulk_update()`;
  - `QuerySet.delete()`;
  - an upserting `bulk_create(update_conflicts=True)`.

  Together they could rewrite or delete history, change a complaint's status or description, or delete a complaint that had no events yet.
- Fixed: `Complaint` and `ComplaintEvent` now use a `ProtectedQuerySet` that refuses `update()`, `bulk_update()`, `delete()` and upserting `bulk_create()`, raising `ProtectedRecordError` (a `ValidationError`).
  - Plain inserts still work.
  - The services are unaffected because `Model.save()` updates rows through Django's internal `_update()`.
  - No migration was needed.
- Scope: this covers the application's ordinary ORM paths. It does not stop raw SQL, direct database access or Django's private `_base_manager` / `_update()` APIs.
- Tests: 16 new tests in `complaints/tests/test_immutability.py` run each real operation and check that the database is unchanged. Two existing tests were updated to the new mechanism with the same assertions: the duplicate-reference test now collides through `save()`, and complaint deletion now expects `ProtectedRecordError`. Run against the previous models, 12 of the 16 new tests fail; the other 4 cover paths that were already protected.
- Results: 232/232 on MySQL 8.0.44 in two consecutive `--keepdb` runs, and 232 on SQLite with 1 skipped. `check`: no issues. `makemigrations --check --dry-run`: no changes. `migrate --check`: exit 0, with only the known allauth W036 warning.

**Review follow-up: detached instances (2026-11-17)**

- Found: the instance guards trusted in-memory state. A newly constructed object given an existing primary key has `_state.adding=True` and none of the description captured on load, so `save()` updated the stored row. Reproduced on a test database:
  - `ComplaintEvent(pk=existing, ..., created_at=...).save()` rewrote an event's kind and message;
  - `ComplaintEvent(pk=existing, message=...).save(update_fields=["message"])` rewrote a message;
  - `Complaint(pk=existing, ...).save()` and `Complaint(pk=existing, description=...).save(update_fields=["description"])` replaced the original description.

  A bare detached event save was stopped only incidentally, by the NOT NULL check on `created_at`.
- Fixed:
  - `ComplaintEvent.save()` refuses `update_fields` and any primary key that already exists, and always inserts (`force_insert=True`), so it can never update a row. A duplicate key racing in between fails in the database.
  - `Complaint.save()` compares the description with the stored row whenever the save could write it, instead of relying on the value captured on load (the `from_db` hook was removed). The services save with `update_fields` that exclude `description`, so they make no extra query.
  - No migration was needed.
- Scope: the `Complaint` guard protects the original description only, as specified. A detached `save()` can still change other complaint fields; status and owner changes are meant to go through `complaints.services`. Raw SQL and Django's private APIs remain outside what the ORM can protect.
- Tests: 4 new tests in `complaints/tests/test_immutability.py` check that the database is unchanged after each refused attempt. Run against the previous models (`b344091`), the 3 detached-instance tests fail; the fourth (saving with an unchanged description is allowed) passes on both, as intended. No test was removed or skipped.
- Results: 236/236 on MySQL 8.0.44 in two consecutive `--keepdb` runs, and 236 on SQLite with 1 skipped (the MySQL-only concurrency test). `check`: no issues. `makemigrations --check --dry-run`: no changes. `migrate --check`: exit 0.

**Limitations from open decisions**

- O27: no responsible owner is assigned automatically; only the Super Admin sets it. Every Batch Advisor of the cohort can act on a complaint until O27 decides whether actions are limited to the owner.
- O28: a cancellation request is only recorded. It does not change the status, and nobody approves or rejects it.
- O33: no event is classified as needing an advisor response, and there is no "Waiting for you" queue.

**Not done (later parts)**

- Student screens (submit, My Submissions, history), Batch Advisor and Super Admin complaint screens, category management for the Super Admin, in-app notifications for status changes and responses (DEC-070, DEC-270), and the DEC-281 analytics.

---

## 2026-11-17 — Production frontend milestone 1 (PR #6)

**Context**

- Built from the approved Design D direction (DEC-300 to DEC-307) on the existing Django views. The backend, permissions and product scope were not changed.

**What was done**

- Self-hosted Inter and Newsreader (variable woff2, with their OFL licences) and vendored Bootstrap 5.3.3. Pages make no requests to outside sites.
- Base, sign-in and application layouts using the Forest Light tokens, a skip link and the ink active-navigation indicator (DEC-301).
- Role navigation from one context processor (`accounts/navigation.py`):
  - Student: sidebar; on phones, a bottom bar with exactly four destinations and no "More" (DEC-304).
  - Batch Advisor: 72px icon rail; drawer on phones.
  - Super Admin: grouped sidebar with no Statistics destination (DEC-306); drawer on phones.
  - Destinations whose module is not built yet are shown as unavailable ("Soon") and are not links.
- Student Dashboard: date, exact cohort, greeting, a personal summary calculated from the student's own updates (`accounts/presentation.py`; "Nothing needs your attention today." when there are none, DEC-303), three Quick Access actions shown as unavailable until their modules exist, and empty states.
- Batch Advisor and Super Admin overviews with empty states and no invented figures. The Super Admin page links to the existing admin pages for Students, Batch Advisors and Academic Structure. The DEC-281 analytics are not built yet.
- Sign-in, sign-in denied and registration restyled. Registration shows the SAP ID taken from the email, and invalid fields carry `aria-invalid` and `aria-describedby`.
- The django-allauth pages a user can reach (sign-out confirmation, sign-in cancelled, sign-in error, account inactive) use the portal layout; Django messages are shown on every page.
- Newsreader + Inter follow the preferred direction in O30, which remains open. Only the Light theme is implemented (O34 open).

**Review and merge**

- A final review before merging found and fixed: messages missing on the sign-in pages, unstyled allauth pages, navigation landmarks and decorative icons, phone touch targets below 44px, the phone bottom bar floating on short pages, and two visual defects.
- Merged into `main` by the owner on 2026-11-17 (00:35 Asia/Karachi) as merge commit `c9a4cd3972b238aa21a00b0e9f07b332d3b10129`, bringing in `7355fb4`, `fa3c240` and `4dc7efa`.

**Verification (local, on the merged `main`)**

- Tests: 170/170 passing on MySQL 8.0.44 (`manage.py test --keepdb`) and 170/170 on SQLite. These include 34 frontend tests.
- `manage.py check`: no issues. `makemigrations --check --dry-run`: no changes. `migrate --check`: clean. `findstatic` finds the stylesheet, Bootstrap and the fonts.
- Before merging, every page state was checked in headless Chrome at 100% zoom at 1280×590 (HP EliteBook 840 G8 in Opera, DEC-307), 1232×590, 1100×590, 1600×740, 1440×800 and 360px wide: no horizontal overflow, local fonts loaded, no outside network requests. Headless viewports approximate the device; the physical laptop was not used.

**Not done / still unverified**

- Sign-in with a real UOL Google account has not been tested; all OAuth tests use simulated Google responses.
- Production deployment: static files need `collectstatic` and a serving setup, and `check --deploy` still reports the HTTPS settings (HSTS, SSL redirect, secure cookies) and `DEBUG` as unset for production. Nothing has been deployed.

---

## 2026-11-16 — Design phase: Forest palette and Design D

**Context**

- The owner reviewed the Frontend Design Research Report (kept outside the repository) and asked for rendered comparisons before choosing a palette or page designs.

**What was done**

- Palette: Forest and Indigo, light and dark, were compared in a development-only preview (PR #4). The comparison found that the Forest current-navigation tint and the Resolved badge are nearly identical in Forest Light, which led to the ink active-navigation indicator. The owner approved Forest (Light and Dark). PR #4 was later closed as obsolete without merging; its preview page is not in `main`.
- Key pages: low-fidelity explorations and then Design D were prepared for the Student Dashboard, the Batch Advisor Complaints workspace and the Super Admin Overview (PR #5). The owner approved Design D as the visual reference for production.
- Laptop zoom investigation: the earlier "too enlarged" feel at 100% zoom came from fixed pixel sizes composed for about 1440×900. The fix is fluid, height-bounded display sizes and container queries, and the HP EliteBook 840 G8 in Opera at 100% (about 1280×590) became the acceptance target.
- Recorded DEC-300 to DEC-308 in `DECISIONS.md` (section 1.13) and the open items O30 to O34, with notes on O18 and O25. Written specification: `docs/design/DESIGN_PLAN.md`.

**Documentation cleanup (2026-11-17, PR #5)**

- On the owner's instruction, the design-phase HTML, CSS and JavaScript prototypes were removed from PR #5 and not replaced. `DESIGN_PLAN.md` is kept as the written production specification, with the Forest Dark values copied in from the palette comparison so DEC-301's fixed values stay recorded.
- PR #5 was brought up to date with `main` by merging `main` into it (no rebase or force-push).

**Not decided**

- O25 (small-cohort privacy threshold), O30 (final typography), O31 (resolved vs not resolved), O32 (reporting window), O33 ("Waiting for you" events) and O34 (System theme option) remain open. Their recommendations are not decisions.

---

## 2026-11-16 — Authentication and account foundation

**Context**

- PR #2 (development log update) was merged into `main` as merge commit `6fc52b7`. This work branches from that commit as `feat/auth-account-foundation`.
- The full design is documented in `docs/technical/AUTHENTICATION.md`.

**What was done**

- Google sign-in for every role through one shared page, using django-allauth 65.22.1 (DEC-010, DEC-200). This is a proposed resolution of O3 and needs the owner's approval as a new dependency.
  - Sign-in starts with a CSRF-protected POST and uses `state` and PKCE.
  - ID tokens are checked for issuer, audience and expiry.
  - Google's email must be verified, and its hosted-domain (`hd`) claim must be present and allowed by default.
  - Password login, sign-up and reset are disabled. The Django admin's password login page redirects to Google sign-in.
- Identity rules (DEC-011, DEC-012, DEC-013):
  - Only valid student emails (eight-digit SAP ID at `@student.uol.edu.pk`) can sign up.
  - Super Admin-created accounts are activated by linking on first sign-in.
  - Unknown staff emails and personal Google accounts are refused.
  - Each account is bound to one Google identity. A different identity, or a changed Google email, is refused.
- Student registration after first sign-in (DEC-201): full name, batch, semester and section. The SAP ID is taken from the email and the department defaults to Software Engineering. Registration is one-time (DEC-202). Unregistered students are kept on the registration page whatever URL they request.
- New `academics` app: database-managed batches, semesters and sections that are deactivated rather than deleted (DEC-020, DEC-210).
- Account model:
  - Review M1: the role is the single source of truth. Only the Super Admin holds `is_staff`/`is_superuser`, enforced on every save.
  - Review M2: `create_user()` validates the email format, the role, the role's email rule and uniqueness.
  - New `User.full_name`, a `StudentProfile` with a unique SAP ID, and an `AdvisorAssignment` linking a Batch Advisor to a semester and section, later scoped to batch + semester + section (see the follow-up below). One advisor can hold several assignments, and several advisors can share a section (DEC-204).
  - `StudentProfileChange` audits the Super Admin's corrections (DEC-211).
  - Accounts are deactivated, not deleted (DEC-212).
- Staff provisioning in the Django admin: the Super Admin creates Batch Advisor accounts from name and official email, with no password, and assigns semesters and sections (DEC-013). There is no Batch Advisor self-registration.
- `manage.py bootstrap_super_admin` creates the initial Super Admin (DEC-203). It runs only when none exists, requires a staff email and sets no password. This is a proposed resolution of O26.
- Reusable access control in `accounts.permissions`: role decorators, plus `visible_student_profiles()` and `can_access_section()` scoped by assignments. `can_access_section()` was renamed to `can_access_cohort()` in the follow-up below.
- Session hardening: 8-hour sessions, HttpOnly and SameSite=Lax cookies, and secure cookies whenever `DEBUG` is off.
- Placeholder role pages only. No dashboard interfaces were built (DEC-120).
- Migrations `academics/0001_initial` and `accounts/0002_account_foundation`, both additive, applied to the development database.

**Tests**

- The test suite was reorganized into `accounts/tests/` and has 118 tests. It covers: email normalization, student email validation, account creation and duplicate prevention, the Google sign-in callback (the real flow with only the token exchange stubbed), role consistency, staff provisioning, the Super Admin bootstrap, registration, and access-control boundaries.
- The original 32 tests were carried over. Their sample data was updated where M2 validation now rejects it, for example student emails without a SAP ID, and duplicates now raise `ValidationError` before reaching the database. The removed admin email-change test was replaced by a test that email and role are fixed after creation.
- A mutation check switched off each protection in memory: the identity rules, role sync, manager validation, the registration gate, the sign-up guard and the hosted-domain check. In every case the relevant tests failed, and with nothing switched off none failed.

**Verified (2026-11-16)**

- All 118 tests passed on MySQL 8.0.44 (`--keepdb`).
- All 118 tests passed on SQLite.
- `manage.py check`: no issues.
- `manage.py makemigrations --check --dry-run`: no changes detected.
- `manage.py migrate --check`: all migrations applied.

**Follow-up: assignments scoped to the exact cohort (owner decision, 2026-11-16)**

- Owner decision: Batch Advisor assignments are scoped to the exact combination of batch, semester and section. Recorded in `DECISIONS.md` as DEC-205.
- `AdvisorAssignment` now requires a batch. Uniqueness changed from advisor + semester + section to advisor + batch + semester + section. Several advisors can still share a cohort, and one advisor can hold several cohorts.
- `visible_student_profiles()` and `can_access_cohort()` (renamed from `can_access_section()`) grant access only when batch, semester and section all match. The admin assignment forms and lists include the batch.
- New migration `accounts/0003_advisor_assignment_batch`. `0002` was already applied to the development and test databases, so it was not edited.
  - Its first step refuses to continue if any assignments exist, because a batch cannot be inferred safely. It does this before any schema change, since MySQL cannot roll back schema changes, and lists the assignments so they can be re-created with a batch.
  - The first version of this guard ran after the column was added, which would have left the documented recovery steps unworkable on both databases. It was moved before shipping.
  - The development database had no assignments, and `0003` was applied to it.
- Tests: 125 in total, up from 118.
  - New: exact-cohort scoping, including the same semester and section in another batch and every partial match; several cohorts per advisor; a shared cohort; batch required; duplicate cohort rejected; admin cohort assignment.
  - Two migration tests run against the real test database: the refusal leaves the schema and data unchanged, and the normal path produces the new constraint.
- A mutation check made the scope helpers ignore the batch. The 4 batch-specific tests failed, and with nothing changed none failed.

**Verified after the follow-up (2026-11-16)**

- All 125 tests passed on MySQL 8.0.44 (`--keepdb`). A second consecutive run also passed, confirming the test database is consistent after the migration tests.
- All 125 tests passed on SQLite.
- `manage.py check`: no issues.
- `makemigrations --check --dry-run`: no changes detected.
- `migrate --check`: all migrations applied.

**Final review of PR #3 (2026-11-16)**

- Decision references: the docstrings of `AdvisorAssignment`, the cohort scope helpers and migration `0003` now cite DEC-205. Only comments changed; `makemigrations --check` confirmed the migration's operations are unchanged.
- Session edge cases reviewed and covered by 11 new tests:
  - A user signed in through the real Google flow, whose session uses allauth's backend, loses access on the next request after deactivation. allauth's backend inherits Django's active-user check.
  - A student deactivated during registration cannot complete it, and no profile is created.
  - A reactivated student signs in again with the same Google identity.
- Two defects found and fixed. Both were confirmed by failing tests before the fix.
  - Two simultaneous registration submissions caused a server error. The one-profile-per-student constraint already prevented a duplicate profile, so no data was affected. The view now treats the constraint violation as "already registered".
  - The last active Super Admin could be deactivated in the admin. That would have left no one able to manage the portal, and `bootstrap_super_admin` refuses while any Super Admin account exists. The admin now refuses to deactivate the last active Super Admin. This is a safeguard, not a product change.
- Multiple Super Admins verified:
  - After bootstrap, an existing Super Admin can create further Super Admins in the admin. They get a staff email, no password and the admin flags, and are activated by their first Google sign-in.
  - Bootstrap still refuses once any Super Admin exists.
  - A Super Admin can be deactivated while another active one remains.
- Full diff reviewed for security, data integrity, migration safety and consistency with `DECISIONS.md`. No blocking code issues were found. The remaining blockers are external or approvals, listed in the PR.
- Migration note: reversing `0003` drops the batch column, losing the batch of every assignment. The reversal also fails if one advisor holds the same semester and section in two batches, because the old unique constraint cannot be restored. Do not reverse it once cohorts are in use.
- Verified: 136 of 136 tests passed on MySQL 8.0.44 (`--keepdb`) and on SQLite. `check`, `makemigrations --check` and `migrate --check` were clean.

**Owner approvals (2026-11-16)**

- django-allauth is approved as a dependency. This settles the library choice for O3. O3 remains open for the OAuth client setup and credential handling, which need a real Google Cloud client.
- Multiple Super Admins are approved, provided at least one remains active. Recorded as DEC-206. The implementation already enforces this: the admin refuses to deactivate the last active Super Admin.
- The owner authorized merging PR #3. UOL's organizational verification is not a precondition for merging.

**Not verified**

- Google sign-in with a real UOL account. No OAuth client is configured, and no external verification has been done. See `AUTHENTICATION.md` section 8.

**Open questions for the owner**

- O2: confirm the official staff email domain or domains. `uol.edu.pk` is assumed.
- O2: confirm that UOL uses Google Workspace for both domains, that UOL permits the app, and the actual `hd` claim values.
- ~~Advisor assignments are recorded per semester and section, without the batch.~~ Resolved: the owner confirmed that assignments are scoped to batch + semester + section (follow-up below).
- ~~Can more than one Super Admin exist?~~ Resolved: the owner approved multiple Super Admins, provided at least one remains active. Recorded as DEC-206.
- Email and role are fixed after an account is created. Confirm that the Super Admin should not change them, or define a procedure for email changes.
- Session length of 8 hours: confirm or change.
- MySQL warning W036: MySQL cannot enforce two conditional unique constraints on allauth's `EmailAddress` table. The portal's identity checks do not depend on that table.

---

## 2026-11-16 — Django foundation completed and verified

**Task 01 — Foundation review, admin, requirements and tests**

- Reviewed the existing foundation. The custom `accounts.User` model (email login, no username field, roles Student, Batch Advisor and Super Admin), its initial migration and `AUTH_USER_MODEL = "accounts.User"` were consistent with each other and with `DECISIONS.md`. CR/GR are not roles in the model, consistent with DEC-016.
- Registered the custom User model in the Django admin (`accounts/admin.py`). Because the model has no username field, the admin uses creation and change forms based on email. The list shows email, name, role, active, staff and date joined; filters cover role, active, staff and superuser; search covers email, first name and last name. Accounts can be created without a usable password.
- Added `requirements.txt` with the exact packages installed in the project environment: Django, mysqlclient and python-dotenv, plus their dependencies asgiref, sqlparse and tzdata.
- Added 19 initial tests for `PortalUserManager`, email-based user creation, superuser creation, role defaults and the User admin.

**Task 02 — Full lowercase email normalization**

- Rule: every email address is normalized to lowercase in full, with surrounding whitespace stripped, before account creation, validation and lookup. Example: `Ali.Khan@Student.UOL.edu.pk` becomes `ali.khan@student.uol.edu.pk`. Django's default lowercases only the domain.
- Implemented once, in `PortalUserManager.normalize_email()`. It applies to:
  - account creation through `create_user()` and `create_superuser()`;
  - model validation, because Django's `AbstractUser.clean()` calls the manager's `normalize_email()`;
  - the admin add and change forms, which normalize the email before the uniqueness check;
  - synchronous authentication lookups, through a `get_by_natural_key()` override;
  - asynchronous authentication lookups, through an `aget_by_natural_key()` override. A code review found that Django 5.2's async lookup does not call the synchronous method, so it needed its own override.
- `create_user()` now checks for an empty email after normalization, so an address made only of whitespace is rejected.
- Email format validation and uniqueness checks are unchanged. No model fields, roles, permissions or migrations changed.
- The rule is enforced in the application and does not depend on MySQL's case-insensitive collation.
- Tests: removed the one test that asserted the old domain-only behaviour and added 14, bringing the total to 32. They cover uppercase and mixed-case addresses through the manager, model validation, the admin add and change forms, and the sync and async lookups. A check that removed the async override confirmed that the async tests fail without it.

**Task 03 — MySQL test database**

- Django's tests need a separate test database, `test_uol_student_affairs`. The application user `uol_app` previously had privileges only on `uol_student_affairs`, so the test database could not be created.
- The owner, acting as MySQL administrator, granted `uol_app` these privileges on `test_uol_student_affairs` only: SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, ALTER, INDEX and REFERENCES. The database name in the grant is escaped (`test\_uol\_student\_affairs`) so that `_` is not treated as a wildcard.
- Verified with `SHOW GRANTS`: `uol_app` has no global privileges beyond `USAGE`, and its existing privileges on `uol_student_affairs` were left as they were.
- The test database exists with `utf8mb4` / `utf8mb4_0900_ai_ci`, the same as the development database.
- Tests are run with `manage.py test accounts --keepdb`, which reuses the test database. Do not use `--parallel`, which would need further databases that this grant does not cover.

**MySQL collation test correction**

- The first MySQL run passed 31 of 32 tests. `test_add_user_lowercases_mixed_case_email` failed because it used a database filter to assert that no row matched the mixed-case address. Under the case-insensitive collation `utf8mb4_0900_ai_ci`, that filter also matches the correctly stored lowercase row.
- Corrected the test to select the newly created user without filtering by email and to compare the stored email exactly in Python. No application code changed.

**Verified (2026-11-16)**

- Account tests on MySQL 8.0.44: 32 of 32 passed.
- Account tests on SQLite (in-memory, using a temporary settings file kept outside the repository): 32 of 32 passed.
- `manage.py check`: no issues.
- `manage.py makemigrations --check --dry-run`: no changes detected.
- `manage.py migrate --check`: all migrations applied to the development database.
- Committed as `99b1ba2` ("feat: establish Django foundation and account system") on branch `chore/django-foundation` and pushed successfully to `origin/chore/django-foundation`. The working tree was clean immediately after the push.
- Pull request #1 (`chore/django-foundation` into `main`) was reviewed, with no blocking findings, and merged on 2026-11-16 as merge commit `a1ed704`. The source branch was kept.

**Not done**

- No authentication pages or Google OAuth (O3), and no product features.

**Notes for later work**

- Future code that queries users by email directly, such as the Google OAuth callback, must normalize the email first or use `get_by_natural_key()`/`aget_by_natural_key()` (O2, O3).
- Consistency between the `role` field and `is_staff`/`is_superuser` is to be settled with the Super Admin bootstrap (O26).
- The manager does not validate email format. Model validation and the admin forms do.

---

## 2026-11-16 — Documentation reconciliation

**What was done**

- Reviewed `MASTER_PROJECT_BRIEF.md`, `PROJECT_CONTEXT.md` and `README.md` against the decisions made in later discussions.
- First reconciliation: recorded 17 decisions supplied by the owner and created `DECISIONS.md` and this log. Six older decisions were left needing confirmation and the open list was long, because the later discussions were not yet reflected.
- Second reconciliation: the owner supplied the full set of confirmed decisions and the actual state of local development. All four documents were revised together.

**Decisions recorded in the second reconciliation**

- Authentication and accounts: one shared Google login, no role selector, registration fields, immediate activation, Super Admin corrections, bootstrap of the initial Super Admin, BA account creation and assignments (DEC-010 to DEC-016 revised; DEC-200 to DEC-204).
- Academic structure and student records: managed entries, deactivation rules, manual semester updates, audited profile changes (DEC-020, DEC-021 revised; DEC-210 to DEC-212).
- Complaints: categories, statuses, mandatory notes, "Still not resolved", further information, cancellation requests, duplicate warning, routing and ownership, Super Admin powers, visibility (DEC-031 revised; DEC-220 to DEC-231).
- Collective issues: raising, support, privacy of responses, statuses, representative assignments (DEC-040 revised; DEC-240 to DEC-247).
- Student Voice: replaces Suggestions and Appreciation; privacy and answering rules (DEC-051 revised; DEC-250 to DEC-254).
- Meetings: requests, BA actions, calendar, visibility, oversight (DEC-060, DEC-061 revised; DEC-260 to DEC-263).
- Notifications, analytics and dashboards (DEC-070, DEC-090 revised; DEC-270, DEC-280 to DEC-284, DEC-083).
- Environment: project database and secrets handling (DEC-100 revised; DEC-290, DEC-291).

**Superseded**

- Email OTP, anonymous complaints, advisor approval after request, one CR per section, Suggestions and Appreciation, the rule on complaints about the Administrator or HOD, the three priority queues, the overdue indicator, and the requirement for further advisor research. See `DECISIONS.md`, section 3.

**Questions closed**

- Q1 to Q6 and most of O1 to O17. See `DECISIONS.md`, section 4.

**Still open**

- Technical implementation choices: O2, O3, O18 to O23, O25, O26.
- Workflow details needing a short answer from the owner: O27, O28, O29.

**Corrections to earlier documentation**

- The earlier documents stated that application implementation had not started. That was inaccurate: the Django foundation already existed locally. See the foundation entry below.
- The earlier documents presented MySQL 8.4 as the database target without stating that development runs on the existing MySQL 8.0.44 server. MySQL 8.4 is not installed and no upgrade is approved.

**Next**

- Confirm the commit and push status of the foundation work and record it here.
- Copy the committed documents to the Claude Project knowledge and share them with ChatGPT.
- Update `README.md`, whose objectives and stack list predate this reconciliation.

---

## Django foundation — created and tested locally

The date or dates of this work are not recorded here. Add them from the local history.

**What was done**

- Set up the development environment on Windows 11 with Python 3.13.15 and Django 5.2.19.
- Created the MySQL database `uol_student_affairs` with utf8mb4 on the existing MySQL Server 8.0.44.
- Configured an application database user with privileges limited to the project database.
- Created the Django project structure with `manage.py` and `config`.
- Created a custom `accounts.User` model.
- Generated and applied the initial accounts migration.
- Configured Django settings to load secrets from `.env` using python-dotenv.
- Added `.env.example` with placeholders.

**Verified**

- Django system check passed.
- Database connection and migrations verified.

**Not done**

- No business workflow or user-facing feature has been implemented.

**Preserved**

- The existing MySQL 8.0.44 installation and the databases `db_final_group_project_working` and `db_final_group_project` belonging to another academic project.

---

## 2026-11-15 — Master brief and independent review requested

**What was done**

- Wrote the initial `MASTER_PROJECT_BRIEF.md` as a consolidated introduction for all collaborators.
- Set up a Claude Project with `MASTER_PROJECT_BRIEF.md`, `PROJECT_CONTEXT.md` and `README.md`.
- Requested an independent strategic assessment of the product from Claude, with no code or file changes.

---

## On or before 2026-11-15 — Repository initialised

The exact date is in the Git history.

**What was done**

- Created the local project directory.
- Initialised the Git repository on `main` and configured the GitHub remote.
- Added `.gitignore`, `README.md` and `PROJECT_CONTEXT.md`.
- Pushed the initial documentation commit.
