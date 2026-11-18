# UOL Student Affairs — Decision Register

**Purpose:** The authoritative record of what has been decided, what has been replaced, and what is still open.
**Last reconciled:** 2026-11-18
**Canonical location:** This file in the GitHub repository. If any other document or copy disagrees with this file, this file wins.

## How to read this file

| Status | Meaning |
|---|---|
| CONFIRMED | Agreed by the project owner. Do not change without the owner's approval. |
| SUPERSEDED | An older decision that has been replaced. Kept for history only. |
| OUT OF SCOPE | Deliberately left outside V1 or outside current requirements. Do not reopen without the owner. |
| OPEN | Not decided. Do not assume an answer. |

Rules for every collaborator (human or AI):

- Only the project owner can approve a product decision.
- Never resolve an OPEN item by assumption.
- When a decision changes, mark the old entry SUPERSEDED, add or revise the new entry, and record the change in `DEVELOPMENT_LOG.md`.
- IDs are permanent labels. They are never reused or renumbered. IDs DEC-001 to DEC-120 date from the first reconciliation; IDs from DEC-200 were added in the second; IDs from DEC-300 record design decisions. "(revised)" marks an earlier entry whose wording was extended.

---

## 1. CONFIRMED decisions

### 1.1 Product and governance

| ID | Decision |
|---|---|
| DEC-001 | UOL Student Affairs is an independently developed academic project. It is not commissioned, approved or deployed by The University of Lahore, and must never be described as such. |
| DEC-002 | The initial target is the Software Engineering Department. |
| DEC-003 | The project owner makes all final product and architecture decisions. AI collaborators propose, challenge and explain; they do not approve. |
| DEC-004 | The GitHub repository is the canonical source of truth for project context. Copies used by Claude Desktop, Claude Code and ChatGPT must mirror the committed versions. |
| DEC-005 | No further stakeholder interviews or surveys are planned at this stage. |

### 1.2 Authentication and accounts

| ID | Decision |
|---|---|
| DEC-010 (revised) | Authentication is Google OAuth. All roles use one shared Google login page. |
| DEC-200 | There is no role selector. Django checks the authenticated Google identity against the user records in MySQL and directs the user to the correct dashboard. |
| DEC-011 (revised) | Student emails follow the exact format of an eight-digit SAP ID followed by `@student.uol.edu.pk`. The SAP ID is extracted from the verified student email. |
| DEC-201 | Student registration collects full name, batch, semester and section. Department defaults to Software Engineering. There is no Morning/Evening field. |
| DEC-012 (revised) | Students self-register after Google login and become active immediately. There is no individual Super Admin approval. |
| DEC-202 | Students cannot submit profile correction requests. The Super Admin can correct student information. |
| DEC-014 | The Super Admin is the Head of Batch Advisors and has department-wide oversight. |
| DEC-203 | The initial Super Admin account must be configured securely through a bootstrap process. |
| DEC-206 | Multiple Super Admin accounts are permitted. The bootstrap process creates only the first (DEC-203); further Super Admins are created by an existing Super Admin, using an official UOL staff email. At least one Super Admin must remain active at all times: the last active Super Admin cannot be deactivated. Confirmed by the owner on 2026-11-16. |
| DEC-013 (revised) | The Super Admin creates Batch Advisor (BA) accounts by entering the teacher's name and official UOL email, then assigning semesters and sections. There is no BA self-registration or application process. BAs use the same Google login page. |
| DEC-204 | A BA can have multiple sections and semesters. Sections can be split among BAs. Multiple BAs can be assigned to one section. Assignments can change. The existing BA structure must not be hardcoded. |
| DEC-015 (revised) | BA access is determined by explicit assignments. BAs see only their assigned sections. |
| DEC-205 | Every BA assignment is tied to one cohort: the exact batch + semester + section combination. A BA may hold multiple cohort assignments, and multiple BAs may share the same cohort. All access-control checks, now and in future modules, must match all three fields; a partial match (for example, the same semester and section in another batch) grants no access. Confirmed by the owner on 2026-11-16. |
| DEC-016 (revised) | Every section has exactly one CR and one GR. GR means Girls Representative. They are existing student accounts with additional permissions, not separate account types or login systems. |

### 1.3 Academic structure and student records

| ID | Decision |
|---|---|
| DEC-020 (revised) | Batches, semesters and sections are database-managed. The Super Admin can add, edit and deactivate academic structure entries. |
| DEC-210 | Deactivating an academic structure entry preserves its associated students and historical records. |
| DEC-021 (revised) | There is no automatic semester promotion. The Super Admin manually updates students' semester and section. |
| DEC-211 | Student profile changes are audited. |
| DEC-212 | Deactivating a student is a soft delete. It preserves historical records and revokes representative permissions. |

### 1.4 Complaints

| ID | Decision |
|---|---|
| DEC-030 | Complaints are identified and linked to student accounts. There are no anonymous complaints and no secret access codes. |
| DEC-031 (revised) | Each complaint receives a unique reference ID. Students have an authenticated "My Submissions" view with status history and advisor responses. |
| DEC-220 | The main categories initially include Academic, Non-academic, Personal/Wellbeing and Other. Categories and subcategories are dynamically managed by the Super Admin. |
| DEC-221 | Statuses are Received, Under Review, Resolved and Rejected. A rejection reason is mandatory and visible to the student. A resolution note is mandatory. |
| DEC-222 | After resolution, a student can indicate "Still not resolved", which returns the complaint to Under Review. |
| DEC-223 | Students can add further information without losing the original description or history. |
| DEC-224 | Students can request cancellation but cannot delete complaints. |
| DEC-225 | A duplicate complaint warning is allowed. Duplicate submissions are not blocked. |
| DEC-226 | There are no complaint priority levels, no three priority queues and no 15-day overdue indicator. |
| DEC-227 | Complaints are routed to BAs based on section assignments. All BAs assigned to a section can see its complaints, but one designated BA is the responsible owner of each individual complaint. |
| DEC-228 | The Super Admin can open, review, reassign, take over and respond to any complaint. |
| DEC-310 | A Super Admin manually designates the responsible owner of a complaint. Eligible owners are active Batch Advisors assigned to the complaint's exact batch + semester + section, or an active Super Admin taking it over. There is no automatic assignment. An unassigned complaint remains unassigned. Owner designation is for accountability; all advisors assigned to that exact cohort retain their existing visibility and action permissions. |
| DEC-229 | Students see only their own complaints. BAs see only complaints from their assigned sections. |
| DEC-230 | There is no special complaint-routing hierarchy for complaints against administrators or the Super Admin in V1. |

### 1.5 CR/GR collective issues

| ID | Decision |
|---|---|
| DEC-040 (revised) | CR/GR have a separate collective issue workflow. Either representative can independently raise a collective issue for their own section. |
| DEC-240 | CR and GR have identical permissions and responsibilities and retain normal student permissions. A student can hold only one representative assignment, for one section. |
| DEC-245 | BAs can assign and replace the CR and GR of their assigned sections. The Super Admin can also manage these assignments. |
| DEC-241 | A collective issue appears on the home page of students in that section. A student can support an issue once. Support cannot be withdrawn or changed. CR/GR can support their own issue. There are no student comments. |
| DEC-242 | Published issues cannot be edited or deleted by CR/GR in V1. |
| DEC-243 | The BA receives the issue and responds privately to the CR/GR. Other students cannot see the advisor's response. After the advisor responds, the issue disappears from student home pages. CR/GR retain the issue and the private response in their dashboard. The underlying record and support count are preserved. |
| DEC-244 | Statuses are Received, Under Review and Resolved. The BA can update the status and provide a short official response. A resolution note is mandatory and private to CR/GR. |
| DEC-246 | CR/GR cannot see individual complaints, private Student Voice submissions or other students' meeting details. |
| DEC-247 | The Super Admin has department-wide oversight of collective issues. |

### 1.6 Student Voice

| ID | Decision |
|---|---|
| DEC-050 | Student Voice has exactly three types: Ideas, Questions and Feedback. |
| DEC-250 | Student Voice replaces the previous Suggestions and Appreciation submission types. |
| DEC-251 | Submissions are typed text. There is no tracking ID. |
| DEC-252 | Ideas and Feedback are reviewed by the relevant BA. An individual response is not mandatory. |
| DEC-051 (revised) | A Question receives one official BA answer, visible beside the question. |
| DEC-052 | There is no chat or follow-up messaging. |
| DEC-253 | Submissions are private to the submitting student, the relevant BA and the Super Admin. Other students and CR/GR cannot see them. |
| DEC-254 | The Super Admin has oversight of all submissions. There is no dedicated Student Voice section on the Super Admin dashboard; it is handled through the relevant BA workflow. |

### 1.7 Meetings

| ID | Decision |
|---|---|
| DEC-060 (revised) | Students can request a meeting with their assigned BA, giving a reason and preferred availability. The BA can accept/confirm, suggest another time, or decline with a reason. |
| DEC-260 | A BA can also invite students. A BA can view and manage meetings involving assigned students, and can schedule, reschedule and cancel meetings. |
| DEC-061 (revised) | The BA calendar has month, week and day views. It is an internal portal calendar, not a Google Calendar integration. |
| DEC-261 | Students see only their own meetings: date, time, location and status. |
| DEC-262 | The Super Admin has department-wide meeting oversight. |
| DEC-263 | There is no chat in the meeting workflow. |

### 1.8 Notifications

| ID | Decision |
|---|---|
| DEC-070 (revised) | Notifications are in-app only. There are no email notifications in V1. |
| DEC-270 | Notification events include: complaint status changes and advisor responses; official answers to Student Voice questions; meeting confirmation, rescheduling and cancellation; and new CR/GR issues in the student's section. Notifications link to the relevant record. |
| DEC-311 | A student's complaint cancellation request is recorded only. It does not change status, cancel or delete the complaint, or trigger an approval/decline workflow. |

### 1.9 Analytics and dashboards

| ID | Decision |
|---|---|
| DEC-090 (revised) | Analytics must be useful, not decorative. Aggregate reporting must not expose individual student identities; no individual student names appear in aggregate charts. |
| DEC-280 | BAs see statistics for their assigned sections. The Super Admin sees department-wide statistics. |
| DEC-281 | Useful analytics include complaint categories and percentages, section-wise complaint distribution, and resolved versus unresolved complaints. |
| DEC-312 | No complaint event is given a response-required classification or a "Waiting for you" queue. Workspaces show factual statuses and recorded history only; they do not imply urgency through an unapproved queue. |
| DEC-313 | For complaint analytics, Resolved means status Resolved. Not resolved means Received + Under Review + Rejected. Rejected complaints must be separately identified and never described as awaiting action. |
| DEC-314 | All three Super Admin complaint analytics use one explicitly named academic-term reporting window, based on complaint submission date. The term name and exact start/end dates are displayed. Missing current-term configuration produces a setup state, not an implicit all-time report. |
| DEC-315 | Aggregate analytics suppress cohort-level breakdowns for cohorts with fewer than five active students. Complementary suppression must prevent hidden values being derived from displayed totals or other cells; when this cannot be guaranteed, suppress the affected total or aggregate. Analytics never expose individual student identities. |
| DEC-316 | Stage 4b reporting period (extends DEC-314). The Super Admin complaint analytics use the **current** academic term only. The window is the existing academic-term rule (`term_window()`, also `AcademicTerm.window()`): the term's start date at 00:00 Asia/Karachi, inclusive, to the day after its end date at 00:00 Asia/Karachi, exclusive. It is applied to each complaint's submission time (`created_at`). With no current term, the Overview shows a setup state and never falls back to all-time figures. There is no historical term selector or term comparison. Confirmed by the owner on 2026-11-18. |
| DEC-317 | Cohort universe and active students for complaint analytics (with DEC-205 and DEC-306). Cohorts are exact batch + semester + section combinations. The real cohorts are the union of the cohorts of existing advisor assignments, of existing student profiles, and of complaints submitted in the reporting window. Active students are counted when the analytics page is generated: active user accounts with the student role and a student profile in that exact cohort. A real cohort with zero complaints is shown differently from a cohort that does not exist. Confirmed by the owner on 2026-11-18. |
| DEC-318 | Presentation of suppressed analytics values (extends DEC-315). Primary suppression (fewer than five active students) and complementary suppression use the same neutral hidden-value presentation. A suppressed value is never exposed through the analytics interface: not in links or drill-downs, URLs or query parameters, tooltips, HTML attributes, hidden fields or embedded data, takeaways or any other text derived from the analytics. A visible cohort value may link to the Super Admin complaint list filtered to that cohort and the reporting term. Analytics never include student names, SAP IDs or complaint titles. The suppression algorithm and how complementary cells are chosen are engineering decisions, provided that no hidden value can be reconstructed from displayed values and that hidden values are never passed to templates. Confirmed by the owner on 2026-11-18. |
| DEC-319 | Withheld analytics (extends DEC-315). All three analytics, the department totals and the takeaways are withheld when either (a) the department complaint total for the reporting window is zero and at least one real cohort requires suppression, or (b) complementary suppression cannot be achieved safely for a non-zero total. Both cases use the same withheld state: the reporting period and a neutral privacy explanation. Confirmed by the owner on 2026-11-18. |
| DEC-320 | Aggregate analytics privacy is separate from operational complaint access. DEC-315, DEC-318 and DEC-319 apply to the analytics output only. They do not restrict the Super Admin's authorised access to individual complaints (DEC-228), including the existing complaint-list cohort and term filters, so a Super Admin can still count records there, including for cohorts that the analytics suppress. This is a documented limitation of the analytics privacy guarantee; the analytics are not described as anonymous. Confirmed by the owner on 2026-11-18. |
| DEC-321 | Analytics content and placement (with DEC-281, DEC-306 and DEC-313). The cohort distribution keeps the existing academic order (Semester 1 to 8), with no new database field for ordering. The category distribution lists every active category, including those with zero complaints in the reporting window, and lists an inactive category only when it has complaints in the window, labelled as inactive. Resolved versus not resolved follows DEC-313. The analytics stay on the existing Super Admin Overview: there is no separate dashboard, and Batch Advisor statistics (DEC-280) are not part of this stage. Confirmed by the owner on 2026-11-18. |
| DEC-322 | Residual privacy risks of the complaint analytics are documented, for example comparing figures across visits or after the current term or its dates change, and cohorts crossing the five-student threshold. Deterministic complement selection is not claimed to remove every inference risk. The analytics are not described as completely anonymous, and a privacy review is required before any pilot use. Confirmed by the owner on 2026-11-18. |
| DEC-282 | Student dashboard: (1) Your Actions: pending complaint updates, unanswered questions, meeting requests. (2) Section Updates: active CR/GR issues awaiting student support. (3) Quick Access: Submit Complaint, Student Voice and My Meetings. |
| DEC-283 | BA dashboard: compact overview, actionable complaint inbox, search and filters, complaint details, CR/GR issues, meeting calendar and useful section statistics. The section filter defaults to All Assigned Sections. |
| DEC-284 | Super Admin dashboard: overview, students, Batch Advisors, CR/GR management, configuration, calendar and department-wide oversight. |

### 1.10 V1 exclusions

| ID | Decision |
|---|---|
| DEC-080 | No attachments in V1. |
| DEC-081 | No public social feed in V1. |
| DEC-082 | No separate department-admin, Administrator or HOD portal in V1. |
| DEC-083 | No general university or department announcements in V1. |

Other exclusions are stated where they belong: anonymous complaints (DEC-030), priority levels, queues and overdue indicator (DEC-226), chat (DEC-052, DEC-263), email notifications (DEC-070), automatic promotion (DEC-021), Google Calendar integration (DEC-061), student comments on collective issues (DEC-241).

### 1.11 Technology and environment

| ID | Decision |
|---|---|
| DEC-100 (revised) | Stack: Python 3.13, Django 5.2 LTS, MySQL, Django Templates, HTML, CSS, vanilla JavaScript, Bootstrap 5.3, HTMX only where genuinely useful, Django testing framework and pytest, Git and GitHub. Development currently runs on the existing MySQL Server 8.0.44. MySQL 8.4 LTS remains a future evaluation and target question (O19); it is not installed, and upgrading the existing server is not approved. |
| DEC-101 | No React, Next.js, separate Node.js backend, microservices, Kubernetes, Redis or similar infrastructure without a justified proposal and owner approval. |
| DEC-102 | The existing MySQL Server 8.0.44 installation must be preserved. The other academic project's databases, `db_final_group_project_working` and `db_final_group_project`, must never be modified or deleted. |
| DEC-290 | The project uses its own database, `uol_student_affairs` (utf8mb4), with an application database user whose privileges are limited to that database. |
| DEC-103 | Secrets (passwords, API keys, OAuth client secrets, the Django secret key, `.env` contents) are never committed and never written into documentation. |
| DEC-291 | Django settings load secrets from `.env` using python-dotenv. `.env.example` contains placeholders only. |

### 1.12 Process and design

| ID | Decision |
|---|---|
| DEC-110 | Git workflow: `main` stays stable and tested, feature branches for substantial features, logical conventional commits, review before commit, no artificial commits. |
| DEC-111 | Development cycle: Understand → Research → Design → Discuss → Approve → Document → Implement → Test → Review. |
| DEC-120 | Design is a core product concern: mobile-first, responsive, consistent components, clear hierarchy, accessible, connected to UOL's visual identity. No generic dashboard templates, excessive gradients or unnecessary animation. |

### 1.13 Design system and key pages

Confirmed by the owner on 2026-11-16. Details in `docs/design/DESIGN_PLAN.md`, the written specification of Design D (the design-phase HTML prototypes were not kept in the repository).

| ID | Decision |
|---|---|
| DEC-300 | Design philosophy: "Confident type. Quiet colour. Meaningful information." Seven principles: type carries the hierarchy; say it before you show it; quiet colour, loud meaning; every case shows where it is; the cohort is the unit; staff get workspaces, not dashboards; private by default, calm in tone. |
| DEC-301 | The Forest palette (Forest Light and Forest Dark) is approved; its values and the four semantic status colours are fixed. Active navigation uses an ink indicator and font weight, not the Forest tint, so it is never confused with the Resolved badge. |
| DEC-302 | Design D is the approved visual reference for production: the Student Dashboard (premium welcome), the Batch Advisor Complaints workspace (split pane with a focused case) and the Super Admin Overview (cohort map with a written briefing). |
| DEC-303 | Student Dashboard: the personal summary is calculated from the student's own records only, never generated by AI ("Nothing needs your attention today." for none; one update described directly; several led by the most important/recent with a count of the others) and never invents urgency. The DEC-282 "Your Actions" section is shown as "Your latest updates". A complaint journey card appears only for relevant new activity and stays while relevant, with seen and unseen updates distinguished. Collective section issues are not part of the personal summary. Support wording: "Support this issue", then "You support this", with "Support can't be withdrawn" shown before the action. Representatives are shown by name and role only. |
| DEC-304 | Student phone navigation has four destinations (Home, Complaints, Student Voice, Meetings) and no "More"; notifications and the account menu are in the header. |
| DEC-305 | Batch Advisor Complaints: Respond and Update status are separate actions, and sending a response never changes a complaint's status. "Other complaints from this student" is not shown in V1. |
| DEC-306 | The Super Admin Overview carries the three DEC-281 analytics with written takeaways; there is no separate Statistics destination for the Super Admin. Cohort map cells are exact batch + semester + section cohorts in academic order, and a section with zero complaints is shown differently from a section that does not exist. |
| DEC-307 | Laptop acceptance target: HP EliteBook 840 G8 (1920×1080 at 150% Windows scaling) in Opera at 100% zoom, a viewport of about 1280×590. Every page must also work at 360px wide. Both are checked throughout implementation. |
| DEC-308 | Meetings: an in-app calendar with month, week and day views, with visibility per DEC-246, DEC-260, DEC-261 and DEC-262. Confirmed meetings offer "Add to Google Calendar" as a prefilled event link (title, date, start and end time, description); no Google Calendar API, extra OAuth scopes or new sign-in flow. The portal remains the source of truth, and adding to Google Calendar never changes a meeting's status. This is a link, not the integration excluded by DEC-061. |

---

## 2. OUT OF SCOPE by decision

| ID | Item |
|---|---|
| DEC-231 | How a complaint about a student's own Batch Advisor is handled. This edge case has deliberately been left outside current requirements and is not to be reopened. |
| DEC-230 | Special routing for complaints against administrators or the Super Admin (see 1.4). |

---

## 3. SUPERSEDED decisions

| ID | Old decision | Replaced by |
|---|---|---|
| SUP-01 | Students verify their UOL email using an OTP. | DEC-010 |
| SUP-02 | Withdrawn from this list. The original decision, that SAP ID is not used to assign a student's section automatically, still holds: section is declared at registration (DEC-201). What changed is that the SAP ID is now extracted from the email (DEC-011). | — |
| SUP-03 | Students can submit complaints anonymously, accessed by reference number and secret access code, not linked to student accounts. | DEC-030, DEC-031 |
| SUP-04 | Advisor accounts are approved by the Super Admin after an advisor requests one. | DEC-013 |
| SUP-05 | The Super Admin assigns sections to advisors. | DEC-013, DEC-204 (semesters and sections) |
| SUP-06 | The Super Admin role is not tied to a specific position. | DEC-014 |
| SUP-07 | One active CR per section, responsibilities undefined. | DEC-016, DEC-040, DEC-240 |
| SUP-08 | Attachments undecided. | DEC-080 |
| SUP-09 | Further advisor research is required before requirements are finalised. | DEC-005 |
| SUP-10 | The role name "Academic Advisor". | "Batch Advisor (BA)" |
| SUP-11 | FastAPI backend (from the earlier Student Voice Portal concept). | DEC-100 |
| SUP-12 | Suggestions and Appreciation are separate submission types, each with a simple status workflow. | DEC-250 |
| SUP-13 | Students declare their name, department, batch and section. | DEC-201 (full name, batch, semester and section; department defaults) |
| SUP-14 | Complaints concerning the Administrator or HOD are directed to the appropriate official university channel. | DEC-230 |
| SUP-15 | The advisor dashboard has three priority queues under "Needs Attention". | DEC-226, DEC-283 |
| SUP-16 | A 15-day overdue indicator (from the earlier Student Voice Portal concept). | DEC-226 |

---

## 4. Resolution of previously open items

Kept for traceability. These items appeared as NEEDS CONFIRMATION (Q) or OPEN (O) in the first reconciliation.

| Old ID | Question | Outcome |
|---|---|---|
| Q1 | Does Student Voice replace Suggestions and Appreciation? | Yes. DEC-250 |
| Q2 | What do students declare at registration? | DEC-201, DEC-011 |
| Q3 | Rule on complaints about the Administrator or HOD | Out of scope for V1. DEC-230 |
| Q4 | Multiple advisors per section | Yes. DEC-204, DEC-227 |
| Q5 | Three priority queues | Not included. DEC-226 |
| Q6 | 15-day overdue indicator | Not included. DEC-226 |
| O1 | Sign-in for BAs and the Super Admin; first Super Admin | DEC-010, DEC-200, DEC-013, DEC-203. The bootstrap mechanism itself remains open as O26. |
| O2 | Domain enforcement | Still open (technical). See section 5. |
| O3 | OAuth implementation | Library chosen: `django-allauth` is approved. The rest is still open (technical). See section 5. |
| O4 | How students change semester or section | DEC-021 |
| O5 | CR/GR lifecycle and the meaning of GR | DEC-016, DEC-240, DEC-245 |
| O6 | Collective issue visibility and support | DEC-241, DEC-243 |
| O7 | Student Voice visibility and answers | DEC-051, DEC-252, DEC-253, DEC-254 |
| O8 | The "did not solve" mechanism | DEC-222, DEC-223 |
| O9 | Complaint ownership with several advisors | DEC-227, DEC-228, DEC-310. Complaint owner designation is settled; BA routing for collective issues, Student Voice and meetings remains open. |
| O10 | Complaints about a student's own BA | Out of scope. DEC-231 |
| O11 | Calendar scope | DEC-061, DEC-261 |
| O12 | Complaint categories and statuses | DEC-220, DEC-221 |
| O13 | Statuses for collective issues and Student Voice | Collective issues: DEC-244. No status workflow has been specified for Student Voice. |
| O14 | Meeting rules | DEC-060, DEC-260. Remaining details are open as O29. |
| O15 | Notification events | DEC-270 |
| O16 | Analytics | DEC-090, DEC-280, DEC-281, DEC-313 to DEC-322. Small-cohort privacy, classification and reporting window are settled. |
| O17 | Role and permission matrix | Settled at the product level by DEC-015, DEC-228, DEC-229, DEC-240, DEC-245, DEC-246, DEC-253, DEC-261 and DEC-262. |
| O24 | What the early prototype was | Not a blocker. A minor gap in the historical record only. |

---

## 5. OPEN items

Product workflows are settled by section 1. What remains falls into two groups.

### 5.1 Technical implementation choices

These do not change what the product does. They are resolved during design and implementation, with the owner's approval where a new dependency or risk is involved.

| ID | Open item |
|---|---|
| O2 | Technical verification and domain enforcement for students and staff: how the email format is enforced, how staff accounts are verified, and confirmation that the relevant UOL accounts work with Google sign-in. |
| O3 | Google OAuth implementation beyond the approved library (`django-allauth`): OAuth client setup and secure handling of the client credentials. Real sign-in with UOL accounts is not yet configured or verified (see also O2). |
| O26 | The exact bootstrap mechanism for the initial Super Admin account (DEC-203). |
| O20 | Final Django app structure and database schema. |
| O18 | Final design system, official UOL brand assets and validated visual references. Partly settled by DEC-300 to DEC-302; official UOL brand assets remain open. |
| O30 | Final production typography. Newsreader (display) + Inter (interface) is the preferred direction. |
| O34 | Theme switch: Light and Dark only, or also a System option that follows the device. |
| O22 | Detailed threat model and security testing plan. |
| O21 | Deployment, hosting, backups and recovery. |
| O19 | Whether and how to move to MySQL 8.4 in future, without touching the existing 8.0.44 installation (DEC-102). |
| O23 | Project licence. |
| O25 | Resolved by DEC-315. |

### 5.2 Workflow details not covered by the confirmed decisions

These are gaps found while reconciling, not reopened decisions. Each needs a short answer from the owner before the related feature is built.

| ID | Open item |
|---|---|
| O27 | Complaint owner designation is resolved by DEC-310. Which BA is relevant/assigned for collective issues, Student Voice and meeting requests remains open for those modules. |
| O28 | Resolved by DEC-311: cancellation requests are record-only, with no status change or approval/decline workflow. |
| O29 | Meeting status names, and whether a student can cancel or ask to reschedule a meeting that has been confirmed. |
| O31 | Resolved by DEC-313. |
| O32 | Resolved by DEC-314. |
| O33 | Resolved by DEC-312: no response-required classification or "Waiting for you" queue is added. |
| O35 | Collective issues: may a CR or GR post be vacant, given DEC-016's "exactly one"? Recommended: yes; the database enforces at most one per post. Details: `docs/technical/COLLECTIVE_ISSUES_SPEC.md` section 12. |
| O36 | Collective issues: what closes an issue for support and removes it from home pages (DEC-243 "after the advisor responds")? Recommended: the first official response or resolution note; Under Review alone does not. Details: `docs/technical/COLLECTIVE_ISSUES_SPEC.md` section 12. |
| O37 | Collective issues: do the current CR and GR see all of their cohort's issues and private responses, including a predecessor's, and does a former representative keep access? Recommended: current representatives see all; access follows the current assignment. Details: `docs/technical/COLLECTIVE_ISSUES_SPEC.md` section 12. |
| O38 | Collective issues: can students support an issue after it is closed for support? Recommended: no; the count is then frozen. Details: `docs/technical/COLLECTIVE_ISSUES_SPEC.md` section 12. |
| O39 | Collective issues: do non-representative students see the issue's status? Recommended: no; only "Open for support" or "Support closed". Details: `docs/technical/COLLECTIVE_ISSUES_SPEC.md` section 12. |
| O40 | Collective issues: who may see which students supported an issue? Recommended: nobody in the interface; counts only. Details: `docs/technical/COLLECTIVE_ISSUES_SPEC.md` section 12. |
| O41 | Collective issues: drafts or immediate publication? Recommended: no stored drafts; a review step with a required confirmation that the issue will be locked. Details: `docs/technical/COLLECTIVE_ISSUES_SPEC.md` section 12. |
| O42 | Collective issues: categories? Recommended: none in V1. Details: `docs/technical/COLLECTIVE_ISSUES_SPEC.md` section 12. |
| O43 | Collective issues: duplicate handling? Recommended: a non-blocking notice listing the cohort's open issues. Details: `docs/technical/COLLECTIVE_ISSUES_SPEC.md` section 12. |
| O44 | Collective issues: may the Super Admin respond or change status, or is oversight (DEC-247) read-only? Recommended: read-only in V1. Details: `docs/technical/COLLECTIVE_ISSUES_SPEC.md` section 12. |
| O45 | Collective issues: new assignments or issues for a cohort that includes an inactive batch, semester or section? Recommended: no; existing records stay readable. Details: `docs/technical/COLLECTIVE_ISSUES_SPEC.md` section 12. |
| O46 | Collective issues: where representatives raise issues and read private responses, given DEC-304's four phone destinations? Recommended: inside Home and the section issues pages reached from it. Details: `docs/technical/COLLECTIVE_ISSUES_SPEC.md` section 12. |
| O47 | Collective issues: reference format? Recommended: CI-<year>-<5 digits>. Details: `docs/technical/COLLECTIVE_ISSUES_SPEC.md` section 12. |
| O48 | Collective issues: a limit on how many issues a representative may raise? Recommended: none in V1. Details: `docs/technical/COLLECTIVE_ISSUES_SPEC.md` section 12. |
| O49 | Collective issues: reopening a Resolved issue, or a Rejected status? Recommended: neither in V1. Details: `docs/technical/COLLECTIVE_ISSUES_SPEC.md` section 12. |
| O50 | Collective issues: moderation of abusive or wrong content, given that nobody can edit or delete? Recommended: none in V1, recorded as a risk. Details: `docs/technical/COLLECTIVE_ISSUES_SPEC.md` section 12. |
| O51 | Collective issues: notify the current CR/GR when a BA responds or resolves (not in DEC-270's list)? Recommended: yes, if approved. Details: `docs/technical/COLLECTIVE_ISSUES_SPEC.md` section 12. |
| O52 | "GR": the Collective Issues brief says "General Representative"; DEC-016 says Girls Representative. Recommended: keep DEC-016 unless the owner changes it. Details: `docs/technical/COLLECTIVE_ISSUES_SPEC.md` section 12. |
