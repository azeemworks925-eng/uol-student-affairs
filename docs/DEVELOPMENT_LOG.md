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
| Product features | Not implemented. |
| Commit and push status of the foundation | Not yet committed or pushed. The foundation files are untracked on the local branch `chore/email-normalization`. Update this row after committing. |

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

**Not done**

- Nothing committed or pushed yet.
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
