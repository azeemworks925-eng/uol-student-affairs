# UOL Student Affairs
## Master Project Brief

**Product name:** UOL Student Affairs  
**Product subtitle:** Student Affairs & Engagement Portal  
**Institution:** The University of Lahore (UOL)  
**Initial target:** Software Engineering Department  
**Project type:** Individual BS Software Engineering, fourth-semester academic project  
**Repository:** https://github.com/azeemworks925-eng/uol-student-affairs  
**Current phase:** Product discovery and requirements engineering  
**Document status:** Initial master brief — living document

---

# 1. Executive Summary

UOL Student Affairs is a proposed Student Affairs & Engagement Portal intended to improve communication, student engagement, feedback management, advisor coordination, and student affairs workflows at The University of Lahore.

The initial target is the Software Engineering Department, with the possibility of a departmental pilot if the product reaches an appropriate standard and relevant stakeholders support it.

The platform is not intended to be merely a complaint submission website. Its broader vision is to provide a structured digital environment through which students can communicate concerns, share suggestions, express appreciation, coordinate with academic advisors, and participate in departmental engagement activities.

The project is being developed as an individual fourth-semester BS Software Engineering academic project. However, the ambition extends beyond simply meeting course requirements.

We want to build something genuinely useful, secure, maintainable, professional, and sufficiently polished to demonstrate to university stakeholders.

**Important distinction:** This is an independently developed academic project. It is not an officially commissioned, approved, or deployed university system.

# 2. Project Origin and Story

The project originated as an individual academic project for the Data Structures and Algorithms (DSA) course during the fourth semester of the BS Software Engineering program at UOL.

The initial concept focused on providing students with a better way to communicate feedback and concerns to their academic advisors.

As the idea developed, it became clear that the opportunity could be broader than complaint management alone.

Students and advisors need structured ways to communicate, coordinate, share feedback, and understand recurring departmental concerns.

This led to the broader product direction:

**UOL Student Affairs — Student Affairs & Engagement Portal.**

The project gradually evolved from a basic student feedback concept into a proposed platform covering multiple student-affairs workflows.

We want to approach its development as a real software engineering project, including stakeholder research, requirements engineering, product design, architecture, implementation, testing, documentation, and potential deployment.

# 3. Stakeholder Engagement and Initial Validation

## 3.1 Batch Advisor Interaction

The project concept and initial prototype were presented to a batch advisor from the Software Engineering Department.

The advisor responded positively to the direction of the project.

The advisor:
- Liked the concept and its potential usefulness.
- Encouraged further research with advisors.
- Expressed willingness to help with departmental deployment if the platform is developed well.

This feedback is encouraging, but it does not constitute formal university approval or a deployment commitment.

## 3.2 Identified Communication Problem

An initial stakeholder discussion highlighted that students currently raise concerns through informal communication channels.

This creates an opportunity for a more structured process for submitting, tracking, managing, and understanding student feedback.

We should investigate this further rather than assume that one workflow will solve every communication problem.

## 3.3 Importance of Meaningful Analytics

The advisor expressed interest in useful, actionable aggregate statistics rather than decorative dashboards.

Potentially useful breakdowns include:
- Complaint distribution by category.
- Complaint distribution by section.
- Percentages and trends that help identify recurring concerns.

Aggregate reporting should not expose individual students or compromise anonymity.

The exact metrics, filters, time periods, and chart types remain undecided.

## 3.4 Further Stakeholder Research

Further advisor research is needed.

We should investigate:
- How advisors currently receive student concerns.
- How they prioritize and follow up on concerns.
- What makes an issue urgent.
- What information they need to manage their sections.
- How students currently request meetings.
- What communication problems occur repeatedly.
- What information advisors would find useful in reports.
- What privacy and confidentiality expectations exist.

Do not invent interview findings. Record actual stakeholder responses separately and distinguish observations from assumptions.

# 4. Product Vision

Our vision is to develop a centralized, student-focused engagement platform that makes communication between students and their academic department more structured, accessible, and manageable.

The product should support more than submitting complaints.

Its broader purpose includes:

1. Student feedback and concerns.
2. Anonymous complaint submission and follow-up.
3. Suggestions and appreciation.
4. Student-advisor interaction.
5. Meeting coordination.
6. Advisor workload and priority management.
7. Useful departmental insights through aggregate analytics.
8. Appropriate administrative oversight.

The product should feel like a cohesive platform rather than several unrelated forms placed inside one dashboard.

## 4.1 Product Principles

The product should be:

- Student-centered.
- Easy to understand.
- Privacy-conscious.
- Responsive across devices.
- Professionally designed.
- Secure by default.
- Maintainable and extensible.
- Grounded in real stakeholder needs.

We should prioritize genuine usability over unnecessary feature count.

# 5. Target Users and Roles

The initial product direction identifies the following roles.

## 5.1 Students

Students are the primary users of the platform.

They should be able to access student-facing workflows after verifying their UOL university email.

Students declare their own:
- Name.
- Department.
- Batch.
- Section.

Student section assignment will not be automatically determined using SAP IDs.

There is no manual student account approval requirement in the current design.

## 5.2 Academic Advisors

Advisors are responsible for handling student concerns and participating in relevant student-affairs workflows.

Advisor accounts require manual approval by the Super Admin.

The Super Admin assigns sections to advisors.

Multiple advisors may serve the same section.

Advisors need appropriate visibility into the students and workflows assigned to them, subject to approved permission rules.

## 5.3 Class Representatives

There is one active CR per section in Version 1.

The precise CR responsibilities, permissions, account lifecycle, and relationship with advisors require further definition.

## 5.4 Super Admin

The Super Admin handles:
- Advisor account approval.
- Advisor section assignments.
- Relevant administrative oversight.

A separate department-admin portal is not included in Version 1.

The complete Super Admin permission model remains to be designed.

# 6. Confirmed Functional Decisions

The following decisions have already been established and should not be silently changed.

## 6.1 Student Authentication

- Students verify their UOL university email using OTP.
- Students declare their name, department, batch, and section.
- SAP ID will not be used for automatic section assignment.
- Students do not require manual account approval.

The OTP delivery provider and detailed verification rules remain undecided.

## 6.2 Advisor Authentication and Approval

- Advisor accounts require manual Super Admin approval.
- Super Admin assigns sections to advisors.
- Multiple advisors may serve the same section.

Detailed advisor onboarding and permission rules remain open.

## 6.3 Anonymous Complaints

Anonymous complaints are an important part of the product.

Confirmed decisions:

- Students can submit complaints anonymously.
- Anonymous complaints are accessed using a reference number and secret access code.
- Anonymous complaints are not linked to student accounts.
- Complaints concerning the Administrator or HOD should be directed to the appropriate official university channel.

The complete anonymous complaint lifecycle still needs to be designed.

Important questions include:
- How are reference numbers generated?
- How are secret access codes generated and stored securely?
- How can a student safely retrieve an existing complaint?
- How are advisor responses delivered?
- How are attachments handled, if supported?
- What happens when a complaint is resolved?
- How do we prevent unauthorized access?
- What information can advisors see?

Do not assume answers to these questions without discussion.

## 6.4 Suggestions and Appreciation

Suggestions and appreciation are separate submission types.

Each has its own simple status workflow.

Their exact statuses, handling rules, and visibility permissions remain to be specified.

## 6.5 Meetings

Students and advisors should be able to coordinate meetings.

The established workflow includes:
- Meeting proposal.
- Confirmation.
- Rescheduling.

Cancellation, rejection, availability management, reminders, and other details remain open.

## 6.6 Advisor Dashboard

The advisor dashboard should include three priority queues under a section named:

**Needs Attention**

The exact queue names, priority rules, sorting logic, and transitions have not yet been decided.

Do not invent the three queues.

## 6.7 Notifications

In-platform notifications are planned for Version 1.

Email and external notification channels have not been approved as requirements.

## 6.8 Administration

- Super Admin manages advisor approval and section assignments.
- A separate department-admin portal is excluded from Version 1.

## 6.9 Analytics

Analytics should provide meaningful aggregate information.

Potential breakdowns include:
- Complaint categories.
- Sections.
- Percentages and other useful summaries.

Analytics should support decision-making rather than merely decorate dashboards.

Individual student privacy must be protected.

Exact reporting requirements remain open.

# 7. Scope and Product Boundaries

## 7.1 Initial Version 1 Direction

The initial version should focus on delivering the essential student and advisor experience.

The established functional areas are:

- Student email verification.
- Student profiles and declared academic information.
- Advisor accounts and approval.
- Advisor section assignments.
- Anonymous complaints.
- Suggestions.
- Appreciation.
- Student-advisor meeting coordination.
- Advisor priority queues.
- In-platform notifications.
- Useful aggregate analytics.
- Super Admin functionality.

This is an initial scope direction, not a fully finalized requirements specification.

## 7.2 Explicit Boundaries

Do not assume the following are included in Version 1:

- A separate department-admin portal.
- SAP ID-based automatic student assignment.
- A university-wide deployment.
- External notification services.
- Complex enterprise infrastructure.
- Features not supported by stakeholder research or approved requirements.

New features can be proposed, but require discussion and approval.

# 8. Design Philosophy and User Experience Ambition

Design is a core product concern, not a final styling exercise.

We want UOL Student Affairs to look and feel like a polished, professionally developed university platform.

## 8.1 Overall Design Direction

The intended qualities are:

- Modern.
- Clean.
- Professional.
- Consistent.
- Intuitive.
- Accessible.
- Responsive.
- Trustworthy.

The product should have a recognizable visual identity connected to UOL.

## 8.2 UOL Branding

We intend to use appropriate UOL branding, including its logo, colors, and visual identity.

Official brand assets and exact design guidelines need to be researched and validated before finalizing the interface.

Do not invent an official university brand palette or claim that unofficial design choices are official UOL standards.

## 8.3 Mobile-First Design

The interface must work well on:
- Mobile phones.
- Tablets.
- Laptops.
- Desktop screens.

Mobile usability is particularly important for students who may primarily access the platform using their phones.

## 8.4 Interface Quality

We want:
- Consistent spacing and typography.
- Clear information hierarchy.
- Reusable interface components.
- Intuitive navigation.
- Thoughtful dashboards.
- Meaningful visualizations.
- Clear form validation.
- Helpful empty states.
- Useful loading and error states.
- Accessible contrast and readable text.
- Consistent design across all user roles.

Avoid:
- Generic dashboard templates without product-specific thinking.
- Excessive gradients and decorative effects.
- Unnecessary animations.
- Cluttered interfaces.
- Inconsistent components.
- Charts that do not communicate meaningful information.
- Interfaces that look attractive but are difficult to use.

## 8.5 Design Process

Before implementing major interfaces:

1. Identify the user and their objective.
2. Understand the workflow.
3. Establish information hierarchy.
4. Explore appropriate layouts.
5. Discuss visual direction.
6. Agree on the design.
7. Implement reusable components.
8. Review on mobile and desktop.

We want to explore design references and professional UI patterns rather than immediately settle for the first generated layout.

The precise design system has not yet been approved.

# 9. Technical Direction

The currently agreed technology stack is:

| Area | Technology |
|---|---|
| Language | Python 3.13 |
| Backend | Django 5.2 LTS |
| Database target | MySQL 8.4 LTS |
| Frontend rendering | Django Templates |
| Structure and styling | HTML and CSS |
| Client-side behavior | Vanilla JavaScript |
| UI framework | Bootstrap 5.3 |
| Dynamic interactions | HTMX when useful |
| Version control | Git and GitHub |
| Testing | Django testing framework and pytest |
| Development IDE | Visual Studio Code |
| Database management | MySQL Workbench |

## 9.1 Architectural Philosophy

We prefer a straightforward, maintainable Django application.

Avoid unnecessary complexity such as:
- Microservices.
- Kubernetes.
- A separate Node.js backend.
- React or Next.js as an initial requirement.
- Unnecessary infrastructure dependencies.

Architecture decisions should be based on actual requirements, not technology trends.

## 9.2 Existing Environment Constraints

Development takes place on Windows 11.

The machine currently has MySQL Server 8.0.44 installed and running.

Existing databases belonging to another academic project must be preserved:

- `db_final_group_project_working`
- `db_final_group_project`

Do not upgrade, uninstall, reset, overwrite, or modify the existing MySQL installation or these databases without explicit permission and verified backups.

The safe approach to using the intended MySQL 8.4 target must be evaluated before implementation.

Never commit credentials, API keys, secret keys, or `.env` files.

# 10. Security and Privacy Principles

Security is especially important because the platform may handle confidential student concerns.

The system should follow appropriate Django security practices.

Areas requiring careful design include:

- Authentication.
- Authorization.
- Role-based permissions.
- Advisor section-level access.
- Anonymous complaint confidentiality.
- Secure secret-code handling.
- Input validation.
- CSRF protection.
- Session management.
- Password and credential storage.
- Sensitive information in logs.
- Secure file uploads if attachments are introduced.
- Protection against unauthorized access to complaint records.

Privacy should be considered during requirements and architecture design, not added after implementation.

The precise threat model and security requirements remain to be developed.

# 11. AI-Assisted Development Strategy

We intend to use two independent AI collaborators and Claude Code.

## 11.1 ChatGPT

Primary responsibilities:
- Product planning.
- Requirements engineering.
- Critical analysis.
- Architecture review.
- Security considerations.
- Explaining technical decisions.
- Independent evaluation of Claude's proposals.

## 11.2 Claude

Primary responsibilities:
- Independent product brainstorming.
- Product and design strategy.
- Identifying overlooked requirements.
- UI/UX exploration.
- Architecture proposals.
- Technical recommendations.
- Critical evaluation of ChatGPT's suggestions.
- Development planning.

Claude should not simply agree with ChatGPT.

We want independent thinking and reasoned disagreement.

## 11.3 Claude Code

Primary responsibilities:
- Working with the local codebase.
- Implementing approved features.
- Editing project files.
- Running tests.
- Debugging.
- Reviewing code changes.
- Supporting Git operations with the owner's approval.

## 11.4 Human Project Owner

The project owner:
- Makes final decisions.
- Approves requirements.
- Approves design direction.
- Approves architecture.
- Reviews significant implementation.
- Learns and understands the code.
- Approves Git operations and changes.

## 11.5 Collaboration Cycle

Our intended workflow:

1. Identify a product problem or feature.
2. Discuss it with ChatGPT.
3. Give Claude the same context for an independent proposal.
4. Compare both perspectives.
5. Challenge assumptions and evaluate alternatives.
6. Make a decision as the project owner.
7. Update project documentation.
8. Give Claude Code the approved specification.
9. Implement incrementally.
10. Test and review.
11. Commit and push verified work.

Do not begin major implementation merely because an idea sounds good.

# 12. GitHub and Engineering Workflow

Repository:

https://github.com/azeemworks925-eng/uol-student-affairs

GitHub is intended to remain updated throughout development.

We want a professional and understandable development history.

Rules:

- Keep `main` stable.
- Use feature branches for substantial features.
- Make small, meaningful commits.
- Test changes before merging.
- Push meaningful, verified work during every working session.
- Do not create artificial commits.
- Do not push knowingly broken code to `main`.
- Never commit secrets.

Example commit messages:

- `docs: add master project brief`
- `docs: define complaint workflows`
- `feat: implement student email verification`
- `fix: prevent duplicate complaint submissions`
- `test: add anonymous complaint workflow tests`
- `security: enforce advisor section permissions`

The owner wants to understand Git operations, not blindly execute commands.

# 13. Development Roadmap

The following is a proposed roadmap, not a rigid schedule.

## Phase 1 — Product Discovery and Requirements

- Establish product vision.
- Review stakeholder feedback.
- Conduct additional advisor research.
- Identify student and advisor needs.
- Define functional requirements.
- Define non-functional requirements.
- Identify privacy and security expectations.
- Clarify Version 1 scope.
- Document unresolved decisions.

## Phase 2 — Product Design and UX

- Establish design philosophy.
- Research UOL branding.
- Identify user journeys.
- Design information architecture.
- Explore interface references.
- Create wireframes.
- Develop a consistent UI design system.
- Review responsive layouts.

## Phase 3 — System Design

- Define application architecture.
- Design database entities and relationships.
- Establish permission boundaries.
- Define workflows and state transitions.
- Review security architecture.
- Document important technical decisions.

## Phase 4 — Development Foundation

- Establish a safe Python and Django environment.
- Finalize the MySQL development setup.
- Configure project settings.
- Establish environment variable handling.
- Set up Git branches and development practices.
- Configure testing.

## Phase 5 — Incremental Implementation

Build features in logically grouped stages.

Each feature should have:
- An approved specification.
- Clear acceptance criteria.
- An implementation plan.
- Appropriate tests.
- A code review.
- Updated documentation.

## Phase 6 — Quality Assurance

- Functional testing.
- Permission testing.
- Security testing.
- Responsive design testing.
- Usability testing.
- Regression testing.
- Stakeholder feedback.

## Phase 7 — Demonstration and Potential Pilot

Prepare:
- Professional documentation.
- A polished README.
- Screenshots and demonstrations.
- Setup instructions.
- Architecture diagrams.
- A demonstration suitable for academic evaluation and stakeholder discussion.

Any departmental pilot would require appropriate university stakeholder approval.

# 14. Open Decisions and Research Areas

These areas must not be treated as finalized.

## Product and Requirements
- Detailed student journeys.
- Detailed advisor workflows.
- Exact complaint categories.
- Complaint statuses and transitions.
- Suggestion and appreciation statuses.
- Meeting cancellation and rejection rules.
- CR responsibilities.
- Complete role and permission boundaries.

## Anonymous Complaints
- Reference-number format.
- Secret access-code generation and storage.
- Complaint retrieval process.
- Advisor response mechanism.
- Confidentiality boundaries.
- Retention and archival rules.

## Advisor Dashboard
- Names and definitions of the three priority queues.
- Queue entry and exit rules.
- Priority calculations.
- Sorting and filtering.

## Authentication
- OTP email provider.
- OTP expiration and resend rules.
- Rate limiting.
- Verification abuse prevention.
- Advisor onboarding details.

## Analytics
- Exact metrics.
- Filters and time periods.
- Visualization types.
- Privacy thresholds and aggregation rules.

## Design
- Official UOL branding assets.
- Final color palette.
- Typography.
- Navigation structure.
- Dashboard layouts.
- Component library and design tokens.

## Technical
- Safe MySQL 8.4 environment.
- Final database architecture.
- Detailed Django application structure.
- Deployment environment.
- Hosting and operational requirements.
- Backup and recovery strategy.

Do not resolve these automatically. Research, discuss, and obtain approval.

# 15. Immediate Priorities

At the time of writing, the project is still in planning.

The initial local repository contains:

- `.gitignore`
- `README.md`
- `PROJECT_CONTEXT.md`

The initial documentation commit has already been pushed to GitHub.

Application implementation has not started.

Our immediate priorities are:

1. Give all AI collaborators a consistent understanding of the project.
2. Conduct an independent strategic review with Claude.
3. Critically evaluate Claude's recommendations with ChatGPT.
4. Refine the product vision.
5. Identify gaps in stakeholder research.
6. Establish a clear design philosophy.
7. Define the Version 1 requirements.
8. Develop system architecture only when requirements are sufficiently clear.

---

# 16. Instructions to AI Collaborators

Read this document together with `PROJECT_CONTEXT.md` and `README.md`.

Treat this brief as a consolidated introduction, not as permission to invent requirements.

When reviewing the project:

- Preserve all confirmed decisions.
- Identify contradictions if you find any.
- Separate facts from assumptions.
- Identify missing stakeholder evidence.
- Challenge weak product ideas.
- Recommend improvements with reasons.
- Explain trade-offs.
- Avoid unnecessary technical complexity.
- Do not begin implementation yet.

We want an independent and honest assessment.

Our ambition is to create a high-quality product that is useful to students and advisors, technically sound, professionally designed, and suitable for a possible departmental pilot.

**Think like a product team building a real university platform, while respecting the realities of an individual academic project.**