# UOL Student Affairs — Project Context

## 1. Project Overview

**Project Name:** UOL Student Affairs  
**Subtitle:** Student Affairs & Engagement Portal  
**Institution:** The University of Lahore (UOL)  
**Project Type:** Individual BS Software Engineering semester project  
**Initial Target:** Software Engineering Department

UOL Student Affairs aims to provide a centralized digital platform for student engagement, communication, feedback, and student affairs workflows.

This is an academic project with the ambition of becoming suitable for a departmental pilot. It is not currently an officially commissioned university system.

## 2. Project Goals

- Provide structured channels for student feedback.
- Help academic advisors manage student concerns.
- Support suggestions and appreciation submissions.
- Facilitate student-advisor meeting coordination.
- Provide useful aggregate insights for departmental decision-making.
- Deliver a polished, responsive experience on desktop and mobile.

## 3. Confirmed Functional Decisions

### Student Access
- Students verify their UOL university email through an OTP.
- Students declare their name, department, batch, and section.
- SAP ID will not be used for automatic section assignment.
- Students do not require manual account approval.

### Advisor Access
- Advisor accounts require manual Super Admin approval.
- Super Admin assigns sections to advisors.
- Multiple advisors may serve the same section.
- There is one active CR per section in Version 1.

### Complaints
- Students can submit anonymous complaints.
- Anonymous complaints are accessed using a reference number and secret access code.
- Anonymous complaints are not linked to student accounts.
- Complaints concerning the Administrator or HOD should be directed to the appropriate official university channel.

### Suggestions and Appreciation
- Suggestions and appreciation are separate submission types.
- Each has its own simple status workflow.

### Meetings
- Advisors and students can coordinate meetings.
- Meeting workflows include proposal, confirmation, and rescheduling.

### Advisor Dashboard
- Include three priority queues under "Needs Attention".
- Exact queue rules and labels are still to be designed.

### Notifications
- In-platform notifications are planned for Version 1.

### Administration
- Super Admin manages advisor approval and section assignments.
- A separate department-admin portal is not included in Version 1.

### Analytics
- Provide meaningful aggregate statistics.
- Include useful breakdowns such as complaint categories and sections.
- Avoid exposing individual students through aggregate reporting.
- Exact metrics, filters, and visualizations remain to be designed.

## 4. Planned Technology Stack

- Python 3.13
- Django 5.2 LTS
- MySQL 8.4 LTS (target)
- Django Templates
- HTML, CSS, and vanilla JavaScript
- Bootstrap 5.3
- HTMX only where genuinely useful
- Git and GitHub
- Django testing framework and pytest
- Visual Studio Code
- MySQL Workbench
- Claude Code for AI-assisted development

Avoid unnecessary complexity such as microservices, Kubernetes, or a separate Node.js backend.

## 5. Environment Constraints

- Development environment: Windows 11.
- Existing MySQL Server 8.0.44 is installed and must be preserved.
- Existing banking project databases must not be modified or deleted.
- Do not upgrade, uninstall, reset, or change MySQL configuration without explicit approval and verified backups.
- Evaluate a safe MySQL 8.4 setup before using it.
- Never commit passwords, secret keys, environment files, or credentials to GitHub.

## 6. Development Principles

- Build incrementally, one feature at a time.
- Keep the architecture understandable and maintainable.
- Follow Django security and permission best practices.
- Validate user input on the server side.
- Write tests for important workflows.
- Use meaningful Git branches and commit messages.
- Explain significant implementation decisions.
- Do not introduce features that have not been discussed or approved.
- Do not claim a feature works until it has been tested.

## 7. Git Workflow

- `main` should contain stable, tested code.
- Use feature branches for substantial features.
- Make small, meaningful commits.
- Review changes and test before merging into `main`.
- Do not push unreviewed changes to `main`.

## 8. Open Decisions

The following details still require discussion and must not be assumed:

- Final database architecture and schema.
- Exact complaint statuses and workflows.
- Exact priority queue definitions.
- OTP email delivery provider.
- Final analytics metrics and filters.
- Detailed permissions and role boundaries.
- Deployment environment and hosting.
- Final UI design and branding assets.

## 9. Current Development Status

- Local project directory created.
- Git repository initialized on `main`.
- GitHub remote configured.
- `.gitignore` created.
- Initial README created.
- Application implementation has not started.

---

**Important instruction for AI coding agents:** Treat this document as the current project context, not permission to make product decisions independently. Ask before changing confirmed requirements or resolving significant open decisions. Keep this document updated when decisions are formally approved.
