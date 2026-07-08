# Future Improvements & Design Alignment

This document is the consolidated roadmap for the next phase of the Form Service.
It merges the earlier high-level design notes with the more detailed implementation
plan so there is one source of truth for future work, trade-offs, and sequencing.

The items below are intentionally deferred. They are not production blockers for
the current release, but they define the next implementation frontier.

---

## Roadmap Summary

The next phase is organized around five areas:

1. Form schema version migration
2. Event-driven actions and webhooks
3. Multi-tenant isolation and explicit sharing
4. Collaborative form editing
5. Bot protection for public submissions

Each item below includes the design decision, the intended architecture, the
implementation shape, and the operational trade-offs.

---

## 1. Form Schema Version Migration

### Design Decision

**Strategy chosen:** Schema isolation

### Problem Statement

Submitted `FormResponse` documents must remain bound to the exact form structure
that was active at submission time. Future changes to the live form should not
rewrite or invalidate historical responses.

### Target Behavior

- Draft edits modify only the active draft structure.
- Publishing a draft creates a new immutable version snapshot.
- Responses reference a specific form version identifier.
- Historical responses remain renderable even after the live draft evolves.

### Planned Data Model Changes

- Extend `Form` in `app/models/form.py` with draft/version tracking metadata.
- Store a static snapshot of the form structure in the `versions` list field.
- Ensure snapshots capture `sections`, `questions`, and `choices` as they exist
  at publish time.
- Add a `form_version_uuid` field to response records so each submission points
  at the exact version snapshot used for validation.

### Planned API Changes

- Update the form publish flow in `app/api/resources_forms.py`.
- On publish:
  - serialize the current draft layout
  - append a new immutable snapshot to the form version history
  - generate a unique version UUID
- On response submission:
  - require the version identifier
  - validate the response against the exact version snapshot

### Benefits

- Strong historical schema integrity
- Zero migration cost for older responses
- Better auditability for form evolution
- Safer long-term form editing

### Acceptance Criteria

- A published form creates a new immutable version snapshot.
- A stored response can always be resolved against the version active at submit time.
- Historical responses remain valid after later draft edits.

---

## 2. Event-Driven Actions & Webhooks

### Design Decision

**Message broker chosen:** Redis Streams / PubSub

### Problem Statement

Question-triggered actions, webhook dispatches, and external side effects should
not execute synchronously inside HTTP request threads.

### Target Behavior

- Endpoints enqueue action/webhook jobs instead of executing them inline.
- Background worker threads consume queued work asynchronously.
- Job results are recorded for observability and troubleshooting.
- Outbound webhooks are signed so downstream consumers can verify authenticity.

### Planned Worker Topology

- Keep the implementation aligned with the existing stack.
- Use a background worker thread model rather than introducing a heavyweight
  broker framework prematurely.
- Spawn the worker from the Flask application startup path so the worker is
  co-located with the service process.

### Planned Queueing Mechanism

- Push jobs to a Redis Stream, such as `tasks:events`.
- Consume jobs with `redis-py` stream reads (`xread` / `xreadgroup`).
- Separate job categories:
  - action executor jobs
  - webhook dispatcher jobs

### Planned Execution Handlers

- Action executor:
  - run external integrations defined on question actions
  - persist execution result metadata
- Webhook dispatcher:
  - POST JSON payloads to registered URLs
  - sign payloads using HMAC-SHA256
  - surface retry and failure outcomes

### Planned Persistence / Observability

- Record execution outcomes asynchronously in a log collection.
- Track job identifiers, timestamps, status, and error details.
- Expose enough state to reconstruct what happened after a failure or restart.

### Security Notes

- Use user-configured secrets for webhook signing.
- Reject spoofed payloads and tampered task metadata.
- Avoid leaking sensitive payload contents in logs.

### Acceptance Criteria

- Request handlers enqueue work instead of blocking on side effects.
- Workers process queued jobs independently of HTTP latency.
- Webhook payload integrity can be verified downstream.
- Execution results are durable enough to troubleshoot failures.

---

## 3. Multi-Tenant Database Isolation

### Design Decision

**Strategy chosen:** Permission-based logical isolation

### Problem Statement

The system must preserve organization-level privacy while still supporting
explicit cross-organization sharing when a workflow requires it.

### Target Behavior

- Query scopes are restricted to the user's active organization by default.
- Cross-tenant access is only granted when an explicit share exists.
- Sharing remains auditable and revocable.
- The database topology stays unified instead of fragmenting into per-tenant
  deployments.

### Planned Data Model Changes

- Add an `OrganizationShare` document in `app/models/user.py`.
- Fields:
  - `uuid`
  - `form_uuid`
  - `shared_with_org_uuid`
  - `role`
  - `created_at`
- Default share role should be restrictive, with expansion only when necessary.

### Planned RBAC Changes

- Update `app/services/rbac.py` to evaluate `OrganizationShare` records during
  permission checks.
- If the owning organization does not match the user’s organization:
  - look for a valid share record
  - grant access only when the share matches both the form and target org

### Planned API Changes

- Add share management routes in `app/api/resources_forms.py`:
  - `POST /api/v1/forms/<uuid>/share`
  - `DELETE /api/v1/forms/<uuid>/share/<org_uuid>`
- Ensure share creation and revocation are restricted to appropriate admins.

### Benefits

- Keeps storage and deployment simple
- Supports explicit collaboration between organizations
- Enables auditable, revocable access
- Avoids premature multi-database complexity

### Acceptance Criteria

- A user cannot access another organization’s form without an explicit share.
- Share creation and revocation are route-level operations with authorization.
- Permission behavior remains deterministic and testable.

---

## 4. Collaborative Form Design

### Design Decision

**Concurrency control chosen:** Pessimistic locking

### Problem Statement

Concurrent editors can collide when saving the same form or section structure.
This can produce lost updates or confusing client behavior.

### Target Behavior

- Editors acquire a lock before modifying a form.
- Locks expire automatically after a short inactivity window.
- Heartbeats extend the lock while the editor continues to work.
- Competing updates fail with a conflict response instead of silently clobbering
  the current draft.

### Planned Data Model Changes

- Add a MongoDB-backed `FormLock` document in `app/models/auth.py`.
- Fields:
  - `uuid`
  - `form_uuid`
  - `locked_by_user_uuid`
  - `created_at`
- Use a TTL index to expire stale locks automatically.

### Planned API Changes

- Add lock management endpoints in `app/api/resources_forms.py`:
  - `POST /api/v1/forms/<uuid>/lock`
  - `POST /api/v1/forms/<uuid>/lock/heartbeat`
  - `DELETE /api/v1/forms/<uuid>/lock`
- Update form modification routes to reject writes unless the requestor holds
  the active lock.

### Operational Notes

- TTL-based expiry protects against abandoned sessions.
- The lock should be short-lived and refreshable to minimize blocking.
- Lock ownership must be transparent in error responses so clients can explain
  why an update was rejected.

### Acceptance Criteria

- Only the lock holder can update a locked form.
- Expired locks release automatically.
- Clients can renew and release locks explicitly.

---

## 5. Bot Protection

### Design Decision

**Mechanism chosen:** Cryptographic proof-of-work using SHA-256 Hashcash

### Problem Statement

Public form submission endpoints need spam resistance without depending on a
third-party CAPTCHA provider.

### Target Behavior

- The backend issues a signed puzzle challenge.
- The client solves the challenge by searching for a valid nonce.
- The server verifies the challenge signature, expiration, and computed hash.
- Invalid or stale submissions fail with client-correctable validation errors.

### Planned Service Design

- Create `app/services/pow.py`.
- Challenge generation should include:
  - `salt`
  - `difficulty`
  - `expires_at`
  - `signature`
- Verification should:
  - validate the HMAC signature
  - reject expired puzzles
  - verify the hash prefix requirement

### Planned API Changes

- Add `GET /api/v1/pow-challenge`.
- Modify the public form response submission endpoint:
  - `POST /api/v1/projects/<uuid>/responses`
  - require both the challenge and solved nonce
- Return `400` or `422` when the proof-of-work is invalid.

### Security Notes

- Difficulty and expiry must be server-signed so the client cannot weaken the
  challenge.
- Keep the puzzle lightweight enough for real users but expensive enough to
  discourage automation.

### Acceptance Criteria

- Public submissions require a valid challenge/nonce pair.
- Challenge tampering is detected.
- Expired puzzles are rejected.
- The UX remains practical for normal users.

---

## Implementation Priorities

Recommended order for future work:

1. Event-driven actions and webhooks
2. Multi-tenant sharing
3. Form locking
4. Bot protection
5. Form schema version migration

That order favors improvements that reduce operational coupling and improve
runtime behavior before introducing deeper schema and submission changes.

---

## Open Questions To Resolve Before Implementation

- What exact events should enter the Redis stream?
- Which actions require retry semantics versus fire-and-forget behavior?
- Should shares apply to forms only, or also to nested resources?
- Should locks block read access, or only write access?
- What difficulty range is acceptable for proof-of-work on public submissions?

These questions should be answered before any implementation phase begins.
