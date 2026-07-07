# Role Assignment Source of Truth

## Purpose

This document defines role assignment expectations used by resources RBAC checks and project membership validation.

## Organization Role Model

User organization roles are stored per organization key. Allowed role labels in this project are:

- `admin`
- `editor`
- `viewer`

## Project Membership Tiers

Project membership lists map to minimum organization-role expectations when `RESOURCE_RBAC_REQUIRE_ORG_ROLE_ALIGNMENT=true`.

- `project.admins`: user must hold `admin` in at least one project organization
- `project.members`: user must hold `admin` or `editor` in at least one project organization
- `project.viewers`: user must hold `admin`, `editor`, or `viewer` in at least one project organization

If project membership lists are populated while project organizations are empty, create/update is rejected.

## Workflow Capability Roles

Form workflow role lists are evaluated in project context:

- Submit flow: `submitter`
- Review flow: `reviewer`
- Approve flow: `approver`

These are additional capabilities and do not replace project read/write/admin membership checks.

## API Enforcement Points

Enforcement currently occurs in:

- Project create/update for membership role alignment
- Central resources route authorization middleware
- Workflow submit/review/approve endpoints

## Operational Guidance

- Apply org role updates before project membership updates to avoid temporary drift.
- Keep project organizations in sync with intended assignment scope.
- For migrations, if drift exists, temporarily set `RESOURCE_RBAC_REQUIRE_ORG_ROLE_ALIGNMENT=false`, reconcile, then re-enable.

## Audit Expectations

Forbidden and rejected attempts produce structured security events containing:

- `actor_user_uuid`
- `endpoint`
- `reason`
- `request_id`

Use these fields to trace assignment drift and unauthorized workflow attempts.
