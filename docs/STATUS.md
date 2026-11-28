# Project status

**As of:** 2026-11-28 · **Course demo:** 2026-11-26

An independent BS Software Engineering student project. It is not an official University of
Lahore system. For the full history, see [`DEVELOPMENT_LOG.md`](DEVELOPMENT_LOG.md); for every
decision, see [`decisions/DECISIONS.md`](decisions/DECISIONS.md).

## What is built

Every V1 module is merged into `main`:

| Module | App | What it covers |
|---|---|---|
| Sign-in and accounts | `accounts` | Google sign-in for every role, student self-registration, a 30-minute idle timeout, role home pages, and CR/GR assignment |
| Super Admin management | `accounts`, `academics` | Portal pages for Students, Staff, Academic Structure (the DSA department tree) and Academic Terms. The Django admin is kept only as a fallback. |
| Complaints | `complaints` | Submission, workflow and history; the Batch Advisor and Super Admin workspaces; categories; owner assignment; DSA sorting, search, "Go to reference", "Next complaint" and duplicate warnings |
| Analytics | `complaints` | Super Admin Overview for the current term, with small-cohort suppression |
| Notifications | `notifications` | In-app notifications and the bell |
| Student Voice | `voice` | Ideas, Questions and Feedback, with advisor answers and replies |
| Meetings | `meetings` | Requests, confirm / suggest / decline / cancel, month and week views, and overlap warnings |
| Section issues | `issues` | CR/GR-raised collective issues, anonymous support counts, advisor review / respond / resolve, and Super Admin oversight |
| DSA | `dsa` | Seven hand-written structures and algorithms, each used in a feature (see [`../dsa/README.md`](../dsa/README.md)) |

## Polish v2 (docs/POLISH_V2.md)

| Session | Scope | State |
|---|---|---|
| P1 Foundation | Tokens and dark mode first pass, all Inter, status colour map, shell, motion system, shared components, toasts, theme toggle, `/dev/ui/` gallery (DEBUG only) | Done (DEC-332 to DEC-338) |
| P2 Pages | Apply the components to every page: heroes, banners, bento layouts, list and detail pages, meetings calendar, people and configuration | Next |
| P3 Doodles + auth | Doodle set into the slots P1 left, auth page family | Not started |
| P4 Logic | Global search typeahead, role switcher (if safe), gender field, CR/GR picker, suppression removal, demo-data cleanup | Not started |

Notes for P2 from the P1 visual check: page titles still differ from sidebar labels (student
"My submissions"); timeline dots on existing detail pages are not yet toned per event; list pages
use the restyled collection rather than the new `list_row` / `card_item` partials; the Overview
heatmap and suppression legend are still there (removed in P2/P4); the phone drawer still needs
Bootstrap's JavaScript.

## Last verified commit

`aaa56f2` (merge of PR #31, Section Issues) was the starting point for the `chore/cleanup`
branch. On that branch, the full suite was run twice:

- locally on MySQL 8.0;
- on GitHub Actions with SQLite, where the 35 MySQL row-lock concurrency tests skip.

The only code change on the branch is a test fix. See the merge of `chore/cleanup` for the
exact commit.

## Known limitations

- **Real UOL staff sign-in is not yet tested.** All sign-in tests use simulated Google
  responses. Sign-in with real `@uol.edu.pk` and `@student.uol.edu.pk` Google Workspace
  accounts, including the hosted-domain (`hd`) claim, still has to be verified
  ([`technical/AUTHENTICATION.md`](technical/AUTHENTICATION.md), section 8). For the laptop
  demo, `DEMO_STAFF_EMAILS` (`DEBUG` only) stands in for staff accounts.
- **Small-cohort suppression will be removed after the demo.** The Overview analytics hide
  cohorts with fewer than five active students (DEC-315, DEC-318, DEC-319). It is planned to
  come out after the demo; that will need its own decision and change.
- **No production deployment yet.** The portal runs only on a local laptop. Production
  static-file serving, HTTPS settings, hosting and backups are not configured, and a privacy
  review is required before any pilot use (DEC-322).
- **CI does not cover MySQL-only behaviour.** The row-lock concurrency tests run only
  locally on MySQL.
