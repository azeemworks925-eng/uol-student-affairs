# Complaints Part 4 — Super Admin Oversight, Categories, Notifications and Analytics

**Status:** Owner-approved scope and product decisions; specification submitted for review.
**Builds on:** Complaints Parts 1–3 merged into main (PRs #7–#11).
**Decisions:** DEC-310 to DEC-315 in docs/decisions/DECISIONS.md.
**Implementation must not begin until this specification is reviewed and merged.**

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

## 6. Super Admin Overview analytics

Keep analytics on the existing Super Admin Overview, following DEC-306: one written department summary followed by three numbered chapters. Each chapter gives its written takeaway before the visual and links into the relevant filtered complaint list.

### 6.1 Reporting period

Use one explicitly named academic-term window shared by all three analytics. Count complaints by submission date and use one consistent inclusive/exclusive boundary rule. Display term name and exact start/end dates.

The current academic structure has Batch, Semester and Section but no dated reporting-term entity. Add the smallest coherent academic-term record with name, start date, end date and one current-term designation managed by Super Admin. Validate date ranges and prevent ambiguous multiple current terms. Do not use a Batch label as a reporting term. If no current term exists, show a setup state; never silently fall back to all-time data.

### 6.2 Three analytics

1. **Distribution by section:** cohort map in academic order. Each cell represents one exact batch + semester + section. A real cohort with zero complaints is visually distinct from a nonexistent cohort. Clicking a cell opens the complaint list filtered to that cohort and reporting period.
2. **Category share:** counts and percentages by category for the period. Include inactive categories if they have complaints in the period. State the denominator and use it consistently.
3. **Resolved vs not resolved:** Resolved = status Resolved. Not resolved = Received + Under Review + Rejected. Rejected complaints must be separately identified in the written takeaway and never described as awaiting action. Show counts, percentages, denominator and period.

### 6.3 Small-cohort privacy

Suppress cohort-level breakdowns where the cohort has fewer than five active students at the relevant reporting point. Apply complementary suppression: hiding one cell is insufficient if its exact value can be derived by subtracting visible cells from a total. Suppress at least one additional value or affected total whenever required. If safe suppression cannot be guaranteed for a chart/filter combination, withhold that aggregate. Show department totals only where they cannot reveal a suppressed value. Never expose names, SAP IDs or individual complaint titles in analytics.

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

Analytics:
- All charts share one configured academic-term period and submission-date rule.
- Counts and percentages reconcile with the underlying aggregate.
- Rejected cases are not described as awaiting action.
- Zero-complaint real cohorts differ from nonexistent cohorts.
- Cohorts below five active students are suppressed.
- Complementary suppression prevents arithmetic recovery through totals and filters.
- No individual identity appears in aggregate output.
- Missing/invalid current-term configuration shows a setup state.

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
4. Academic-term configuration and privacy-safe analytics on the existing Overview.
5. Full regression, database/browser acceptance, and technical documentation updates.

Split into focused PRs if that reduces review and regression risk. Do not combine unrelated work just to reduce PR count.

## 10. Decision boundaries

DEC-310 to DEC-315 resolve the complaint-specific portions of O27, O28, O33, O31, O32 and O25. The separate BA routing question for collective issues, Student Voice and meetings remains open. Other OPEN items are not resolved by this specification.
