# UOL Student Affairs

[![tests](https://github.com/azeemworks925-eng/uol-student-affairs/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/azeemworks925-eng/uol-student-affairs/actions/workflows/tests.yml)

**Student Affairs & Engagement Portal**: one place where students raise complaints, share
ideas, request meetings and raise section-wide issues, and where Batch Advisors and the
department handle them.

> This is an independent student project: an individual BS Software Engineering
> (4th semester) project. It is **not** an official University of Lahore system. The
> University has not commissioned, approved or deployed it.

## Features by role

Everyone signs in with Google on one shared sign-in page. There is no role selector: the
portal matches the Google account to a user record and opens the right home page.

### Student

- Self-registers on first sign-in (SAP ID, batch, semester, section) and is active at once.
- **Complaints:** submits a complaint in a category, follows its status and history, and
  answers the advisor's requests for more information. A "possibly a duplicate" warning
  appears when a new title is close to one of their own open complaints.
- **Student Voice:** sends an Idea, Question or Feedback and sees the advisor's answer.
- **Meetings:** requests a meeting with their Batch Advisor; accepts, declines or cancels;
  adds it to Google Calendar; month and week views.
- **Section issues:** sees their section's issues and supports them. Only the count is
  shown, never who supported.
- **Home:** the five latest updates across complaints, Student Voice and meetings, plus
  in-app notifications.

### CR / GR (Class Representative / Girls Representative)

A student account with extra permissions for their own section (one CR and one GR per section):

- Raises collective **section issues** for the section, with a non-blocking warning when a
  similar issue is already open.
- Keeps every normal student feature.

### Batch Advisor

Sees only the sections they are assigned to.

- **Complaints workspace:** filters, sorting, search by student name or SAP ID,
  "Go to reference" and "Next complaint" (the oldest one waiting). Changes status, responds
  and asks for more information.
- **Student Voice:** answers, replies and marks submissions reviewed.
- **Meetings:** confirms, suggests another time, declines, cancels or schedules a meeting.
  A warning appears when a time overlaps another confirmed meeting; it does not block.
  Month and week views.
- **Collective issues:** marks their sections' issues Under Review, responds and resolves them.
- Assigns and replaces the CR and GR of their sections.

### Super Admin (Head of Batch Advisors)

Department-wide oversight:

- **Overview:** stat tiles and charts, with complaint analytics for the current term
  (cohort map, category share, resolved vs. not resolved). Cohorts with fewer than five
  active students are hidden.
- **Complaints:** every complaint, term and cohort filters, and assigning the responsible owner.
- **People:** students, Batch Advisors and Super Admins, including advisor section assignments.
- **Academic structure:** the Department → Batch → Semester → Section tree with totals,
  academic terms, and complaint categories and subcategories.
- **Read-only oversight** of Student Voice, meetings and collective issues.

## Data structures and algorithms

The portal hand-writes seven data structures and algorithms in [`dsa/`](dsa/). Each one runs
inside a real feature. They do not use `sorted()`, `heapq`, `bisect`, `dict`, `set` or
`collections`. [`dsa/README.md`](dsa/README.md) gives their complexity and explains how each
one is wired in.

| Algorithm / structure | File | Where it is used |
|---|---|---|
| Merge sort (stable) | [`dsa/sorting.py`](dsa/sorting.py) | Every complaint list (advisor and Super Admin workspaces, My Submissions) and its sort options; Student Home's latest updates; Student Voice, meetings, section issues and people lists |
| Hash table (separate chaining) | [`dsa/hash_table.py`](dsa/hash_table.py) | "Go to reference" in the staff complaint workspaces |
| Trie (prefix tree) | [`dsa/trie.py`](dsa/trie.py) | Staff complaint search by student name or SAP ID prefix; Super Admin people search |
| Binary min-heap | [`dsa/heap.py`](dsa/heap.py) | "Next complaint" for Batch Advisors: the oldest complaint still Received or Under Review |
| Interval overlap sweep | [`dsa/intervals.py`](dsa/intervals.py) | Meetings: warns a Batch Advisor about overlapping confirmed meetings |
| General tree + DFS | [`dsa/tree.py`](dsa/tree.py) | Academic Structure: the department tree with subtree totals |
| Edit distance (Levenshtein, dynamic programming) | [`dsa/edit_distance.py`](dsa/edit_distance.py) | "Possibly a duplicate" warnings for new section issues and new complaints |

The callers are in `complaints/ordering.py`, `meetings/presentation.py`,
`academics/structure.py`, `accounts/people.py`, `issues/services.py` and
`complaints/services.py`. `dsa/tests/` checks each structure against Python's built-ins on
random inputs.

## Tech stack

- Python 3.13
- Django 5.2 (LTS)
- MySQL 8.0 (utf8mb4)
- django-allauth for Google sign-in (OAuth 2.0 / OpenID Connect)
- Server-rendered Django templates, vanilla JavaScript and CSS, and a vendored copy of
  Bootstrap 5.3. There is no frontend build step.

## Local setup

Requirements: Python 3.13 and a local MySQL 8.0 server. These commands are for Windows
PowerShell; on macOS or Linux, activate the venv with `source .venv/bin/activate`.

1. Create a database and a user for it in MySQL:

   ```sql
   CREATE DATABASE uol_student_affairs CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   CREATE USER 'uol_app'@'localhost' IDENTIFIED BY '<choose-a-password>';
   GRANT ALL PRIVILEGES ON uol_student_affairs.* TO 'uol_app'@'localhost';
   -- The test runner creates and drops test_uol_student_affairs:
   GRANT ALL PRIVILEGES ON test_uol_student_affairs.* TO 'uol_app'@'localhost';
   ```

2. Create a virtual environment and install the dependencies:

   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and fill it in. You need at least `DJANGO_SECRET_KEY`,
   `DJANGO_DEBUG=True` (for local work) and the `DB_*` values. To use Google sign-in, also
   set `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET`. Use `DEMO_STAFF_EMAILS` to
   sign in as staff with your own Google accounts on a laptop demo (`DEBUG` only).
   **Never commit `.env`.**

   ```powershell
   Copy-Item .env.example .env
   ```

4. Create the tables, load the demo data and start the server:

   ```powershell
   python manage.py migrate
   python manage.py seed_demo      # demo cohorts, people, complaints, meetings... (DEBUG only; safe to rerun)
   python manage.py runserver
   ```

   Open <http://127.0.0.1:8000>.

`python manage.py bootstrap_super_admin` creates the first Super Admin when you are not
using the demo data.

## Running the tests

The full suite runs against MySQL using your `.env`:

```powershell
python manage.py test
python manage.py check
```

GitHub Actions ([`.github/workflows/tests.yml`](.github/workflows/tests.yml)) runs the same
suite on every push and pull request, on Ubuntu with Python 3.13. CI uses an in-memory
SQLite database ([`config/settings_ci.py`](config/settings_ci.py)), a dummy secret key and
`DEBUG` off. On SQLite, the concurrency tests that need MySQL row locks
(`select_for_update`) skip themselves, so run the suite locally on MySQL before merging.

## Project status

All V1 modules are built and merged into `main`: sign-in and accounts, complaints,
notifications, Student Voice, meetings, section issues, Super Admin people and structure
management, and the analytics overview. The course demo is on **2026-11-26**. The portal
runs locally only and has no production deployment. Sign-in with real UOL staff Google
accounts is not yet tested. For details and known limitations, see
[`docs/STATUS.md`](docs/STATUS.md).

More documentation:

- [`docs/decisions/DECISIONS.md`](docs/decisions/DECISIONS.md): the decision register
- [`docs/DEVELOPMENT_LOG.md`](docs/DEVELOPMENT_LOG.md): what was built and when
- [`docs/technical/`](docs/technical/): technical notes per module

## License

License to be determined.
