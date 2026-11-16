# Authentication and Account Foundation

**Status:** Implemented and tested with simulated Google responses. **Not yet verified with a real UOL Google account** (see section 8).
**Related decisions:** DEC-010 to DEC-016, DEC-020, DEC-021, DEC-200 to DEC-205, DEC-210 to DEC-212. Open items O2, O3, O20 and O26.

## 1. Sign-in flow

Every role uses one sign-in page with one "Sign in with Google" button. There is no role selector (DEC-010, DEC-200).

1. The user submits the sign-in form. This is a CSRF-protected POST; a GET only shows a confirmation page.
2. They are redirected to Google with a one-time `state` value and a PKCE challenge, requesting only the `openid email profile` scopes.
3. Google redirects back with an authorization code. The server exchanges it for an ID token directly with Google over TLS.
4. django-allauth validates the ID token's issuer (`https://accounts.google.com`), audience (our client ID), expiry and `state`.
5. `accounts.adapters.PortalSocialAccountAdapter` applies the portal's identity rules (section 3).
6. The user is signed in and sent to `/`, which redirects by stored role. A student who has not registered is sent to registration first.

Google's OAuth tokens are not stored (`SOCIALACCOUNT_STORE_TOKENS = False`). Only the identity claims are kept, in allauth's `SocialAccount.extra_data`.

## 2. Library choice (proposed resolution of O3)

**django-allauth 65.22.1** with its Google provider (`requirements.txt` pins it and its dependencies). Reasons:

- It is very actively maintained.
- It validates Google ID tokens and protects against login CSRF, using a POST start, a `state` parameter and PKCE.
- It binds each Google identity to one user through a unique `(provider, uid)` record.
- Its adapter hooks let the portal decide account matching without patching the library.

`SOCIALACCOUNT_ONLY = True` removes password login, sign-up, password reset and email-confirmation URLs entirely. The Django admin's password login page is replaced by a redirect to the Google sign-in page.

On signatures: when the ID token arrives through the direct server-to-Google exchange, allauth skips signature verification, as OpenID Connect Core 1.0 section 3.1.3.7 allows. It always checks the issuer, audience and expiry. Tokens posted by browsers to `/accounts/google/login/token/` (Google One Tap) are signature-verified against Google's published keys.

## 3. Identity rules

All rules are in `accounts/identity.py` and `accounts/adapters.py`.

| Rule | Detail |
|---|---|
| Email normalization | The whole address is lowercased and stripped, everywhere: creation, validation, admin forms, sync and async lookups. |
| Verified email | Google's `email_verified` claim must be true. |
| Hosted domain | By default Google's `hd` claim must be present and listed in `UOL_GOOGLE_ALLOWED_HOSTED_DOMAINS`. Only Google Workspace accounts carry `hd`, so personal Google accounts are refused. Configurable; see section 8. |
| Student email | Exactly eight digits followed by `@student.uol.edu.pk` (DEC-011). The SAP ID is extracted from it and never typed by the student. |
| Staff email | A domain in `UOL_STAFF_EMAIL_DOMAINS` (default `uol.edu.pk`; O2). The student domain is never accepted as a staff domain. |
| Known Google identity | Signs in to its linked account. If the Google email no longer matches the account's email, sign-in is refused. |
| Unknown Google identity, existing account | It is linked to the account with the same email. This is how Super Admin-created accounts are activated. If that account is already linked to a different Google identity, sign-in is refused. |
| Unknown Google identity, no account | Only a valid student email may sign up (DEC-012). Any other email is refused, because staff accounts are created only by the Super Admin (DEC-013). |
| Inactive account | Sign-in is refused, and existing sessions stop working on their next request. |
| Linking extra accounts | Not supported. Connecting or disconnecting Google accounts is refused. |

## 4. Account model

| Topic | Implementation |
|---|---|
| Roles (review M1) | `role` is the single source of truth. `User.save()` sets `is_staff` and `is_superuser` to true only for the Super Admin and false for everyone else, whatever was passed in. Only the Super Admin can open the Django admin. |
| Validation (review M2) | `create_user()` runs full model validation: email format, a known role, the role's email rule, and uniqueness. |
| Full name | `User.full_name`, collected at student registration (DEC-201) and entered by the Super Admin for staff. `first_name`/`last_name` remain from Django's base model but are unused. |
| SAP ID | `StudentProfile.sap_id`: unique, not editable, always derived from the student email on save. |
| Department | `StudentProfile.department`, fixed at "Software Engineering" (DEC-201). |
| Deactivation | `is_active = False`. Accounts, student profiles and audit records cannot be deleted in the admin (DEC-212). Advisor assignments can be removed, because assignments change (DEC-204). |
| Email and role | Fixed after creation in the admin. The email is the Google identity, and the role defines the account type. |
| Audit (DEC-211) | `StudentProfileChange` records the Super Admin's changes to a student's full name, batch, semester and section: old and new values, who made the change, and when. It is read-only in the admin. |
| Academic structure (DEC-020, DEC-210) | The `academics` app holds `Batch`, `Semester` and `Section` with `is_active` flags. They cannot be deleted. Inactive entries are not offered at registration. |

| Advisor assignments | `AdvisorAssignment` links a Batch Advisor to one **cohort**: the exact batch + semester + section combination (DEC-205). All three are required. Each advisor and cohort pair is unique. Several advisors may share a cohort, and one advisor may hold several cohorts (DEC-204). |

Migrations:
- `academics/0001_initial` and `accounts/0002_account_foundation` are additive; `accounts/0001_initial` is unchanged.
- `accounts/0003_advisor_assignment_batch` adds the required batch and replaces the unique constraint, changing it from advisor + semester + section to advisor + batch + semester + section.
  - A batch cannot be inferred for an assignment made before batches were part of the scope, and guessing would give an advisor access to the wrong students. So the migration's first step refuses to continue if any assignments exist.
  - It does this before any schema change, which matters because MySQL cannot roll back schema changes. Nothing is changed or deleted, and the error message lists each assignment.
  - Recovery: record the listed assignments, remove them, run `migrate` again, then re-create each with its batch.
  - Both the refusal and the normal path are covered by `accounts/tests/test_migrations.py`.

## 5. Staff accounts and the initial Super Admin

**Initial Super Admin (proposed resolution of O26).** Run on the server:

```
python manage.py bootstrap_super_admin --email head.advisor@uol.edu.pk --full-name "Full Name"
```

The command:
- runs only when no Super Admin exists;
- requires a staff-domain email;
- sets no password.

The Super Admin then signs in with Google. The first sign-in links their Google identity to the account. Because the command needs shell access to the server, it cannot be triggered from the web.

**Batch Advisors (DEC-013).** The Super Admin creates them in the admin (Accounts → Users → Add) with name, official email and role. No password is set. The advisor's first Google sign-in with that email activates the account; the user list shows "Google sign-in: Linked" or "Not signed in yet". Cohorts (batch, semester and section, all required) are assigned on the advisor's page or under Accounts → Advisor assignments. One advisor may hold several cohorts, and several advisors may share a cohort (DEC-204). There is no self-registration.

Django's own `createsuperuser` command still works, but it creates a password that no page accepts. Use `bootstrap_super_admin`.

## 6. Access control for later modules

From `accounts.permissions`:

- Decorators: `student_required`, `batch_advisor_required`, `super_admin_required`, and `role_required(*roles)`. They redirect anonymous users to sign-in and return 403 for any other role.
- `visible_student_profiles(user)`: everything for the Super Admin, only students in the advisor's assigned cohorts for a Batch Advisor, only their own profile for a student, and nothing for inactive or anonymous users.
- `can_access_cohort(user, batch, semester, section)`: the same rule for a single cohort.

A cohort matches only when **all three** of batch, semester and section match. An advisor assigned to Fall 2024, Semester 4, Section A cannot see Spring 2025, Semester 4, Section A. When a later module scopes its own records, such as complaints, it must filter on all three fields as well, for example through the profile of the student who owns the record.

Access is decided only from the stored role and assignments, never from URL or request parameters. `StudentRegistrationMiddleware` keeps unregistered students on the registration page whatever URL they request.

## 7. Configuration

| Variable | Purpose | Default |
|---|---|---|
| `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` | OAuth client. Without both, the sign-in page says Google is not configured. | empty |
| `UOL_STAFF_EMAIL_DOMAINS` | Comma-separated staff email domains | `uol.edu.pk` |
| `UOL_GOOGLE_REQUIRE_HOSTED_DOMAIN` | Require the `hd` claim | `True` |
| `UOL_GOOGLE_ALLOWED_HOSTED_DOMAINS` | Accepted `hd` values | `student.uol.edu.pk,uol.edu.pk` |
| `DJANGO_SESSION_COOKIE_AGE` | Session length in seconds | `28800` (8 hours) |
| `DJANGO_SECURE_COOKIES` | Secure-only session and CSRF cookies | `True` whenever `DEBUG` is off |

Secrets live only in `.env`, which is never committed. Session cookies are HttpOnly with `SameSite=Lax`, which keeps the session across Google's top-level redirect back.

**Local setup.** In Google Cloud Console, create an OAuth client of type "Web application" with the authorized redirect URI `http://localhost:8000/accounts/google/login/callback/`. Then put the client ID and secret in `.env`. There is no development bypass: a manual end-to-end test needs a real Google account that passes the identity rules.

## 8. External verification required

None of the following has been verified. No real UOL Google account has signed in. The automated tests prove the portal's logic against simulated Google responses only. Before claiming that UOL accounts work, confirm each item and record the outcome in `DEVELOPMENT_LOG.md`:

1. **UOL uses Google Workspace for both domains.** `@student.uol.edu.pk` and `@uol.edu.pk` must be Google Workspace accounts, not Microsoft 365 or another provider. If students are not on Google Workspace, Google sign-in with those addresses is not possible as designed.
2. **UOL permits the app.**
   - The Workspace administrator's API controls ("third-party app access") may block unconfigured apps. If so, UOL IT must allow or trust this app's OAuth client ID.
   - Ask UOL IT whether apps requesting only basic sign-in information (`openid email profile`) are allowed for students and staff.
3. **The actual `hd` values.** Sign in once with a real student account and a real staff account. Inspect `SocialAccount.extra_data["hd"]` in the admin, then set `UOL_GOOGLE_ALLOWED_HOSTED_DOMAINS` to those values. A secondary domain may report the organization's primary domain instead of the email's domain. If the claim is absent, Workspace is not in use (item 1).
4. **`email_verified` is true** for UOL accounts in the same test.
5. **Official staff email domain(s)** for Batch Advisors and the Super Admin (O2). `uol.edu.pk` is an assumption.
6. **OAuth consent screen and publishing.**
   - A Google Cloud project outside UOL's Workspace organization must use the "External" user type.
   - While the app is in "Testing" status, only listed test users can sign in.
   - Check Google's current requirements for moving to "In production" with only the basic scopes.
   - A project created inside UOL's Workspace organization by UOL IT could use the "Internal" user type instead. That decision belongs to UOL.

## 9. Known limitations

- **MySQL warning W036 during `migrate`.** MySQL cannot enforce two conditional unique constraints on allauth's `EmailAddress` table. The portal's identity guarantees do not depend on that table; they rest on `User.email UNIQUE` and `SocialAccount (provider, uid) UNIQUE`.
- **Google One Tap endpoint.** allauth also exposes `/accounts/google/login/token/`. It verifies signatures and goes through the same adapter rules.
- **Placeholder pages only.** The pages are deliberately plain placeholders until the design direction is agreed (DEC-120).
