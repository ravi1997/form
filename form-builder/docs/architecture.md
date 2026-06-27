# Architecture Overview

This repository is a backend service for building, versioning, and submitting forms.

## Layers

### Transport layer

- `app.py` defines the Flask application and HTTP routes.
- It handles request parsing, response serialization, auth context, and route-level permission checks.

### Auth layer

- `auth.py` implements password hashing, JWT token generation, token verification, and decorators.
- Access and refresh tokens are distinct via `token_type`.

### Versioning layer

- `git_version_control.py` manages commit-like history for forms.
- It supports commits, branches, diffs, merges, and purge retention.

### Validation layer

- `validator.py` validates submissions, required fields, conditional logic, and computed values.

### Translation layer

- `surveyjs_translator.py` converts the internal schema into SurveyJS-compatible structures.

### Workflow layer

- `pipeline_engine.py`, `workflow_engine.py`, and `task_manager.py` handle asynchronous and rule-driven processing.

### Storage layer

- `s3_helper.py` handles S3-compatible uploads.
- `pdf_generator.py` produces receipt artifacts and uploads them.

## Core domain model

- `projects` contain forms.
- `forms` are the primary authored asset.
- `commits` store form history and version snapshots.
- `responses` store submissions and drafts.
- `themes` store appearance settings.

## Tenant model

- Default mode uses a shared MongoDB database.
- When `TENANT_DB_ISOLATION=true`, the app switches to one database per organization.
- Index creation and freezing are managed in `app.py`.

## Primary risks to watch

- Merge conflicts in form and response editing
- Token misuse between access and refresh flows
- Runtime artifact accumulation in `static/uploads/`
- Cold-start latency after tenant DB reactivation

