# Database Models

MongoDB is accessed through MongoEngine documents in `app/models/`.

## User and auth collections

### `app/models/user.py`

- `User`
- `Organization`

Users store:

- UUID, name, email, phone, designation
- auth provider and password hash
- flags such as `is_super_admin`, `is_organisation_admin`, and `must_change_password`
- per-organization role mappings
- organization references and last-login timestamps

### `app/models/auth.py`

- `UserSession`
- `RateLimitCounter`
- `SessionAuditLog`
- `TokenBlocklist`

These collections store:

- active JWT session state
- auth endpoint counters
- session audit trails
- revoked refresh-token JTIs and hashes

## Form/resource collections

### `app/models/form.py`

Main documents include:

- `Project`
- `Form`
- `Section`
- `Question`
- `Choice`
- `Condition`
- `FormResponse`
- `ActionExecution`
- `Version`

Important behaviors:

- Projects contain forms
- Forms contain sections
- Sections contain questions
- Questions can contain choices and action definitions
- Forms and responses support workflow state transitions
- Conditions support nested logical trees and approval states

## Condition-management collections

### `app/models/condition_management.py`

- `ConditionPreset`
- `ConditionPresetVersion`
- `ConditionVersion`
- `ConditionApprovalAudit`
- `ConditionAsyncJob`
- `ConditionEvaluationStat`

These collections power:

- preset management
- version history
- approval audit
- async job tracking
- evaluation analytics

## Rate-limit collections

### `app/models/rate_limit.py`

- `RateLimitConfig`
- `RateLimitLog`

They store:

- scope-specific configuration
- per-route limits
- audit logs for rate-limit decisions

## UI template collections

### `app/models/ui_template.py`

- `ThemeTemplate`
- `LayoutTemplate`
- `TemplateRevision`

Templates track:

- scope, visibility, status
- admins/editors/viewers
- revision history
- current published revision
- usage count

## Schema/collection notes

- The codebase uses document collections rather than relational migrations
- Most models define explicit indexes through MongoEngine `meta`
- Several documents use TTL indexes for expiration/retention behavior
