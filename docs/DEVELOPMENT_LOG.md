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
| Django foundation | Created and tested locally. |
| Product features | Not implemented. |
| Commit and push status of the foundation | Not recorded here. Confirm with `git status` and `git log`, then replace this row. |

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
