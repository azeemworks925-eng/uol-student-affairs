# Academic terms — technical notes

**Status:** Complaints Part 4 Stage 4a. Under review on branch `feat/academic-term`; not merged.
**Decisions:** DEC-314 (one named academic-term reporting window, by submission date), DEC-210 (academic records are kept, not deleted). Specification: `COMPLAINTS_PART4_SPEC.md` section 6.1.

An academic term is the reporting window for the complaint analytics planned for Stage 4b. This stage adds the term record, how the current term is chosen, the shared date-boundary rule, and a term filter on the Super Admin complaint list. It adds no analytics.

## 1. Model (`academics.AcademicTerm`)

| Field | Meaning |
|---|---|
| `name` | Unique, up to 50 characters, for example "Fall 2026". A term is not a `Batch`. |
| `start_date`, `end_date` | The first and last day of the term. Both are included. |
| `is_current` | `TRUE` for the current term and `NULL` for every other term. It is never `FALSE`. It isn't a form field (`editable=False`). |
| `created_at`, `updated_at` | Timestamps. |

**Database constraints** (migration `academics/0002_academicterm`):
- **Name:** `name` is `UNIQUE`.
- **Dates:** the check constraint `academic_term_dates_valid` requires `end_date >= start_date`.
- **One current term:**
  - `is_current` has a plain `UNIQUE` index. MySQL and SQLite both allow many `NULL`s in a unique index but only one `TRUE`, so **the database itself allows at most one current term**.
  - The check constraint `academic_term_current_true_or_null` allows only `NULL` or `TRUE`, so a `FALSE` (or any other value) can't get around the unique index.
  - No conditional unique constraint is used, because MySQL ignores those (the same reason as the existing allauth W036 warning, which this stage leaves alone).
- **Verification:** tests use raw SQL, which skips every ORM guard, to show that MySQL 8.0.44 and SQLite each refuse:
  - a second current term;
  - `FALSE`, `0` and `2` in the current flag;
  - reversed dates;
  - duplicate names.

**Names.** Validation trims and collapses whitespace. It refuses duplicates while ignoring case and accents, to match MySQL's `utf8mb4_0900_ai_ci` collation, so behaviour is the same on SQLite. Complaint category names work the same way.

**Date range.** Validation also requires dates between 1 Jan 1900 and 31 Dec 9998. This keeps the window's boundaries representable when they are converted to UTC.

**Overlap.** Terms may overlap, and no constraint stops it, because only the current term is reported.

**Guards** (`TermQuerySet` and `AcademicTerm.save()`/`delete()`, raising `ProtectedTermError`):
- **Never deleted:** instance and bulk `delete()` are refused, and the admin has no delete permission.
- **Current flag:** only `academics.services` changes it. The ORM refuses:
  - `update(is_current=...)` and `bulk_update` with that field;
  - `bulk_create` of a current term, or an upsert that writes the field;
  - an instance `save()` whose flag differs from the stored row.

  The `save()` check compares with the stored row, including an unsaved instance built with an existing pk. Other fields save normally.
- **Raw SQL** is outside what the ORM can protect, but the database constraints still apply to it.

**Migration.** `academics/0002_academicterm` only creates this table with its constraints. It is additive, needs no data and is reversible. A test reverses it, then re-applies it and checks the constraints, on MySQL and SQLite. **It has not been applied to the owner's development database.**

## 2. Reporting window (`academics.models.term_window`)

There is one boundary rule, calculated in one place (`term_window(start_date, end_date)`, also `AcademicTerm.window()`):

- **start:** `start_date` at 00:00 Asia/Karachi, **inclusive**;
- **end:** the day after `end_date` at 00:00 Asia/Karachi, **exclusive**;
- **query:** `created_at >= start AND created_at < end`.

These are timezone-aware datetimes in `Asia/Karachi` (UTC+05:00, with no daylight saving), fixed regardless of the active time zone. With `USE_TZ=True`, the database stores and compares UTC. For example, a term starting on 1 Sep 2026 begins at 2026-08-31 19:00 UTC. Every later user of the window, including Stage 4b analytics, must call this function instead of rebuilding the boundary.

## 3. Current-term services (`academics/services.py`)

| Function | Behaviour |
|---|---|
| `set_current_term(term)` | Makes `term` the only current term. Returns `(previous, changed)`, where `changed` is `False` if it was already current; in that case nothing is written. An unsaved or missing term raises `AcademicTerm.DoesNotExist`. |
| `clear_current_term(expected=...)` | Leaves no term current. Returns `(previous, changed)`; with nothing current it returns `(None, False)`. With `expected` (a term or `None`), it changes nothing and raises `CurrentTermChanged(current)` if a different term is current once the locks are held. This protects a stale screen from clearing a term that someone else has just made current. |
| `current_term()` | The current term, or `None`. |

**Concurrency.** Each change is one `transaction.atomic` block:
1. It locks **every** term row with `SELECT … FOR UPDATE` in primary-key order. Concurrent changes are serialised, and the fixed order means they can't deadlock each other.
2. It reads the current term again **under the locks**, so a waiting change sees the earlier one's result.
3. It clears the old term first, because MySQL checks the unique index row by row, and then sets the new one.

**Why rows added later don't matter.** A term inserted after the locks are taken is always non-current, because `save()` refuses anything else, so it can't become a second current term.

**Final safeguard.** The database's unique index. If it fires, for example after raw SQL, the `IntegrityError` is caught **outside** the rolled-back atomic block and re-raised as `CurrentTermConflict`. The caller's transaction stays usable and nothing is half-applied.

**Tests.** The MySQL-only tests (`has_select_for_update`) run real concurrent transactions on separate connections:
- a second selection waits while the first holds its locks, then sees and replaces the first result;
- a clear waits for a selection, then clears it;
- a stale `clear(expected=old)` after a concurrent switch changes nothing;
- two concurrent clears;
- six writers making 48 mixed changes never leave two current terms and never deadlock.

Removing the row lock makes these tests fail.

## 4. Administration (Configuration → Academic Structure)

`AcademicTermAdmin` sits in the Django admin `academics` app, next to batches, semesters and sections. Only active Super Admins can open the admin, because the role sets `is_staff`. Other roles, anonymous visitors and inactive accounts are redirected away.

- **List:** name, start date, end date and a "Current term" / "Not current" column. The change form shows the designation read-only, and a posted `is_current` is ignored.
- **Validation:** reversed dates produce a form error on the end date ("The end date cannot be before the start date."). Duplicate names, ignoring case and accents, produce a form error on the name. If someone else saves a conflicting term at the same moment, the database refuses it; the admin then shows an error message and saves nothing, instead of a server error.
- **No deletion:** there is no delete view (403) and no "Delete selected" action.
- **"Make the selected term the current term":** exactly one term must be selected; otherwise an error is shown and nothing changes. The messages say whether the term became current, replaced another term, or was already current.
- **"Clear the current term":**
  - the selection must be the current term and nothing else;
  - it calls `clear_current_term(expected=<that term>)`, so if someone else switched the current term in the meantime, nothing changes and the message names the term that is now current;
  - a `CurrentTermConflict` is reported as an error message, never a server error.
