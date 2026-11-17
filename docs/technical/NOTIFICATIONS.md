# In-app notifications — technical notes

**Status:** Complete. The foundation and the two complaint producers (Complaints Part 4 Stage 3) were merged into `main` through PR #16 (merge commit `d857d276f94c38bc081e7b86bf9a3205ddc16dee`). Migration `notifications.0001_initial` has been applied to the owner's local development database.
**Decisions:** DEC-070 (in-app only), DEC-270 (events), DEC-301 (quiet colour), DEC-304 (notifications in the student phone header). Specification: `COMPLAINTS_PART4_SPEC.md` section 5.

There is no email, push, SMS, external messaging, broadcast, recipient picker or extra OAuth scope, and no Celery, Redis, WebSockets or separate API.

## 1. Model (`notifications/models.py`)

`Notification` holds one notification for one recipient.

| Field | Meaning |
|---|---|
| `recipient` | The user (`CASCADE`: notifications are derived data; users are deactivated, not deleted) |
| `event_type` | A key in `notifications/registry.py`, for example `complaint.response` |
| `source_type`, `source_id` | The source record's model label (for example `complaints.complaintevent`) and primary key |
| `title`, `body` | Concise, written once (150 and 300 characters) |
| `target_url_name`, `target_arg` | An allowlisted route name and one argument. Never a URL. |
| `created_at`, `read_at` | `read_at` is `NULL` while unread; reading sets it once |

**Constraints and indexes**
- `unique_notification_per_recipient_source` on `(recipient, source_type, source_id)`;
- `notification_unread_idx` on `(recipient, read_at)` and `notification_recent_idx` on `(recipient, -created_at)`;
- ordering: newest first.

**Write-once content**, matching the complaint models' standard:
- `QuerySet.update()` and `bulk_update()` accept only `read_at`;
- an upserting `bulk_create(update_conflicts=True)` is refused;
- instance `save()` only inserts (`force_insert`) or updates `read_at` (`update_fields`);
- a newly built object carrying an existing primary key is refused;
- violations raise `ProtectedNotificationError`; plain inserts work.

Raw SQL is outside what the ORM can protect.

Migration: `notifications/0001_initial` creates only this table, its constraint and its indexes. It is reversible, and a test reverses and re-applies it on MySQL and SQLite.

## 2. Registry (`notifications/registry.py`)

Each event type declares a `NotificationType`: the `source_model` its source records must be, and the `destinations` (route names) it may open. Registered now:

| Event type | Source model | Destination |
|---|---|---|
| `complaint.status_changed` | `complaints.complaintevent` | `student_complaint_detail` |
| `complaint.response` | `complaints.complaintevent` | `student_complaint_detail` |

**Adding a future producer** (DEC-270: official Student Voice answers; meeting confirmation, rescheduling and cancellation; new CR/GR issues):
1. register the type with its source model and destinations;
2. call `notify()` from the module's service, inside its transaction;
3. decide the recipients with that module's own requirements. None are decided here.

## 3. Services (`notifications/services.py`)

- **`notify(recipient, *, event_type, source, title, body, target_url_name, target_arg)`**, for producers:
  - **Checks:** the type is registered; the destination is allowed for the type and resolves; and the source is a **persisted row** of the declared model. A non-NULL pk alone is not accepted as proof. The source must:
    - be a Django model instance of the declared model;
    - not be marked as new (`_state.adding`);
    - have a pk and a database alias (`_state.db`);
    - still have its row on that alias (checked with `_base_manager.using(source._state.db)`).

    So an unsaved instance built with an explicit pk, even one matching an existing row, and an instance whose row has been removed, are rejected.
  - **Writes:** truncates the title and body, then `get_or_create` on the unique key. The savepoint means a concurrent duplicate returns the existing row and never breaks the caller's transaction. Returns `(notification, created)`.
  - **Recipients:** it does **not** require an active recipient, so deactivated users keep their notifications for when they are reactivated.
- **User-facing functions:** `for_user`, `unread_count`, `mark_read` and `mark_all_read`.
  - They require an **authenticated, active** user; anonymous or inactive users get nothing.
  - They are always scoped to `recipient=user`.
  - `mark_read` is idempotent and keeps the first read time, using an `update` filtered on `read_at IS NULL`.
- **`destination_url(notification)`:** builds the URL only from the registry and `reverse()`. It returns `None` if the stored route isn't allowed for the type or no longer resolves.

## 4. Pages and header

| Route | Name | Method |
|---|---|---|
| `/notifications/` | `notifications` | GET: the user's notifications, newest first, 20 per page. Viewing does not mark anything read. |
| `/notifications/<pk>/open/` | `notification_open` | POST: marks the user's own notification read, then 303-redirects to `destination_url`. Another user's ID is a 404 identical to a missing one. A disallowed or stale destination returns to the list with a message. |
| `/notifications/read-all/` | `notifications_mark_all_read` | POST |

- **Access:** every view is `login_required`, and the auth backend signs inactive users out. Changes require POST and CSRF. Unregistered students are sent to registration by the existing middleware.
- **A notification grants no access.** The destination view runs its own permission checks; for example, `student_complaint_detail` uses `get_visible_complaint`.
- **Header entry point** (`templates/includes/notifications_link.html`): it sits outside the role navigation, so the student's four bottom-bar destinations (DEC-304) and the Super Admin Overview links are unchanged.
  - **Placement:** a "Notifications" row in the student and Super Admin sidebar, a bell in the Batch Advisor rail, and a bell in the phone header for every role.
  - **Badge:** neutral ink, "9+" above nine.
  - **Accessible name:** "Notifications, N unread" or "Notifications, none unread", with `aria-current` on the notifications page.
  - **Count:** the `notifications.context_processors.notifications` context processor provides a lazy object. Its single indexed `COUNT` runs only when the application layout reads it, and never for anonymous or inactive users.

## 5. Complaint producers

See `docs/technical/COMPLAINTS.md` section 7.
