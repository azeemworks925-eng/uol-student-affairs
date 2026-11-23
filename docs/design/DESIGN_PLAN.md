# UOL Student Affairs — Design Plan

**Status:** Design D is the approved visual reference for production implementation (owner, 2026-11-16; DEC-302).
**This document is the written production specification of Design D.** The HTML prototypes used during the design phase were not kept in the repository and are not a reference; where a detail is not written here, it is decided during implementation within these rules.
**Implemented so far:** the application shell, role navigation, Student Dashboard and the Batch Advisor and Super Admin overviews, and the sign-in pages (PR #6). Production tokens and components live in `static/css/app.css` and `templates/`.
**Decisions:** recorded in `docs/decisions/DECISIONS.md` (DEC-300 to DEC-308; the complaint and analytics items O25, O27 (for complaints), O28 and O31 to O33 are resolved by DEC-310 to DEC-322; O29, O30 and O34 remain open). If this plan and `DECISIONS.md` disagree, `DECISIONS.md` wins.

Labels used below: **Approved** (owner decision), **Recommendation** (default for implementation unless the owner says otherwise), **Open** (needs an owner decision before the related feature is final).

---

## 1. Philosophy and palette — Approved

**Confident type. Quiet colour. Meaningful information.** (DEC-300)

1. Type carries the hierarchy: one display-size moment per page, and it carries information.
2. Say it before you show it: a calculated summary sentence before any chart; no chart without a written takeaway.
3. Quiet colour, loud meaning: Forest only for the one primary action, links and focus; ink for selection; status tones only on status.
4. Every case shows where it is: one status journey at every scale; monospace reference IDs.
5. The cohort is the unit: exact batch + semester + section everywhere (DEC-205).
6. Staff get workspaces, not dashboards.
7. Private by default, calm in tone.

**Palette (DEC-301).** Forest Light and Forest Dark are approved; their values and the four status tones are fixed. Light values: accent `#176B52`, on-accent `#FFFFFF`, canvas `#F5F7F5`, surface `#FFFFFF`, subtle `#EDF2EE`, border `#DCE8E0`, strong border `#B8D8C7`, control border `#7A8A82`, text `#16201C`, heading `#253B32`, muted `#55635C`, disabled `#8B978F`. Status: Received `#E8F0FE`/`#1B4AA8`, Under Review `#FDF1D7`/`#8A5300`, Resolved `#E6F4DF`/`#2F6B1E`, Rejected `#FBEAE8`/`#9F2D22`.

Dark values, as given in the Frontend Design Research Report (kept outside the repository) and rendered in the palette comparison during the design phase: accent `#5CC9A3`, on-accent `#0F1513`, canvas `#0F1513`, surface `#161E1B`, raised and subtle surface `#1E2925`, border `#2C3A34`, strong border `#3D5047`, control border about `#6F8279` (the report's approximate value, to be verified for contrast when Dark is implemented), text `#E6EEEA`, muted `#9DB0A7`, disabled `#5F6F67`. Status (dark): Received `#16233F`/`#9DBBFF`, Under Review `#33270F`/`#F2C56B`, Resolved `#1B2C14`/`#9AD27F`, Rejected `#3A1A17`/`#F2A198`. The report gives no separate dark heading colour. Forest Dark is approved but not yet implemented; whether a System theme option is offered is open (O34).

- Active navigation uses an **ink indicator bar and font weight**, never the Forest tint (the tint is nearly identical to the Resolved badge in Forest Light).
- Derived states (hover, map shades) are mixed from these tokens; no new colour values. Every text pair must reach 4.5:1 (3:1 for large text and control boundaries).

## 2. Typography and components

- **Recommendation (O30 open; used by the PR #6 implementation pending the owner's final decision):** Newsreader for display moments (greetings, headline sentences, case titles, large numerals) and Inter for all interface text; system monospace for reference IDs, SAP IDs and cohorts. Self-host the variable woff2 files with `font-display: swap`; fallbacks Iowan Old Style / Palatino / Georgia and system-ui.
- Display sizes are fluid and bounded by viewport width **and height** with `clamp()` and rem minimums (see section 6).
- Shared components: ink-active navigation (sidebar, icon rail, mobile header, bottom navigation), cohort chip, monospace reference, status pill with dot and label, status journey, immutable history list, compact list rows, buttons (one Forest primary per view), form fields with visible labels and inline errors.

## 3. Navigation — Approved direction

| Role | Desktop | Phone |
|---|---|---|
| Student | Sidebar: Home, Complaints, Student Voice, Meetings; account menu at the foot | Header (notifications, account) + bottom navigation with those **four** destinations; no "More" (DEC-304) |
| Batch Advisor | 72px icon rail: Overview, Complaints, Collective Issues, Student Voice, Meetings, Representatives, Statistics | Header with menu button and drawer |
| Super Admin | Sidebar groups — Oversight: Overview, Complaints, Collective Issues, Calendar · People: Students, Staff, CR/GR Management · Configuration: Academic Structure, Academic Terms, Complaint Categories (DEC-330). **No separate Statistics** (DEC-306) | Header with menu button and drawer |

The full application shell (drawer behaviour, notification list, account menu contents) is refined as modules are built.

Section Issues (DEC-331): the current CR and GR also get a "Section issues" sidebar and drawer item and a "Raise a section issue" entry in + New. The four phone tabs do not change. Batch Advisors and the Super Admin reach the work through "Collective Issues"; the Super Admin's page is read-only.

## 4. Student Dashboard — Approved (DEC-302, DEC-303)

- Welcome: date, exact cohort chip (e.g. "Fall 2024 · Semester 4 · Section A"), display greeting with the student's first name.
- **Personal summary**, calculated from the student's own records only, never generated by AI:
  - zero updates: "Nothing needs your attention today.";
  - one update: describe it directly;
  - several: lead with the most important/recent update, then "You have N other updates.";
  - never invent urgency or imply an action is required when none is. Collective section issues are **not** part of this summary.
- **Quick Access**: three separate actions — Submit a complaint (the only Forest primary), Student Voice, My meetings.
- **Your latest updates** (DEC-282 "Your Actions"): the complaint journey card appears only for a complaint with relevant new activity and stays while the update is relevant, even after it is opened; seen and unseen updates are visibly distinguished. Other updates are hairline rows.
- **Your section** (DEC-282 "Section Updates"): noticeboard of active CR/GR issues with support counts; representative names and roles only, no contact details. Before supporting: "Support can't be withdrawn." and "Support this issue"; afterwards "You support this".

## 5. Batch Advisor Complaints — Approved (DEC-302, DEC-305)

- Reference layout: 72px rail | ~360px list | case workspace | ~300px context. Proportions adapt; below about 1360px the context becomes a compact strip under the case header instead of disappearing.
- List: headline sentence, search by reference ID or student name (within assigned cohorts only), cohort and status filters, rows with reference, flags, title, full student name (never truncated), cohort chip and status.
- Case: reference, status, title, student, cohort, category; status journey; immutable history (newest first); response composer; **Respond and Update status are separate, and sending a response never changes the status.** Resolve/Reject ask for the mandatory note (DEC-221).
- Context: student identity, exact batch/semester/section, the advisors assigned to the cohort. The responsible owner is designated manually by a Super Admin (DEC-310); the Batch Advisor workspace does not currently show it. "Other complaints from this student" is **not** in V1.
- A "Waiting for you" / "Other open" grouping is **not** adopted (DEC-312, resolving O33).
- Phone: list → full-screen case → back. Context below the case content. The composer sits at the end of the history (never floating over it) with a sticky Respond / Update status bar; `interactive-widget=resizes-content` so the keyboard shrinks the layout instead of covering the history.

## 6. Super Admin Overview — Approved (DEC-302, DEC-306)

- Editorial layout, no KPI tiles: department headline sentence, then three numbered chapters for the DEC-281 analytics, each with a written takeaway before its visual and links into records: **01 Distribution by section** (cohort map), **02 Category share**, **03 Resolved vs not resolved**.
- Cohort map: academic order (Semester 1 → 8), each cell exactly one batch + semester + section, linking to that cohort's complaints. A real section with zero complaints (solid cell, "No complaints") is visibly different from a section that does not exist (hatched, no number).
- **Resolved (O31, DEC-313):** Resolved = Resolved; not resolved = Received + Under Review + Rejected. Wording must never present rejected complaints as awaiting action (e.g. "42 are not resolved: 33 are still being handled and 9 were rejected").
- **Resolved (O32, DEC-314, DEC-316):** one explicitly defined reporting window shared by all three analytics — the academic term, with start and end dates stored in Academic Structure; complaints counted by submission date. The screen always states the window.
- **Resolved (O25, DEC-315, DEC-317 to DEC-320):** suppress a cohort's breakdown when it has fewer than 5 active students. **Risk found:** suppressing one cell while showing totals lets anyone derive the hidden value by subtraction; the rule needs complementary suppression (hide at least one more cell or withhold the affected total).

## 7. Laptop and zoom acceptance — Approved (DEC-307)

- Reference device: **HP EliteBook 840 G8**, 13.9" 1920×1080 panel at **150% Windows scaling** = 1280×720 logical px (1280×672 work area). Opera at **100% zoom** leaves a viewport of about **1280×590** (≈1232 wide with Opera's sidebar). This is the **primary acceptance target**; 80% zoom (≈1600×740) is comparison only.
- Root cause of the earlier "too enlarged" feel: fixed pixel sizes composed for ~1440×900 with no vertical budget. Fix: fluid display sizes bounded by height, merged top bars, content-driven breakpoints (container queries), never a global transform, forced zoom or blanket font reduction.
- Acceptance per page at 1280×590: the page's focal content is above the fold, no horizontal overflow, no truncated names, readable body text (≥14px), navigation complete.
- Test every page during implementation at: 1280×590, 1232×590, 1100×590 (non-maximised window), 1600×740 (80% comparison), 1440×800, and 360px mobile. Headless-browser viewports must be measured from inside the page; they do not reproduce the physical device exactly.

## 8. Mobile — Approved

- Every page works at 360px with no horizontal scrolling; text ≥14px, inputs 16px, touch targets ≥44px.
- Tables become list rows below 768px; dialogs become full-screen sheets below 576px.

## 9. Meetings — Approved (DEC-308)

- The portal has its own calendar with **month, week and day** views. Visibility: students only their own meetings (DEC-261); Batch Advisors meetings involving their assigned cohorts (DEC-260); Super Admin department-wide (DEC-262); CR/GR get no access to other students' meeting details (DEC-246).
- **Add to Google Calendar:** a prefilled Google Calendar event URL (title, date, start and end time, description) on confirmed meeting details and relevant cards/notifications. No Google Calendar API, no extra OAuth scopes, no new authentication flow. The portal stays the source of truth; adding to Google Calendar never changes a meeting's status. This clarifies DEC-061: it is a link, not an integration.

## 10. Scope guard

No attachments, social feeds, email notifications, extra analytics, unapproved dashboards, new roles, priorities or overdue queues, or cross-student data exposure. CR/GR remain permissions on student accounts.

## 11. Open questions

| ID | Question |
|---|---|
| O25 | Resolved: DEC-315, with DEC-317 to DEC-320 (Stage 4b details in COMPLAINTS_PART4_SPEC.md section 6) |
| O27 | Resolved: complaints by DEC-310, collective issues by DEC-324, Student Voice by DEC-326, meetings by DEC-328 |
| O28 | How cancellation requests appear and are recorded |
| O29 | Meeting status names and student actions on suggested times |
| O30 | Final production typography (Newsreader + Inter preferred) |
| O31 | Resolved: DEC-313 |
| O32 | Resolved: DEC-314 and DEC-316 (current academic term only) |
| O33 | Resolved: DEC-312 (no response-required classification or queue) |
| O34 | Theme switch: Light and Dark only, or also System |

## 12. Shell, components and motion (DEC-329)

This section takes precedence over the earlier layout notes where they differ. Palette, type roles and every privacy rule are unchanged.

- **Shell:** a 56px top bar (menu, wordmark, breadcrumb, quick search, + New, bell, avatar) and a 240px sidebar for every role, collapsing to a 64px rail. Phones use a drawer; students keep the bottom navigation.
- **Layout:** canvas `#F5F7F5`, white cards with a 16px radius and hairline border, content up to 1440px, one page scrollbar.
- **Components:** one each in `static/css/app.css` and `templates/includes/ui/`: greeting, stat tile, card header, filter chip, cohort chip, avatar, list/cards toggle, status journey, activity, pagination, dialog header, and line, bars, stacked bar and shaded grid charts.
- **Lists:** one markup shown as rows or item cards. Rows are one line from 1200px and two compact lines below it.
- **Detail:** main column plus a sticky panel. On phones: title, original, panel, history, with actions in a bottom bar.
- **Charts:** inline SVG, Forest and status colours, a written takeaway, and no scale derived from a hidden value. The stacked bar keeps a light segment between the two dark ones, because the status colours are too close for colour-blind readers when they touch.
- **People and structure (DEC-330):** Students, Staff, Academic Structure and Academic Terms reuse these components. The Django admin is an emergency fallback, linked only from the Super Admin's avatar menu.
- **Motion:** only `--dur-fast` (120ms), `--dur-base` (200ms), `--dur-slow` (320ms) and `--ease-out`. Opacity and transform where possible. Off under `prefers-reduced-motion`.
