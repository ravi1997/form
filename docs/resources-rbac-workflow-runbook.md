# Resources RBAC and Workflow Runbook

## Scope

This runbook covers:

- Project/Form/Section/Question/Choice resources routes under `/api/v1`
- Route-level RBAC authorization and failure handling
- Workflow actions for submit, review, and approve
- Security and audit operational checks

## Key Configuration

- `RESOURCE_RATE_LIMIT_MAX`
- `RESOURCE_RATE_LIMIT_WINDOW_SECONDS`
- `RESOURCE_RBAC_REQUIRE_ORG_ROLE_ALIGNMENT`
- `WORKFLOW_STRICT_REVIEW_BEFORE_APPROVE`
- `ENABLE_AUDIT_LOGS`
- `REQUEST_ID_HEADER`

Validate effective values with `GET /api/v1/auth/admin/config/health`.

## Permission Matrix (High Level)

- `project_read`: view project and nested resources
- `project_write`: create/update forms, sections, questions, choices
- `project_admin`: destructive and version-admin operations
- `project_submit`: `POST /projects/<project_uuid>/forms/<form_uuid>/workflow/submit`
- `project_review`: `POST /projects/<project_uuid>/forms/<form_uuid>/workflow/review`
- `project_approve`: `POST /projects/<project_uuid>/forms/<form_uuid>/workflow/approve`
- `global_admin`: create project and admin-only auth endpoints

## Workflow State Machine

Primary states:

- `draft`
- `submitted`
- `in_review`
- `approved`
- `rejected`

Action behavior:

- `submit`: usually `draft|rejected -> submitted`
- `review`: requires reviewer workflow, usually `submitted -> in_review`
- `approve`: requires approver workflow, usually `in_review -> approved` when strict review is enabled

Idempotency:

- Repeating an already satisfied action returns success semantics with an idempotent message.

Transition guards:

- Invalid transitions return HTTP 409.
- Guard failures are logged as `resources_security_event` entries with `reason`.

## Security Event Reference

Resources API logs structured events with:

- `event`
- `outcome`
- `endpoint`
- `path`
- `method`
- `actor_user_uuid`
- `reason`
- `request_id`

Common events:

- `resources_rate_limit`
- `resources_auth`
- `resources_rbac`
- `resources_workflow_submit`
- `resources_workflow_review`
- `resources_workflow_approve`

## Incident Playbook

### 401 Unauthorized spikes

1. Check token rotation and signer keys.
2. Validate `Authorization` header format (`Bearer <token>`).
3. Confirm session revocation activity from auth audit logs.

### 403 Forbidden spikes

1. Filter `resources_security_event` where `event=resources_rbac` and `outcome=forbidden`.
2. Group by `reason` and target endpoint.
3. Confirm user project membership and org-role alignment.
4. If `RESOURCE_RBAC_REQUIRE_ORG_ROLE_ALIGNMENT=true`, verify user org roles include required values for assignment tier.

### 409 Workflow conflicts

1. Filter workflow events with `outcome=rejected`.
2. Inspect transition pair (`transition_from`, `transition_to`) in form workflow history.
3. Verify strict mode expectations (`WORKFLOW_STRICT_REVIEW_BEFORE_APPROVE`).

### 429 Throttling spikes

1. Check `resources_rate_limit` events and `retry_after` values.
2. Verify edge/proxy source IP forwarding behavior.
3. Tune `RESOURCE_RATE_LIMIT_MAX` and `RESOURCE_RATE_LIMIT_WINDOW_SECONDS` if required.

## Query Examples

Use request-id correlation:

- Search app logs for `request_id=<value>`
- Cross-check with auth events using the same request ID

Filter by actor:

- `actor_user_uuid=<user_uuid>` across resources and auth streams

## Recovery and Rollback Guidance

- To relax workflow constraints quickly, set `WORKFLOW_STRICT_REVIEW_BEFORE_APPROVE=false`.
- To disable project membership/org alignment enforcement temporarily, set `RESOURCE_RBAC_REQUIRE_ORG_ROLE_ALIGNMENT=false`.
- Keep changes time-bound and record change ticket + rollback target time.
