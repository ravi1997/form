# Data Model

This document describes the main persisted entities in the backend and how they relate to each other.

## Overview

The system centers on a versioned form-authoring model:

- `projects` group related forms
- `forms` are the primary authored asset
- `commits` store the form version history
- `responses` store submissions and drafts
- `themes` store presentation metadata
- `users` and `organizations` define identity and tenancy
- `audit_logs` record operational history
- `idempotency_keys` prevent duplicate submission processing

## Collections

### organizations

Organization records define tenancy and org-level settings.

Typical fields:

- `_id`
- `name`
- `billing_plan`
- `settings.allowed_email_domains`
- `created_at`

### users

User records store identity, credentials, and roles.

Typical fields:

- `_id`
- `organization_id`
- `email`
- `password_hash`
- `first_name`
- `last_name`
- `roles`
- `status`
- `created_at`
- `updated_at`

### projects

Projects group forms and carry sharing metadata.

Typical fields:

- `_id`
- `organization_id`
- `name`
- `description`
- `deleted`
- `shares`
- `created_at`

### forms

Forms are the central authored asset in the system.

Typical fields:

- `_id`
- `organization_id`
- `project_id`
- `title`
- `description`
- `theme_id`
- `workflows`
- `block_script`
- `ab_testing`
- `start_date`
- `end_date`
- `max_submissions`
- `deleted`
- `shares`
- `current_version`
- `versions`
- `created_at`
- `updated_at`

### commits

Commits hold the version history for a form schema.

Typical fields:

- `_id`
- `form_id`
- `hash`
- `parent`
- `author_id`
- `message`
- `sections`
- `timestamp`
- optional `keep`

Each commit is linked to a form and forms a parent chain. Branch heads are stored on the form document, not in a separate branches collection.

### responses

Responses store submitted answers and draft updates.

Typical fields:

- `_id`
- `form_id`
- `version`
- `status`
- `organization_id`
- `submitted_at`
- `answers`
- `receipt_url`

Responses may be drafts or submitted records. Draft update flow lives in `PATCH /api/responses/<response_id>`.

### themes

Themes store visual configuration for forms.

Typical fields:

- `_id`
- `organization_id`
- `name`
- `active`
- `style`

### audit_logs

Audit logs capture operational events such as create, delete, share, publish, and submit actions.

These are useful for traceability, but they are not the source of truth for domain state.

### idempotency_keys

Idempotency keys are stored per organization and are used to suppress duplicate submission processing.

Typical fields:

- `key`
- `org_id`
- `response_data`
- `created_at`

## Relationships

- A `project` belongs to one `organization`
- A `form` belongs to one `project` and one `organization`
- A `form` can reference one `theme`
- A `form` can have many `commits`
- A `form` can have many `responses`
- A `response` belongs to one `form` and one `organization`
- A `user` belongs to one `organization`

## Versioning model

The versioning model is git-like, but it is implemented in MongoDB documents.

### Form versions

`forms.versions` stores published and draft schema snapshots at the form level.

### Commit history

`commits` stores schema evolution history with:

- a parent pointer
- the author
- the change message
- the full sections payload

### Branch heads

Branch pointers are stored inside the form document, typically under `vcs_branches`.

### Merge conflicts

Merge conflicts are represented inline in the merged schema as conflict marker objects rather than a separate conflict table.

## Tenant model

Tenant isolation is controlled by `TENANT_DB_ISOLATION`.

- `false`: all data lives in `DB_NAME`
- `true`: data is stored in `form_db_<organization_id>`

When per-tenant mode is enabled, the app chooses collections through `get_collections()`.

## Operational data

Not all persisted data is canonical domain state.

Operational or derived data includes:

- `audit_logs`
- `idempotency_keys`
- generated receipt artifacts
- exported CSV / JSON files
- runtime upload artifacts under `static/uploads/`

## Practical notes

- `commits` is the canonical source of form history.
- `responses` are mutable during draft editing.
- `forms.current_version` indicates the active published version.
- `forms.versions` and `commits` should be read together when reconstructing form history.

