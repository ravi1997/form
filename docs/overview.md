# Overview

Form Service API is a production-oriented backend for managing form hierarchies, user sessions, condition evaluation, and operational workflows.

## What it does

- Exposes OpenAPI-backed HTTP endpoints under `/api/v1`
- Authenticates users with short-lived access tokens and long-lived refresh tokens
- Stores application state in MongoDB via MongoEngine
- Executes async condition work through Celery workers using Redis
- Tracks rate limits, request IDs, metrics, and structured logs

## Main domains

- Auth: user registration, login, refresh, logout, sessions, and admin flows
- Resources: projects, forms, sections, questions, choices, and actions
- Conditions: testing, batching, cache metrics, presets, versioning, approval, and async evaluation
- System: health, liveness, readiness, metrics, and schema echo routes
- UI templates: template CRUD for layout/theme configuration

## Runtime components

- `app.wsgi:app` is the WSGI entry point
- `app.openapi:create_openapi_app()` builds the Flask/OpenAPI application
- `app.celery.worker` provides the Celery worker app
- `docker-compose.yml` runs API, MongoDB, Redis, worker, and optional beat
