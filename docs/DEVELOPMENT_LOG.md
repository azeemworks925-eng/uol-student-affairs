# UOL Student Affairs — Development Log

**Purpose:** A dated record of what was done and decided in each working session.
**Canonical location:** This file in the GitHub repository.

Rules:

- Newest entry first.
- Record what actually happened. Do not record plans as completed work.
- Decisions are recorded in full in `DECISIONS.md`; entries here refer to them by ID.
- Dates use the owner's local time (Asia/Karachi).

---

## Status at a glance (2026-11-16)

| Area | Status |
|---|---|
| V1 product workflows | Confirmed in `DECISIONS.md`. |
| Django foundation | Complete and verified locally: custom user model, admin, email normalization, 32 account tests passing on MySQL 8.0.44 and SQLite. |
| Authentication and account foundation | Merged into `main` through PR #3 as merge commit `df47133` on 2026-11-16. Google sign-in is tested with simulated Google responses only; it has not been verified with a real UOL account. |
| Design system | Design philosophy approved in principle. A development-only palette comparison exists on branch `design/palette-preview`. No palette or design token is approved. |
| Product features | Not implemented. |
| Commit and push status of the foundation | Committed as `99b1ba2` ("feat: establish Django foundation and account system") on branch `chore/django-foundation` and pushed to `origin/chore/django-foundation`. Merged into `main` through PR #1 as merge commit `a1ed704` on 2026-11-16. |

---

## 2026-11-16 — Palette comparison preview (development only)

**Context**

- The owner reviewed the Frontend Design Research Report (`UOL Student Affairs — Frontend Design Research Report.docx`, kept outside the repository). The owner approved the design philosophy in principle: quiet structure, one shared system, two densities, responsive role-specific navigation, Bootstrap 5.3 and CSS tokens.
- The owner asked for a rendered comparison of Forest and Indigo, in light and dark, before choosing a palette. No palette, token or design decision has been approved or recorded in `DECISIONS.md`.

**What was done**

- Added `design/preview/palette-comparison.html`, a standalone development-only page.
  - It lives outside `templates/` and `static/`, has no Django URL, and is opened directly in a browser. No production page is affected.
  - It loads Bootstrap 5.3.3 and the Inter font from CDNs. Neither is added to the project: no new Python or static dependency was added.
- The page renders identical components in Forest light, Forest dark, Indigo light and Indigo dark. Each component is written once and cloned into all four panels:
  - primary, secondary and quiet buttons (hover, focus and disabled states);
  - the four complaint status badges (DEC-221) in both badge sizes, plus a block placing the accent beside the Resolved badge;
  - inputs, selects and textareas (focus, error and read-only states);
  - standard and compact cards;
  - the student and Batch Advisor sidebars;
  - a phone-width Student Dashboard with the three DEC-282 sections.
- Content uses confirmed workflows only, with fictional names.
- Colour values are the report's exact values. For Indigo, the report gives no strong border, control border, subtle surface or disabled text, so these were derived by the same method as Forest and are marked "derived" on the page. The dark accent tints use the report's formula (accent at 16% over the surface).
- The page measures contrast in the browser from the rendered colours. It was rendered in headless Chrome to check layout and read those results, and three preview layout bugs found that way were fixed.

**Findings from rendering** (also listed on the page)

- Text contrast: every required pair passes WCAG AA in all four versions. That covers 15 pairs per version, including body and muted text, button labels, current navigation, all four badges, form errors, placeholders, input borders, error borders and focus rings. The report's stated ratios were confirmed, apart from rounding.
- The Forest accent against Resolved:
  - The solid accent and Resolved text are in the same green family: colour difference ΔE 28.9 in light and 27.3 in dark, against more than 100 for Indigo. They stay distinguishable because the accent is a solid fill and Resolved is a tinted pill with an icon.
  - The report did not cover this closer clash: in Forest light, the current-navigation tint `#E4F0EA` and the Resolved pill `#E6F4DF` are nearly identical fills (ΔE 7.8). In Forest dark the difference is ΔE 12.8. For Indigo it is ΔE 19.9 in light and 36.8 in dark.
- Secondary button and tile borders: about 1.4 to 2.1:1 against the canvas in all four versions, below 3:1. This is advisory, not a WCAG failure, because the label identifies the control. It does mean the button's edge is faint.
- The "Supported" state on Section Updates: the report describes a quiet state. Rendered in disabled-text colour, it measures 2.8 to 3.2:1. Disabled controls are exempt from WCAG, but this text tells the student their support is recorded and cannot be withdrawn (DEC-241), so it should be readable.
- Disabled button labels: 2.5 to 2.8:1. These are exempt and expected.

**Not done**

- No palette chosen, no tokens or decisions recorded, no application shell built.

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
