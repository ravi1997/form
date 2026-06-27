# API Guide

This document shows representative request and response shapes for the main backend endpoints.

## Auth

### Register

`POST /api/auth/register`

Request:

```json
{
  "email": "owner@company.com",
  "password": "securepassword123",
  "first_name": "Alice",
  "last_name": "Smith",
  "organization_name": "Alice Industries",
  "allowed_email_domains": ["company.com"]
}
```

Response:

```json
{
  "message": "User registered successfully",
  "access_token": "jwt...",
  "refresh_token": "jwt...",
  "user": {
    "id": "user_id",
    "email": "owner@company.com",
    "first_name": "Alice",
    "last_name": "Smith",
    "roles": ["Admin"]
  },
  "organization": {
    "id": "org_id",
    "name": "Alice Industries"
  }
}
```

### Login

`POST /api/auth/login`

Request:

```json
{
  "email": "owner@company.com",
  "password": "securepassword123"
}
```

Response:

```json
{
  "message": "Login successful",
  "access_token": "jwt...",
  "refresh_token": "jwt...",
  "user": {
    "id": "user_id",
    "email": "owner@company.com",
    "first_name": "Alice",
    "last_name": "Smith",
    "roles": ["Admin"]
  },
  "organization": {
    "id": "org_id",
    "name": "Alice Industries"
  }
}
```

### Refresh

`POST /api/auth/refresh`

Request:

```json
{
  "refresh_token": "jwt..."
}
```

Response:

```json
{
  "access_token": "jwt...",
  "refresh_token": "jwt..."
}
```

## Projects

### Create project

`POST /api/projects`

Request:

```json
{
  "name": "Research Program",
  "description": "Internal survey program"
}
```

Response:

```json
{
  "_id": "project_id",
  "organization_id": "org_id",
  "name": "Research Program",
  "description": "Internal survey program",
  "deleted": false,
  "shares": [],
  "created_at": "2026-06-27T12:00:00"
}
```

## Forms

### Create form

`POST /api/forms`

Request:

```json
{
  "project_id": "project_id",
  "title": "Customer Feedback",
  "description": "Quarterly feedback form",
  "questions": [
    {
      "id": "q_satisfaction",
      "type": "multiple_choice",
      "title": "How satisfied are you?"
    }
  ]
}
```

Response includes the initial version history:

```json
{
  "_id": "form_id",
  "title": "Customer Feedback",
  "current_version": 1,
  "versions": [
    {
      "version_number": 1,
      "published": true,
      "sections": [
        {
          "id": "default_section",
          "title": "General",
          "questions": []
        }
      ]
    }
  ]
}
```

### Publish a version

`POST /api/forms/<form_id>/publish`

Request:

```json
{
  "version_number": 2
}
```

Response:

```json
{
  "message": "Version 2 is now active"
}
```

## Versioning

### Create commit

`POST /api/forms/<form_id>/commit`

Request:

```json
{
  "branch": "main",
  "message": "Initial schema",
  "sections": [
    {
      "id": "s1",
      "questions": [
        {
          "id": "q1",
          "type": "text",
          "title": "First question"
        }
      ]
    }
  ]
}
```

Typical response:

```json
{
  "commit_hash": "abc123...",
  "branch": "main"
}
```

### Create branch

`POST /api/forms/<form_id>/branches`

Request:

```json
{
  "branch_name": "feature-1",
  "source_branch": "main"
}
```

### Merge branches

`POST /api/forms/<form_id>/merge`

Request:

```json
{
  "source_branch": "feature-1",
  "target_branch": "main"
}
```

Response can include conflict metadata:

```json
{
  "merged": true,
  "type": "fast_forward",
  "commit_hash": "abc123...",
  "conflicts": []
}
```

## Responses

### Submit

`POST /api/forms/<form_id>/submit`

Request:

```json
{
  "q_satisfaction": "Very Satisfied",
  "status": "Submitted"
}
```

Response:

```json
{
  "message": "Response processed successfully",
  "response": {
    "_id": "response_id",
    "form_id": "form_id",
    "status": "Submitted",
    "answers": {
      "q_satisfaction": "Very Satisfied"
    }
  }
}
```

### Update draft response

`PATCH /api/responses/<response_id>`

Request:

```json
{
  "status": "Draft",
  "base_answers": {
    "q1": "old value"
  },
  "answers": {
    "q1": "new value"
  }
}
```

If there is a merge conflict, the API returns `409 Conflict`.

## Exports

### Export CSV

`GET /api/forms/<form_id>/export/csv`

Returns a CSV download of responses.

### Export JSON

`GET /api/forms/<form_id>/export/json`

Returns a JSON list of responses.

## Workflows

### Trigger workflows

`POST /api/forms/<form_id>/workflows/trigger`

This endpoint triggers configured workflows for a form.

### Inspect workflow runs

`GET /api/forms/<form_id>/workflows/runs`

Returns recent workflow execution runs and their step status.

## Health

### Health check

`GET /api/health`

Use this as a basic liveness check.

## Notes

- Authenticated routes expect `Authorization: Bearer <access_token>`.
- Refresh endpoints require a refresh token, not an access token.
- Some routes enforce additional `roles_required(...)` checks.
- `static/uploads/` may contain generated receipt files and uploaded artifacts when local fallback storage is used.

