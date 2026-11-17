# UOL Student Affairs
## Master Project Brief

**Product name:** UOL Student Affairs
**Product subtitle:** Student Affairs & Engagement Portal
**Institution:** The University of Lahore (UOL)
**Initial target:** Software Engineering Department
**Project type:** Individual BS Software Engineering fourth-semester academic project
**Repository:** https://github.com/azeemworks925-eng/uol-student-affairs
**Current phase:** V1 product workflows confirmed. Incremental implementation in progress: authentication, the application shell, complaints (Parts 1–4 Stage 4a) and in-app notifications are merged into `main`; Stage 4b analytics are specified, not implemented. See section 13.
**Document status:** Reconciled on 2026-11-16; status, analytics decisions and resolved open items updated on 2026-11-18. Living document.

This is the complete product and engineering brief. The authoritative list of decisions is `DECISIONS.md`; if the two disagree, `DECISIONS.md` wins. IDs in brackets (DEC, O) refer to that file.

---

# 1. Executive Summary

UOL Student Affairs is a proposed Student Affairs & Engagement Portal intended to improve communication, student engagement, feedback handling, advisor coordination and student affairs workflows at The University of Lahore.

The initial target is the Software Engineering Department, with the possibility of a departmental pilot if the product reaches an appropriate standard and the relevant stakeholders support it.

The platform is broader than a complaint submission website. Version 1 gives students four connected workflows:

- **Complaints:** identified, tracked and answered by a responsible Batch Advisor.
- **Collective issues:** raised by a section's class representatives and supported by its students.
- **Student Voice:** Ideas, Questions and Feedback.
- **Meetings:** requested, confirmed and managed through an internal calendar.

The project is an individual fourth-semester BS Software Engineering academic project. The ambition goes beyond meeting course requirements: we want something useful, secure, maintainable and polished enough to demonstrate to university stakeholders.

**Important distinction:** This is an independently developed academic project. It is not an officially commissioned, approved or deployed university system. (DEC-001)

# 2. Project Origin

The project originated as an individual academic project for the Data Structures and Algorithms (DSA) course during the fourth semester of the BS Software Engineering programme at UOL.

The initial concept focused on giving students a better way to communicate feedback and concerns to their advisors. As the idea developed, the opportunity proved broader than complaint management alone, which led to the current direction:

**UOL Student Affairs — Student Affairs & Engagement Portal.**

We approach it as a real software engineering project: requirements engineering, product design, architecture, implementation, testing, documentation and potential deployment.

# 3. Stakeholder Input

## 3.1 What has been recorded

The project concept and an initial prototype were presented to a batch advisor from the Software Engineering Department. The advisor:

- Liked the concept and its potential usefulness.
- Encouraged further research with advisors.
- Expressed willingness to help with departmental deployment if the platform is developed well.
- Expressed interest in useful, actionable aggregate statistics, not decorative dashboards.

The discussion also highlighted that students currently raise concerns through informal communication channels.

This feedback is encouraging. It is not formal university approval and not a deployment commitment.

## 3.2 Current position on research

No further stakeholder interviews or surveys are planned at this stage. (DEC-005)

The points in 3.1 come from a single conversation. They are observations, not validated research findings. Never invent stakeholder feedback.

# 4. Product Vision

Our vision is a centralised, student-focused engagement platform that makes communication between students and their department more structured, accessible and manageable.

The product should feel like one cohesive platform, not several unrelated forms inside a dashboard.

## 4.1 Product principles

- Student-centred.
- Easy to understand.
- Privacy-conscious.
- Responsive across devices.
- Professionally designed.
- Secure by default.
- Maintainable and extensible.

We prioritise usability over feature count.

# 5. Users and Roles

## 5.1 Students

- Sign in with Google and self-register. (DEC-010, DEC-012)
- Become active immediately, with no individual Super Admin approval. (DEC-012)
- See only their own complaints, Student Voice submissions and meetings. (DEC-229, DEC-253, DEC-261)
- Cannot submit profile correction requests. (DEC-202)

## 5.2 Class Representatives: CR and GR

- Every section has exactly one CR and one GR. GR means Girls Representative. (DEC-016)
- They are existing student accounts with additional permissions, not separate account types or login systems. (DEC-016)
- CR and GR have identical permissions and responsibilities and keep their normal student permissions. (DEC-240)
- A student can hold only one representative assignment, for one section. (DEC-240)
- They cannot see individual complaints, private Student Voice submissions or other students' meeting details. (DEC-246)

## 5.3 Batch Advisors (BA)

- Accounts are created by the Super Admin. There is no self-registration or application process. (DEC-013)
- Access is determined by explicit assignments. A BA sees only assigned sections. (DEC-015)
- A BA can have multiple sections and semesters. Sections can be split among BAs, and several BAs can be assigned to one section. Assignments can change, and the existing BA structure is not hardcoded. (DEC-204)
- BAs can assign and replace the CR and GR of their assigned sections. (DEC-245)

## 5.4 Super Admin

- The Super Admin is the Head of Batch Advisors and has department-wide oversight. (DEC-014)
- Creates BA accounts and assigns their semesters and sections. (DEC-013)
- Manages the academic structure and complaint categories. (DEC-020, DEC-220)
- Corrects student information and updates students' semester and section. (DEC-202, DEC-021)
- Can manage CR/GR assignments. (DEC-245)
- The initial Super Admin account is configured securely through a bootstrap process. (DEC-203)

There is no separate department-admin, Administrator or HOD portal in V1. (DEC-082)

# 6. Version 1 Workflows

## 6.1 Authentication and registration

- Authentication is Google OAuth. All roles use one shared Google login page. (DEC-010)
- There is no role selector. Django checks the authenticated Google identity against the user records in MySQL and directs the user to the correct dashboard. (DEC-200)
- Student emails follow the exact format of an eight-digit SAP ID followed by `@student.uol.edu.pk`. The SAP ID is extracted from the verified email. (DEC-011)
- Student registration collects full name, batch, semester and section. Department defaults to Software Engineering. There is no Morning/Evening field. (DEC-201)
- The Super Admin creates each BA account by entering the teacher's name and official UOL email. BAs then use the same Google login page. (DEC-013)

Open technical items: domain enforcement and verification (O2), OAuth library and credentials (O3), bootstrap mechanism (O26).

## 6.2 Academic structure and student records

- Batches, semesters and sections are database-managed. The Super Admin can add, edit and deactivate entries. (DEC-020)
- Deactivating an entry preserves its associated students and historical records. (DEC-210)
- There is no automatic semester promotion. The Super Admin manually updates students' semester and section. (DEC-021)
- Student profile changes are audited. (DEC-211)
- Deactivating a student is a soft delete. It preserves historical records and revokes representative permissions. (DEC-212)

## 6.3 Complaints

**Submission**

- Complaints are identified and linked to student accounts. There are no anonymous complaints or secret access codes. (DEC-030)
- The main categories initially include Academic, Non-academic, Personal/Wellbeing and Other. Categories and subcategories are managed by the Super Admin. (DEC-220)
- A duplicate warning may be shown, but duplicate submissions are not blocked. (DEC-225)
- Each complaint receives a unique reference ID. (DEC-031)

**Tracking**

- Students follow their complaints in an authenticated My Submissions view, with status history and advisor responses. (DEC-031)
- Statuses are Received, Under Review, Resolved and Rejected. (DEC-221)
- A rejection reason is mandatory and visible to the student. A resolution note is mandatory. (DEC-221)
- After resolution, the student can indicate "Still not resolved", which returns the complaint to Under Review. (DEC-222)
- Students can add further information without losing the original description or history. (DEC-223)
- Students can request cancellation but cannot delete a complaint. (DEC-224)

**Handling**

- Complaints are routed to BAs based on section assignments. (DEC-227)
- All BAs assigned to a section can see its complaints. One designated BA is the responsible owner of each complaint. (DEC-227)
- The Super Admin can open, review, reassign, take over and respond to any complaint. (DEC-228)
- There are no priority levels, priority queues or overdue indicators. (DEC-226)

**Boundaries**

- There is no special routing hierarchy for complaints against administrators or the Super Admin in V1. (DEC-230)
- Handling of a complaint about a student's own BA is deliberately outside current requirements. (DEC-231)

Resolved workflow details: a Super Admin designates the responsible owner manually (DEC-310); a cancellation request is recorded only (DEC-311); there is no response-required queue (DEC-312).

## 6.4 CR/GR collective issues

**Raising and supporting**

- Either representative can independently raise a collective issue for their own section. (DEC-040)
- The issue appears on the home page of students in that section. (DEC-241)
- A student can support an issue once. Support cannot be withdrawn or changed. CR/GR can support their own issue. (DEC-241)
- There are no student comments. (DEC-241)
- Published issues cannot be edited or deleted by CR/GR in V1. (DEC-242)

**Advisor response**

- The BA receives the issue, can update its status, and provides a short official response. (DEC-243, DEC-244)
- The response is private to CR/GR. Other students cannot see it. (DEC-243)
- Statuses are Received, Under Review and Resolved. A resolution note is mandatory and private to CR/GR. (DEC-244)
- After the advisor responds, the issue disappears from student home pages. CR/GR keep the issue and the private response in their dashboard. The underlying record and support count are preserved. (DEC-243)
- The Super Admin has department-wide oversight. (DEC-247)

**Representative assignments**

- BAs can assign and replace CR/GR for their assigned sections. The Super Admin can also manage assignments. (DEC-245)

## 6.5 Student Voice

- Exactly three types: Ideas, Questions and Feedback. (DEC-050)
- Student Voice replaces the previous Suggestions and Appreciation submission types. (DEC-250)
- Submissions are typed text, with no tracking ID. (DEC-251)
- Ideas and Feedback are reviewed by the relevant BA. An individual response is not mandatory. (DEC-252)
- A Question receives one official BA answer, visible beside the question. (DEC-051)
- There is no chat or follow-up messaging. (DEC-052)
- Submissions are private to the submitting student, the relevant BA and the Super Admin. Other students and CR/GR cannot see them. (DEC-253)
- The Super Admin has oversight of all submissions, handled through the relevant BA workflow. There is no dedicated Student Voice section on the Super Admin dashboard. (DEC-254)

## 6.6 Meetings

- A student can request a meeting with their assigned BA, giving a reason and preferred availability. (DEC-060)
- The BA can accept/confirm, suggest another time, or decline with a reason. (DEC-060)
- A BA can also invite students. (DEC-260)
- A BA can view and manage meetings involving assigned students, and can schedule, reschedule and cancel them. (DEC-260)
- The BA calendar has month, week and day views. (DEC-061)
- It is an internal portal calendar, not a Google Calendar integration. (DEC-061)
- Students see only their own meetings: date, time, location and status. (DEC-261)
- CR/GR cannot see other students' meeting details. (DEC-246)
- The Super Admin has department-wide meeting oversight. (DEC-262)
- There is no chat. (DEC-263)

Open workflow detail: meeting status names, and whether a student can cancel or ask to reschedule a confirmed meeting (O29).

## 6.7 Notifications

- In-app notifications only. No email notifications in V1. (DEC-070)
- Events include:
  - Complaint status changes and advisor responses.
  - Official answers to Student Voice questions.
  - Meeting confirmation, rescheduling and cancellation.
  - New CR/GR issues in the student's section.
- Each notification links to the relevant record. (DEC-270)

## 6.8 Dashboards

**Student dashboard** (DEC-282)

1. Your Actions: pending complaint updates, unanswered questions, meeting requests.
2. Section Updates: active CR/GR issues awaiting student support.
3. Quick Access: Submit Complaint, Student Voice and My Meetings.

There are no general university or department announcements in V1. (DEC-083)

**BA dashboard** (DEC-283)

- Compact overview.
- Actionable complaint inbox with search and filters.
- Complaint details.
- CR/GR issues.
- Meeting calendar.
- Useful section statistics.
- The section filter defaults to All Assigned Sections.

**Super Admin dashboard** (DEC-284)

- Overview.
- Students.
- Batch Advisors.
- CR/GR management.
- Configuration.
- Calendar.
- Department-wide oversight.

## 6.9 Analytics

- BAs see statistics for their assigned sections. The Super Admin sees department-wide statistics. (DEC-280)
- Useful analytics include complaint categories and percentages, section-wise complaint distribution, and resolved versus unresolved complaints. (DEC-281)
- No individual student names appear in aggregate charts, and aggregate reporting must not expose individual identities. (DEC-090)
- No meaningless decorative charts. (DEC-090)

- Resolved means status Resolved; not resolved means Received, Under Review and Rejected, with rejected complaints identified separately. (DEC-313)
- The Super Admin analytics use the current academic term's window, by submission date, with a setup state when no term is current. (DEC-314, DEC-316)
- Cohorts with fewer than five active students are suppressed, with complementary suppression, and all figures are withheld when suppression cannot be made safe. (DEC-315, DEC-317 to DEC-319)
- This protects the analytics output only; the Super Admin's authorised access to individual complaints is unchanged, so the analytics are not described as anonymous, and a privacy review is required before any pilot use. (DEC-320, DEC-322)
- Full Stage 4b specification: `docs/technical/COMPLAINTS_PART4_SPEC.md` section 6. Not yet implemented.

# 7. Scope Boundaries

Not included in Version 1:

- Anonymous complaints and secret access codes. (DEC-030)
- Attachments. (DEC-080)
- A public social feed. (DEC-081)
- Student comments on collective issues. (DEC-241)
- Chat or follow-up messaging. (DEC-052, DEC-263)
- Email or other external notifications. (DEC-070)
- General university or department announcements. (DEC-083)
- Complaint priority levels, priority queues and overdue indicators. (DEC-226)
- Automatic semester promotion. (DEC-021)
- Google Calendar integration. (DEC-061)
- A separate department-admin, Administrator or HOD portal. (DEC-082)
- Special routing for complaints against administrators or the Super Admin. (DEC-230)
- A university-wide deployment. (DEC-002)

New features can be proposed. They require discussion and the owner's approval before they become requirements.

# 8. Design Philosophy and User Experience

Design is a core product concern, not a final styling exercise. (DEC-120)

## 8.1 Direction

Modern, clean, professional, consistent, intuitive, accessible, responsive and trustworthy, with a recognisable visual identity connected to UOL.

## 8.2 UOL branding

We intend to use appropriate UOL branding. Official brand assets and guidelines must be researched and validated before the interface is finalised (O18). Do not invent an official palette or present unofficial choices as UOL standards.

## 8.3 Mobile-first

The interface must work well on phones, tablets, laptops and desktops. Many students may use the platform mainly on their phones.

## 8.4 Interface quality

We want:

- Consistent spacing and typography.
- Clear information hierarchy.
- Reusable components.
- Intuitive navigation.
- Clear form validation.
- Helpful empty, loading and error states.
- Accessible contrast and readable text.
- A consistent experience across all roles.

We avoid:

- Generic dashboard templates.
- Excessive gradients and decorative effects.
- Unnecessary animation.
- Cluttered layouts.
- Charts that communicate nothing.

## 8.5 Design process

Before implementing a major interface:

1. Identify the user and their objective.
2. Understand the workflow.
3. Establish the information hierarchy.
4. Explore layouts.
5. Discuss visual direction.
6. Agree on the design.
7. Implement reusable components.
8. Review on mobile and desktop.

The contents of each dashboard are confirmed (section 6.8). The design system and visual references are not yet approved (O18).

# 9. Technical Direction

| Area | Technology |
|---|---|
| Language | Python 3.13 (3.13.15 installed) |
| Backend | Django 5.2 LTS (5.2.19 installed) |
| Database | MySQL. Development on the existing MySQL Server 8.0.44. |
| Authentication | Google OAuth (library not yet chosen) |
| Configuration | `.env` loaded with python-dotenv |
| Frontend rendering | Django Templates |
| Structure and styling | HTML and CSS |
| Client-side behaviour | Vanilla JavaScript |
| UI framework | Bootstrap 5.3 |
| Dynamic interactions | HTMX only where genuinely useful |
| Testing | Django testing framework and pytest |
| Version control | Git and GitHub |
| IDE | Visual Studio Code |
| Database management | MySQL Workbench |
| AI-assisted implementation | Claude Code |

## 9.1 Architectural philosophy

A straightforward, maintainable Django application. No microservices, Kubernetes, separate Node.js backend, React, Next.js or Redis without a justified proposal and approval. (DEC-101)

## 9.2 Database and environment

- Development takes place on Windows 11.
- The project uses its own database, `uol_student_affairs` (utf8mb4), on the existing MySQL Server 8.0.44, through an application user whose privileges are limited to that database. (DEC-290)
- The existing MySQL 8.0.44 installation must be preserved. (DEC-102)
- The databases `db_final_group_project_working` and `db_final_group_project` belong to another academic project and must never be modified or deleted. (DEC-102)
- MySQL 8.4 LTS remains a future evaluation and target question (O19). It is not installed, and upgrading the existing server is not approved. (DEC-100)
- Secrets are loaded from `.env`; `.env.example` contains placeholders only. Secrets are never committed or written into documentation. (DEC-291, DEC-103)

# 10. Security and Privacy Principles

Complaints are identified and linked to student accounts, so the platform holds records that connect named students to their concerns. Protecting those records is a central requirement.

Confirmed access rules:

- Students see only their own complaints, Student Voice submissions and meetings.
- BAs see only their explicitly assigned sections.
- CR/GR gain only representative permissions and cannot see individual complaints, private Student Voice submissions or other students' meetings.
- Advisor responses to collective issues are private to CR/GR.
- The Super Admin has department-wide oversight.
- Student profile changes are audited.
- Deactivation preserves history.
- Aggregate reporting must not expose individual identities.

Areas requiring careful technical design:

- Google OAuth and restriction to permitted accounts.
- Enforcement of every access rule above on the server.
- Secure bootstrap of the initial Super Admin.
- Input validation and CSRF protection.
- Session management.
- Sensitive information in logs.
- Storage of OAuth credentials and other secrets.

The detailed threat model and security testing plan are still to be developed (O22).

# 11. AI-Assisted Development Strategy

## 11.1 Roles

| Collaborator | Responsibilities |
|---|---|
| ChatGPT | Requirements analysis, planning, architectural critique, security review, explanations, independent evaluation of Claude's proposals. |
| Claude | Independent product brainstorming, design exploration, requirements challenges, technical recommendations, implementation planning, critical evaluation of ChatGPT's suggestions. |
| Claude Code | Implementation, file editing, testing, debugging, and Git operations with the owner's approval. |
| Project owner | The only person authorised to approve product decisions. Sets priorities, gives final acceptance, and learns and understands the code. |

The two AI collaborators are meant to give independent perspectives. Neither should simply agree with the other.

## 11.2 Collaboration cycle

1. Identify a product problem or feature.
2. Discuss it with ChatGPT.
3. Give Claude the same context for an independent proposal.
4. Compare both perspectives and challenge assumptions.
5. The owner decides.
6. Update `DECISIONS.md` and the affected documents.
7. Give Claude Code the approved specification.
8. Implement incrementally.
9. Test and review.
10. Commit and push verified work.

## 11.3 Shared context

The GitHub repository is the canonical source of truth. (DEC-004)

Context documents are changed in the repository first, through a reviewed commit. The exact committed versions are then copied to the Claude Project knowledge and shared with ChatGPT. No collaborator treats an uncommitted draft as current context.

# 12. GitHub and Engineering Workflow

Repository: https://github.com/azeemworks925-eng/uol-student-affairs

- Keep `main` stable and tested.
- Use feature branches for substantial features.
- Make logical, meaningful commits.
- Review changes before committing.
- Test before merging.
- Push meaningful, verified work during every working session.
- Do not create artificial commits.
- Never push knowingly broken work to `main`.
- Never commit secrets.

Example commit messages:

- `docs: reconcile project context with confirmed decisions`
- `feat: implement Google sign-in`
- `fix: prevent duplicate support on collective issues`
- `test: add complaint workflow tests`
- `security: enforce advisor section permissions`

The owner wants to understand each Git operation, not run commands blindly.

# 13. Current Status

Three things are kept distinct.

The authoritative, dated status is the "Status at a glance" table in `DEVELOPMENT_LOG.md`. Summary on 2026-11-18:

- Merged into `main` and verified locally (no deployment):
  - Django foundation;
  - authentication and account foundation (Google sign-in tested only with simulated Google responses);
  - production frontend milestone 1;
  - Complaints Parts 1–3;
  - Complaints Part 4 Stages 1–4a: Super Admin workspace and owner assignment, category management, in-app notifications, academic terms and the term filter.
- Specified, not implemented: Complaints Part 4 Stage 4b, the privacy-safe analytics on the Super Admin Overview (DEC-316 to DEC-322).
- Not implemented: collective issues, Student Voice, meetings and the calendar, and Batch Advisor statistics.

The original foundation record follows, kept for history.

**1. Django foundation: created and tested locally**

- Windows 11 development environment.
- Python 3.13.15 and Django 5.2.19.
- MySQL Server 8.0.44, with the database `uol_student_affairs` created with utf8mb4.
- Application database user with privileges limited to the project database.
- Django project structure created with `manage.py` and `config`.
- Custom `accounts.User` model created.
- Initial accounts migration generated and applied.
- Settings load secrets from `.env` using python-dotenv; `.env.example` exists with placeholders.
- Django system check passed; database connection and migrations verified.

**2. Product features** (historical; superseded by the summary above)

At the time of the foundation, no business workflow or user-facing feature had been implemented.

**3. Commit and push status**

Whether the foundation work has been committed and pushed is not recorded in this brief. Confirm it with `git status` and `git log`, then replace this paragraph with the actual state.

# 14. Development Roadmap

A proposed roadmap, not a fixed schedule.

| Phase | Content | State |
|---|---|---|
| 1. Requirements | V1 product workflows, roles and boundaries. | Confirmed. Three workflow details remain (O27 to O29). |
| 2. Development foundation | Environment, Django project, database, custom user model, secrets handling. | Created and tested locally. |
| 3. System design | App structure, database schema, permission enforcement, state transitions, threat model. | Next (O20, O22). |
| 4. Product design and UX | UOL brand research, user journeys, wireframes, design system, responsive review. | To do (O18). |
| 5. Incremental implementation | One feature at a time. Each has confirmed requirements, acceptance criteria, an implementation plan, tests, a code review and updated documentation. | In progress (see section 13). |
| 6. Quality assurance | Functional, permission, security, responsive, usability and regression testing. | Not started. |
| 7. Demonstration and potential pilot | README, screenshots, setup instructions, architecture diagrams, demonstration. Any pilot requires approval from the appropriate university stakeholders. | Not started. |

Phases 3 and 4 can overlap, and implementation can begin on features whose requirements and design are ready.

# 15. Open Items

Product workflows are settled. The complete list of remaining items is in `DECISIONS.md`, section 5.

**Technical implementation choices**

- Domain enforcement and verification for students and staff (O2).
- Google OAuth library, client setup and credential handling (O3).
- Bootstrap mechanism for the initial Super Admin (O26).
- Django app structure and database schema (O20).
- Design system, official UOL brand assets and visual references (O18).
- Threat model and security testing plan (O22).
- Deployment, hosting, backups and recovery (O21).
- Future MySQL 8.4 evaluation (O19).
- Project licence (O23).

**Workflow details needing a short answer from the owner**

- Which BA is relevant for collective issues, Student Voice and meeting requests when a cohort has several BAs (O27; resolved for complaints by DEC-310).
- Meeting status names, and whether a student can cancel or ask to reschedule a confirmed meeting (O29).

Open items are resolved when the work reaches them. They do not block features they do not affect.

# 16. Instructions to AI Collaborators

Read this document together with `PROJECT_CONTEXT.md`, `DECISIONS.md` and `DEVELOPMENT_LOG.md`.

- Preserve all CONFIRMED decisions. Do not reopen settled product decisions.
- Never treat an OPEN item as decided.
- Never invent requirements, stakeholder feedback or implementation progress.
- Separate confirmed product decisions from technical implementation choices.
- Challenge weak ideas and explain trade-offs, clearly labelled as proposals.
- Avoid unnecessary technical complexity.
- Implement a feature only when its requirements are confirmed, and never claim it works without testing it.

**Think like a product team building a real university platform, while respecting the realities of an individual academic project.**
