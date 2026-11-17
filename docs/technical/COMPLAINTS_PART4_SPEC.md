# Complaints Part 4 — Super Admin Oversight, Categories, Notifications and Analytics

**Status:** Owner-approved scope and product decisions. Merged in PR #12. Stages 1–4a are implemented and merged (PRs #14, #15, #16 and #18). Section 6 is the final Stage 4b specification; Stage 4b is **not implemented**.
**Builds on:** Complaints Parts 1–3 merged into main (PRs #7–#11).
**Decisions:** DEC-310 to DEC-322 in docs/decisions/DECISIONS.md.
**Stage 4b implementation must not begin until the section 6 update (DEC-316 to DEC-322) is reviewed and merged.**

## 1. Purpose and scope

Part 4 completes the complaint workflow for department-wide administration and connects existing complaint records to the approved notification and analytics foundations.

In scope:
1. A Super Admin complaint workspace with department-wide visibility, search, filters, case history, response/status actions, and manual responsible-owner assignment/reassignment/take-over.
2. Super Admin category and subcategory management, including activation/deactivation.
3. A reusable in-app notification foundation and the complaint notification events whose recipients are defined by DEC-270.
4. The three approved complaint analytics on the existing Super Admin Overview: distribution by section, category share, and resolved versus not resolved.
5. Documentation, permissions, tests, accessibility and responsive acceptance.

Explicitly out of scope: new roles; separate department-admin portal; public feed; attachments; email notifications; chat; priorities, overdue indicators or priority queues; new complaint statuses or transitions; deletion; cancellation approval; automatic owner assignment; Student Voice, meeting or collective-issue feature implementation; a separate Statistics destination; changes to the approved Forest palette or Design D.

## 2. Invariants and permissions

- Every Super Admin route requires an authenticated, active Super Admin. Role is derived from the authenticated account, never request data.
- Super Admin complaint queries use complaints.permissions.visible_complaints(user); they may see every complaint.
- Batch Advisors remain limited to exact batch + semester + section assignments (DEC-205, DEC-229). Filters only narrow the permission-scoped queryset.
- Students see only their own complaints. They never see responsible-owner identity or internal owner-change events.
- All mutations use the complaint service layer and append immutable events. Never edit the original description, delete complaints or rewrite history.
- Preserve existing statuses, allowed transitions, mandatory resolution/rejection notes, separate Respond and Update status actions, and stale-status protection.
- No priority, overdue, response-required or “Waiting for you” classification (DEC-226, DEC-312).
- Category deactivation preserves historical references; inactive values remain readable and filterable but cannot be selected for new submissions.
- Notifications are private to recipients and do not grant access to linked records. Destination views re-check permissions.
- Aggregate analytics show no student names, SAP IDs or individual complaint titles. Apply DEC-315 suppression.
- Preserve Design D, Forest Light/Dark tokens, semantic status colours, keyboard accessibility and responsive behaviour.

## 3. Super Admin complaint workspace

### 3.1 List and search

Add a Complaints destination to the existing Super Admin navigation. The list begins with visible_complaints(request.user), not an unrestricted model query.

Search by complaint reference, title, student full name and SAP ID. Filters:
- exact cohort (batch + semester + section);
- status: All, Received, Under Review, Resolved, Rejected;
- category, including inactive categories present on historical records;
- responsible owner: eligible advisor, Super Admin take-over, or Unassigned.

Default status is All. Sort by latest activity (default) or newest submitted. Do not introduce age-based priority. Paginate and preserve list state across detail, back navigation and POST redirects.

Rows show reference, title, student full name and SAP ID, exact cohort at submission, category, status, responsible owner or Unassigned, and last activity. Empty states distinguish no complaints, no filter matches and an empty selected cohort.

### 3.2 Case detail and actions

Reuse the existing complaint presentation and service layer. Show original complaint, submission-time cohort, category/subcategory, status, status journey and complete staff history. Staff history is newest first. Super Admins and BAs may see owner-change events; students never do.

Show student name and SAP ID, not student email. Do not add “Other complaints from this student”. Respond and Update status remain separate. Use existing allowed transitions, required notes and expected_status stale-write protection. Super Admin may perform existing staff actions on any complaint through complaints.services.

### 3.3 Responsible owner

- A Super Admin manually assigns, reassigns or takes over a complaint. No automatic assignment or round-robin.
- Eligible owners are active BAs assigned to the complaint’s exact batch + semester + section, or an active Super Admin.
- Repeating the current assignment is a no-op; actual changes create one immutable RESPONSIBLE_CHANGED event through services.assign_responsible.
- Unassigned stays explicitly Unassigned; opening a complaint does not assign it.
- Owner designation is for accountability, not authorization. All BAs assigned to the exact cohort retain existing visibility and action rights.
- Owner identity and owner-change history remain hidden from students. No owner-assignment notification is introduced.

## 4. Category and subcategory management

Provide a Super Admin-only management destination within the existing configuration area.

Support creating, renaming, reordering, activating and deactivating categories and subcategories. A subcategory belongs to exactly one category. Enforce uniqueness and parent-child consistency server-side.

No hard deletion. Deactivation preserves foreign-key references and historical complaints. Active categories and subcategories are offered on new complaint forms. Inactive values remain visible on historical detail and filter results. A subcategory under an inactive category is unavailable for new submissions regardless of its own active flag.

Do not reclassify existing complaints when a category is renamed or deactivated. Mutations use POST and CSRF protection.

## 5. In-app notifications

### 5.1 Shared foundation

Implement a reusable notification model/service, not complaint-specific ad hoc messages. Each notification has one recipient, stable event type/source identity, concise title/body, creation time, read state/read timestamp, and a safe internal destination or record reference.

Enforce deduplication per recipient/source event with a database uniqueness constraint where appropriate. Create notifications transactionally with source events, or through a reliable post-commit mechanism so rolled-back actions cannot leave orphan notifications.

Provide a header entry point, unread count, recent-notification list and mark-read behaviour. Notifications are recipient-private; guessed IDs or URLs must not expose another user's data. Opening marks read and redirects only to an internal destination, whose view performs its normal permission check.

In-app only: no email, push, SMS, external messaging or extra OAuth scopes. No broadcast mechanism or arbitrary recipient selection.

### 5.2 Complaint producers in this part

Only these complaint events produce notifications in Part 4:

| Event | Recipient | Destination |
|---|---|---|
| BA or Super Admin changes complaint status | Student who submitted that complaint | That student's complaint detail |
| BA or Super Admin responds | Student who submitted that complaint | That student's complaint detail |

Create one notification per qualifying immutable source event. Status notification states the new status factually. Do not duplicate rejection/resolution notes into notification previews. A response notification may include a safely truncated preview; full text stays on the complaint page. Do not notify the actor about their own action.

Do not notify staff for submission, further information, “Still not resolved”, cancellation requests or owner assignment. Do not notify every BA in a shared cohort; DEC-270 does not define those recipients.

### 5.3 Future compatibility

The foundation should support future producers for the already-approved DEC-270 events: official Student Voice answers, meeting confirmation/rescheduling/cancellation, and new CR/GR issues. Do not implement those producers or invent their recipients in this part.

## 6. Super Admin Overview analytics (Stage 4b)

**Status:** final specification, not implemented. **Decisions:** DEC-090, DEC-205, DEC-228, DEC-281, DEC-306, DEC-313 to DEC-322. Where this section and `DECISIONS.md` disagree, `DECISIONS.md` wins.

The analytics stay on the existing Super Admin Overview (`super_admin_home`), following DEC-306:
- one written department summary, then three numbered chapters;
- each chapter gives its written takeaway before its visual, and links into records only where section 6.5 allows.

There is no separate dashboard, no new route and no Batch Advisor analytics in this stage (DEC-321). Every rule below concerns only what the Overview displays; section 6.6 explains how this relates to operational complaint access.

### 6.1 Reporting period (DEC-314, DEC-316)

- **Term:** the **current** academic term only, from `academics.services.current_term()`. There is no historical term selector and no comparison between terms.
- **Window:** the term's reporting window, from the existing rule `term_window()` (also `AcademicTerm.window()`; see `docs/technical/ACADEMIC_TERMS.md` section 2):
  - start date at 00:00 Asia/Karachi, inclusive;
  - the day after the end date at 00:00 Asia/Karachi, exclusive;
  - a complaint belongs to the window when `created_at >= start` and `created_at < end`.

  The window is calculated once per page and used by all three analytics.
- **Shown with it:** the term name and its exact dates (`AcademicTerm.dates_label`), in the summary and in the withheld state.
- **Setup state:** with no current term, the Overview shows:
  - a setup state explaining that a current academic term must be set;
  - a link to the academic-term administration (Configuration → Academic Structure → Academic terms);
  - **no** figures, totals, takeaways or analytics drill-down links.

  It never falls back to all-time figures.
- **Status counted:** the status of each complaint as it stands when the page is generated (see 6.3, analytic 3). The window decides which complaints are counted, by submission time, not which status they had.

### 6.2 Cohorts and active students (DEC-205, DEC-317)

- **Cohort:** an exact batch + semester + section combination.
- **Real cohorts:** the union of the cohorts of:
  1. existing advisor assignments (`AdvisorAssignment`);
  2. existing student profiles (`StudentProfile`);
  3. complaints submitted in the reporting window (`Complaint.batch`, `semester`, `section`, recorded at submission).
- **Inactive entries:** cohorts made of inactive batches, semesters or sections are included when they are in this union.
- **Active students of a cohort:** counted when the page is generated, as user accounts that are active, have the student role and have a student profile in that exact cohort. Inactive accounts, staff and accounts without a student profile are not counted.

### 6.3 The three analytics

The department total `T` is the number of complaints in the reporting window. It is the denominator of every percentage, and each chapter states it. Rounding of percentages is an engineering choice, but each percentage is calculated from the counts shown with it.

**Department summary.** A sentence built from `T` and the term name and dates, for example the number of complaints submitted in the term. It replaces the current placeholder headline.

**1. Distribution by section (cohort map).**
- **Grid:**
  - **Order:** the existing academic order (DESIGN_PLAN.md section 6): Semester 1 to 8. Within a semester, batches and sections follow their existing ordering (`Batch` and `Section` are ordered by name). No database field is added for ordering (DEC-321).
  - **Cells:** each cell is one exact cohort. The grid covers the semester-and-batch rows and the section columns present among the real cohorts. A combination inside the grid that is not a real cohort is a **nonexistent cohort**.
- **Cell states** (DEC-306, DEC-318):

  | Cell | Shown as | Link |
  |---|---|---|
  | Real cohort, visible, with complaints | Its count | Yes (6.5) |
  | Real cohort, visible, with zero complaints | "No complaints" (solid cell) | Yes (6.5) |
  | Nonexistent cohort | Hatched, no number | No |
  | Real cohort, suppressed (primary or complementary) | One neutral hidden-value presentation, identical for both kinds of suppression, with no number | No |

**2. Category distribution (DEC-281, DEC-321).**
- **Which categories:**
  - every **active** category, including those with zero complaints in the window;
  - an **inactive** category only when it has at least one complaint in the window, labelled as inactive (for example "(inactive)");
  - an inactive category with no complaints in the window is not listed.
- **Each row:** its count and its percentage of `T`.
- **Order:** the existing category ordering (position, then name).
- **Scope:** department-level only. There is no breakdown of categories by cohort.

**3. Resolved versus not resolved (DEC-313).**
- **Resolved:** status `resolved`.
- **Not resolved:** statuses `received`, `under_review` and `rejected`.
- **Shown:** counts and percentages of `T` for both groups.
- **Takeaway:** it identifies rejected complaints separately and never describes them as awaiting action. Received and Under Review complaints may be described as still being handled. Example: "9 are not resolved: 6 are still being handled and 3 were rejected."
- **Scope:** department-level only, with no breakdown by cohort.

**Takeaways (all chapters):**
- They are calculated from displayed values only.
- They never name, rank, compare or otherwise describe a suppressed cohort or value. For example, "the most complaints" refers only to the cohorts shown, and says so.
- They never include student names, SAP IDs or complaint titles.

### 6.4 Suppression (DEC-315, DEC-318, DEC-319)

- **Primary suppression:**
  - **Rule:** a real cohort with fewer than five active students (6.2) is suppressed, whatever its complaint count, including zero.
  - **Scope:** suppression applies to cohort-level values. The category and status chapters have no cohort breakdown.
- **Complementary suppression:**
  - **Requirement:** further cohort values are suppressed so that **no suppressed value can be reconstructed** from the displayed values. Those include every visible cell and the department total `T`, which appears in the summary and in chapters 2 and 3.
  - **Minimum acceptance criteria:** a single suppressed cell, or a set of suppressed cells whose total can be inferred to be zero, never satisfies this requirement.
  - **Engineering choices:** the algorithm and how complementary cells are chosen. The choice should be stable rather than dependent on small changes in counts. This does not remove every inference risk (6.7).
- **No hidden values in the page:** the analytics code passes the template only values that may be displayed. A suppressed value is `None`, or absent, and is never in the HTML, attributes, hidden fields, embedded data or text.
- **Withheld state (DEC-319):**
  - **When:** all three analytics, the department totals and the takeaways are withheld if:
    - (a) `T` is zero and at least one real cohort requires suppression; or
    - (b) complementary suppression cannot be achieved safely for a non-zero `T`. For example, the only real cohort is a suppressed cohort.
  - **What is shown:** the term name and dates, and one neutral privacy explanation.
  - **The same in both cases:** the text and layout must not reveal which case applied, or whether the total is zero.
  - **No figures or links:** no number and no analytics drill-down link is shown. The existing Manage links stay.

### 6.5 Drill-down links

- **Visible cells:** each one, including a visible zero cell, links to the Super Admin complaint list filtered to that cohort and the reporting term: `super_admin_complaints?cohort=<batch_id>.<semester_id>.<section_id>&term=<current term id>`.
- **Category rows:** link with `?category=<id>&term=<id>`.
- **Status figures:**
  - Resolved links with `?status=resolved&term=<id>`.
  - "Not resolved" has no single link. Its components link separately to `received`, `under_review` and `rejected`, using the existing status filter; no new filter value is added.
- **Not linked:** suppressed and nonexistent cells; and nothing at all in the setup or withheld state. Their markup carries no hidden value and no cohort-specific URL.
- **Access:** the links lead only to the existing Super Admin complaint list. It keeps its own access rules (`super_admin_required`, `visible_complaints`) and its existing filters. Stage 4b changes nothing there (6.6).

### 6.6 Aggregate analytics privacy versus operational access (DEC-320)

Suppression protects the **analytics output**. It does not limit the Super Admin's authorised access to individual complaint records (DEC-228):
- **Unchanged:** the Super Admin complaint list, including its cohort and term filters (Stage 1 and Stage 4a), is not blocked, blurred or restricted for small cohorts.
- **Consequence:** an authorised Super Admin can therefore count individual records there, including for cohorts that the analytics suppress. This is a known, documented limitation of the analytics privacy guarantee. It is not a defect to be fixed by restricting operational access.
- **No path from the Overview itself:** the analytics interface must still give no direct or indirect path to a suppressed value. There are no links, URLs or data for suppressed cells (6.4, 6.5).
- **Wording:** neither the documentation nor the interface describes the analytics as anonymous, or claims that hidden counts cannot be obtained by an authorised administrator.

### 6.7 Residual privacy risks and review (DEC-322)

These risks remain and are documented, not eliminated:
- **Operational access:** counts can be obtained from authorised record access (6.6).
- **Comparing visits:** if `T` rises while every visible cell stays the same, a new complaint was in a suppressed cohort.
- **Term changes:** changing the current term or editing its dates changes the window; comparing the figures before and after can narrow down suppressed values.
- **Membership changes:** a cohort reaching five active students shows values that were suppressed before. Students are counted when the page is generated, while complaints keep their cohort at submission, so a cohort's suppression can change over time.
- **Structural information:** a suppressed cell shows that the cohort is small, or was chosen as a complement.
- **Small department-level figures:** the category and status chapters are not suppressed by DEC-315. A very small count (for example one complaint in a category) can still be meaningful to someone who knows the department.
- **Complement selection** reduces, but does not remove, inference across visits.

The analytics are not described as completely anonymous. **A privacy review is required before any pilot use.**

### 6.8 Not in Stage 4b

- a historical term selector or term comparison;
- Batch Advisor analytics or statistics (DEC-280);
- a separate dashboard or Statistics destination (DEC-306);
- new complaint filters or changes to complaint permissions;
- charts beyond the three analytics;
- exports;
- new database fields for ordering.

No migration is expected.

## 7. Architecture and migration planning

Follow the existing Django app and template conventions. Expected areas:
- Super Admin complaint views/URLs/templates in the existing complaints app.
- Category management within the existing complaints configuration area.
- Reusable notification model, services, permissions, views and templates in a coherent notification module.
- Academic-term model and Super Admin configuration integrated with academics.
- Analytics query/presentation code separate from templates; templates render prepared aggregates only.

Reuse visible_complaints, get_visible_complaint, can_manage_complaint and complaint services. Preserve exact-cohort rules. Use Django Templates, approved CSS tokens/components and progressive enhancement.

Before implementation, the implementation plan must enumerate every migration and explain why it is needed. Do not alter the existing MySQL installation or other project databases.

## 8. Acceptance and testing

Permissions and complaint operations:
- Active Super Admin can list/open all complaints; anonymous, student, BA and inactive-user access is denied appropriately.
- BA exact-cohort isolation remains intact; partial matches and forged filters never broaden access.
- All BAs assigned to a cohort retain visibility/action rights regardless of owner.
- Assignment accepts only active eligible owners; rejects wrong-cohort BAs, students and inactive users.
- Same-owner assignment creates no duplicate event; real changes create exactly one immutable event.
- Owner changes appear in staff history, never student history or student context.
- Super Admin response/status use existing service rules; response does not change status; stale expected_status is rejected.
- Original description, historical category references and event history remain intact.

Categories:
- Only active category/subcategory values are offered on new submissions.
- Inactive values remain readable and filterable on historical complaints.
- Deactivation never deletes records or cascades into complaint history.
- Duplicate names, invalid parent-child pairs and forged IDs are rejected.

Notifications:
- Each qualifying status/response event creates exactly one notification for its student.
- Excluded events and unrelated recipients receive none.
- Recipient isolation, guessed IDs and destination permission checks are tested.
- Opening marks read; unread count/read state persist.
- Rolled-back actions leave no orphan notification.
- No external/email notification is sent.

Analytics (Stage 4b; section 6):
- All three analytics use the current term's window (6.1); complaints exactly on the window boundaries are counted correctly.
- No current term shows the setup state, with no figures and no all-time fallback.
- Counts and percentages reconcile with `T`, the cohort, category and status totals.
- Rejected cases are identified separately and not described as awaiting action.
- Zero-complaint real cohorts differ from nonexistent cohorts; cohorts come from the real-cohort union (6.2).
- Active categories with zero complaints are listed; inactive categories appear only with complaints in the window, labelled.
- Cohorts below five active students, counted at page generation, are suppressed.
- No suppressed value can be reconstructed from the displayed values (for example, an exhaustive check over small generated grids).
- No suppressed value appears anywhere in the page: links, URLs, attributes, hidden fields, embedded data or takeaways.
- Primary and complementary suppression look the same.
- Both withheld cases (6.4) show the same withheld state with no figures.
- Visible cells link to the complaint list with the correct cohort and term; suppressed and nonexistent cells do not link.
- No student names, SAP IDs or complaint titles appear in the analytics.
- The Super Admin complaint list and its filters are unchanged (6.6).

Quality:
- Full test suite on MySQL and SQLite; identify MySQL-specific skips.
- Run manage.py check, makemigrations --check --dry-run, migrate --check, compileall and git diff --check.
- Browser acceptance at 1280×590, 1232×590, 1100×590, 1600×740, 1440×800 and 360px. Check keyboard navigation, focus, overflow, long names, empty/error states.
- Verify Student and Batch Advisor complaint workflows remain unchanged.
- Review every migration and test on both databases. No destructive migration.

## 9. Implementation sequence

1. Super Admin complaint workspace and owner assignment.
2. Category/subcategory management.
3. Notification foundation and the two approved complaint producers.
4. Academic-term configuration (Stage 4a, merged in PR #18) and then privacy-safe analytics on the existing Overview (Stage 4b, section 6).
5. Full regression, database/browser acceptance, and technical documentation updates.

Split into focused PRs if that reduces review and regression risk. Do not combine unrelated work just to reduce PR count.

## 10. Decision boundaries

DEC-310 to DEC-315 resolve the complaint-specific portions of O27, O28, O33, O31, O32 and O25; DEC-316 to DEC-322 settle the Stage 4b analytics details. The separate BA routing question for collective issues, Student Voice and meetings remains open. Other OPEN items are not resolved by this specification.
