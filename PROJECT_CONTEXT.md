# UOL Student Affairs — Project Context

**Purpose:** A compact working context for every collaborator (the owner, Claude, Claude Code, ChatGPT).
**Last reconciled:** 2026-11-18 (status and resolved open items only)
**Canonical location:** This file in the GitHub repository.

Related documents:

- `MASTER_PROJECT_BRIEF.md`: the complete product and engineering brief.
- `DECISIONS.md`: the authoritative decision register. If this file and `DECISIONS.md` disagree, `DECISIONS.md` wins.
- `DEVELOPMENT_LOG.md`: what happened and when.

## 1. Project overview

| | |
|---|---|
| Name | UOL Student Affairs |
| Subtitle | Student Affairs & Engagement Portal |
| Institution | The University of Lahore (UOL) |
| Initial target | Software Engineering Department |
| Project type | Individual BS Software Engineering fourth-semester project |
| Repository | https://github.com/azeemworks925-eng/uol-student-affairs |
| Phase | Requirements confirmed for V1 workflows. Incremental implementation in progress; see the "Status at a glance" table in `DEVELOPMENT_LOG.md`. |

This is an independently developed academic project with the ambition of becoming suitable for a departmental pilot. It is not an officially commissioned, approved or deployed university system.

## 2. Current status

| Area | Status |
|---|---|
| Django foundation | Created and tested locally (details below). |
| Product features | Authentication, the application shell, complaints (Parts 1–4 Stage 4a) and in-app notifications are merged into `main`. Stage 4b analytics are specified (DEC-316 to DEC-322), not implemented. Collective issues, Student Voice and meetings are not implemented. |
| Authoritative status | The dated "Status at a glance" table in `DEVELOPMENT_LOG.md`. |

Foundation work performed locally:

- Python 3.13.15 and Django 5.2.19 on Windows 11.
- Database `uol_student_affairs` created with utf8mb4 on the existing MySQL Server 8.0.44.
- Application database user with privileges limited to the project database.
- Django project structure created with `manage.py` and `config`.
- Custom `accounts.User` model created; initial accounts migration generated and applied.
- Settings load secrets from `.env` using python-dotenv; `.env.example` holds placeholders.
- Django system check passed; database connection and migrations verified.

## 3. Roles

| Role | Summary |
|---|---|
| Student | Signs in with Google, self-registers, active immediately. Sees only their own complaints, Student Voice submissions and meetings. |
| CR and GR | Exactly one of each per section. GR means Girls Representative. Existing student accounts with identical additional permissions. Raise collective issues for their own section. |
| Batch Advisor (BA) | Account created by the Super Admin. Access only to explicitly assigned sections. Handles complaints, collective issues, Student Voice and meetings for those sections. Can assign and replace their sections' CR and GR. |
| Super Admin | The Head of Batch Advisors. Department-wide oversight. Manages BAs, students, CR/GR assignments, academic structure and complaint categories. |

## 4. Confirmed decisions (summary)

IDs refer to `DECISIONS.md`, which has the full wording.

### Authentication and accounts

- Google OAuth with one shared login page for all roles and no role selector. Django matches the Google identity to a user record and directs the user to the correct dashboard. (DEC-010, DEC-200)
- Student email: eight-digit SAP ID followed by `@student.uol.edu.pk`. SAP ID is extracted from the verified email. (DEC-011)
- Registration collects full name, batch, semester and section. Department defaults to Software Engineering. No Morning/Evening field. (DEC-201)
- Students are active immediately, with no individual approval. (DEC-012)
- Students cannot request profile corrections; the Super Admin corrects student information. (DEC-202)
- The initial Super Admin is configured through a secure bootstrap process. (DEC-203)
- The Super Admin creates BA accounts from the teacher's name and official UOL email, then assigns semesters and sections. No BA self-registration. (DEC-013)
- BA assignments are explicit and changeable; several BAs can share a section; the existing BA structure is not hardcoded. (DEC-204, DEC-015)

### Academic structure and student records

- Batches, semesters and sections are database-managed; the Super Admin adds, edits and deactivates them. Deactivation preserves students and history. (DEC-020, DEC-210)
- No automatic semester promotion; the Super Admin updates semester and section manually. (DEC-021)
- Student profile changes are audited. (DEC-211)
- Student deactivation is a soft delete that preserves history and revokes representative permissions. (DEC-212)

### Complaints

- Identified and linked to student accounts. No anonymous complaints. (DEC-030)
- Unique reference ID; authenticated My Submissions with status history and advisor responses. (DEC-031)
- Initial main categories: Academic, Non-academic, Personal/Wellbeing, Other. Categories and subcategories are managed by the Super Admin. (DEC-220)
- Statuses: Received, Under Review, Resolved, Rejected. Rejection reason mandatory and visible to the student. Resolution note mandatory. (DEC-221)
- "Still not resolved" returns a resolved complaint to Under Review. (DEC-222)
- Students can add further information; the original description and history are kept. (DEC-223)
- Students can request cancellation but cannot delete. (DEC-224)
- Duplicate warning allowed; duplicates not blocked. (DEC-225)
- No priority levels, priority queues or overdue indicator. (DEC-226)
- Routed by section assignment. All assigned BAs see the section's complaints; one designated BA owns each complaint. (DEC-227)
- The Super Admin can open, review, reassign, take over and respond to any complaint. (DEC-228)
- Students see only their own complaints; BAs only their assigned sections. (DEC-229)

### CR/GR collective issues

- Either representative can raise an issue for their own section. (DEC-040)
- The issue appears on the home page of students in that section. One support per student, which cannot be withdrawn or changed. CR/GR can support their own issue. No comments. (DEC-241)
- Published issues cannot be edited or deleted by CR/GR. (DEC-242)
- The BA responds privately to CR/GR. After the response, the issue leaves student home pages; CR/GR keep it and the response in their dashboard; the record and support count are preserved. (DEC-243)
- Statuses: Received, Under Review, Resolved. Resolution note mandatory and private to CR/GR. (DEC-244)
- BAs assign and replace CR/GR for their sections; the Super Admin can also do so. One representative assignment per student. (DEC-245, DEC-240)
- CR/GR cannot see individual complaints, private Student Voice submissions or other students' meetings. (DEC-246)

### Student Voice

- Exactly three types: Ideas, Questions, Feedback. Replaces Suggestions and Appreciation. (DEC-050, DEC-250)
- Typed text, no tracking ID. (DEC-251)
- Ideas and Feedback are reviewed by the relevant BA; a response is not mandatory. (DEC-252)
- A Question receives one official BA answer, shown beside the question. (DEC-051)
- No chat or follow-up messaging. (DEC-052)
- Private to the student, the relevant BA and the Super Admin. (DEC-253)
- No dedicated Student Voice section on the Super Admin dashboard. (DEC-254)

### Meetings

- A student requests a meeting with their assigned BA, giving a reason and preferred availability. The BA accepts, suggests another time, or declines with a reason. (DEC-060)
- A BA can invite students, and can schedule, reschedule and cancel meetings involving assigned students. (DEC-260)
- The BA calendar has month, week and day views. It is internal to the portal, with no Google Calendar integration. (DEC-061)
- Students see only their own meetings: date, time, location, status. (DEC-261)
- The Super Admin has department-wide meeting oversight. No chat. (DEC-262, DEC-263)

### Notifications

- In-app only. No email in V1. (DEC-070)
- Events: complaint status changes and advisor responses; official answers to questions; meeting confirmation, rescheduling and cancellation; new CR/GR issues in the student's section. Each links to its record. (DEC-270)

### Analytics and dashboards

- BAs see statistics for assigned sections; the Super Admin sees department-wide statistics. (DEC-280)
- Complaint categories and percentages, section-wise distribution, resolved versus unresolved. No student names in aggregate charts. No decorative charts. (DEC-281, DEC-090)
- Student dashboard: Your Actions, Section Updates, Quick Access. (DEC-282)
- BA dashboard: overview, complaint inbox, search and filters, complaint details, CR/GR issues, meeting calendar, section statistics. Section filter defaults to All Assigned Sections. (DEC-283)
- Super Admin dashboard: overview, students, Batch Advisors, CR/GR management, configuration, calendar, department-wide oversight. (DEC-284)

### Not in V1

- Anonymous complaints and secret access codes.
- Attachments.
- A public social feed, student comments, chat or follow-up messaging.
- Email or other external notifications.
- General university or department announcements.
- Complaint priority levels, priority queues and overdue indicators.
- Automatic semester promotion.
- Google Calendar integration.
- A separate department-admin, Administrator or HOD portal.
- Special routing for complaints against administrators or the Super Admin.
- Handling of complaints about a student's own BA (deliberately outside current requirements; do not reopen).

## 5. Open items

Product workflows are settled. Do not assume answers to the following; full wording is in `DECISIONS.md`, section 5.

**Technical implementation choices**

- O2: Domain enforcement and verification for students and staff.
- O3: Google OAuth client setup and credential handling. The library choice is settled: `django-allauth` is approved; real sign-in with UOL accounts is not yet configured or verified.
- O26: Bootstrap mechanism for the initial Super Admin.
- O20: Django app structure and database schema.
- O18: Design system, official UOL brand assets, visual references.
- O22: Threat model and security testing plan.
- O21: Deployment, hosting, backups and recovery.
- O19: Future MySQL 8.4 evaluation.
- O23: Project licence.

**Workflow details needing a short answer from the owner**

- O27: Which BA is relevant for collective issues, Student Voice and meeting requests (resolved for complaints by DEC-310).
- O29: Meeting status names, and whether a student can cancel or ask to reschedule a confirmed meeting.

## 6. Technology stack

- Python 3.13 (3.13.15 installed)
- Django 5.2 LTS (5.2.19 installed)
- MySQL: development on the existing MySQL Server 8.0.44. MySQL 8.4 LTS is a future evaluation question; it is not installed and no upgrade is approved.
- python-dotenv for loading settings from `.env`
- Google OAuth for authentication, through the approved `django-allauth` library. Real Google sign-in is not yet configured or verified with UOL accounts (O2, O3).
- Django Templates
- HTML, CSS and vanilla JavaScript
- Bootstrap 5.3
- HTMX only where genuinely useful
- Django testing framework and pytest
- Git and GitHub
- Visual Studio Code and MySQL Workbench
- Claude Code for AI-assisted implementation

Do not introduce React, Next.js, a separate Node.js backend, microservices, Kubernetes, Redis or other infrastructure without a justified proposal and the owner's approval. Any other new library also needs approval; the Google OAuth library, `django-allauth`, is already approved.

## 7. Environment constraints

- Development environment: Windows 11.
- The existing MySQL Server 8.0.44 installation must be preserved. Do not upgrade, uninstall, reset or reconfigure it without explicit approval and verified backups.
- The databases `db_final_group_project_working` and `db_final_group_project` belong to another academic project and must never be modified or deleted.
- This project uses only the `uol_student_affairs` database, through an application user limited to that database.
- Never commit or document passwords, API keys, OAuth client secrets, the Django secret key or `.env` contents.

## 8. Development principles

- Follow the cycle: Understand → Research → Design → Discuss → Approve → Document → Implement → Test → Review.
- Build incrementally. Implement a feature only when its requirements are confirmed in `DECISIONS.md`.
- Open technical items are resolved when the work reaches them. They do not block unrelated features.
- Keep the architecture understandable and maintainable.
- Follow Django security and permission best practices. Validate input on the server.
- Write tests for important workflows.
- Explain significant implementation decisions to the owner.
- Do not introduce features that have not been approved.
- Do not claim something works until it has been tested.

## 9. Git workflow

- `main` contains stable, tested work.
- Use feature branches for substantial features.
- Make logical commits with conventional messages (`docs:`, `feat:`, `fix:`, `test:`, `security:`, `refactor:`).
- Review the diff before committing. Test before merging into `main`.
- Push meaningful, verified work during every working session. No artificial commits.
- Never commit secrets.

## 10. Keeping context synchronised

1. The GitHub repository is canonical (DEC-004).
2. Context documents are changed in the repository first, through a reviewed commit.
3. After a commit, the exact committed versions are copied to the Claude Project knowledge and shared with ChatGPT.
4. No collaborator treats an uncommitted draft as current context.

---

**Instruction for AI coding agents:** This document is context, not permission to make product decisions. The project owner is the only person who can approve a product decision. Ask before changing a confirmed decision or resolving an open item. Update this file and `DECISIONS.md` only when the owner has approved the change.
