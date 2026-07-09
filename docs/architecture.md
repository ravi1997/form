# Architecture

## Application flow

1. Requests enter Flask through the WSGI app in `app/wsgi.py`.
2. `create_openapi_app()` in `app/openapi.py` applies configuration, middleware, logging, Celery integration, and route registration.
3. Route handlers live in `app/api/` and are intentionally thin.
4. Business logic lives in `app/services/`.
5. Persistent state is stored in MongoDB through MongoEngine models in `app/models/`.
6. Async condition work is dispatched to Celery using Redis as broker/result backend.

## Code layout

- `app/config.py` handles environment parsing, runtime settings, and validation
- `app/api/` contains blueprints and route modules
- `app/middleware/` handles request IDs, observability, and rotating request logging
- `app/models/` defines MongoEngine documents
- `app/schemas/` defines request/response models
- `app/services/` contains auth, RBAC, rate limiting, condition evaluation, and logging services
- `app/celery/` contains Celery app setup, signals, tasks, and worker entry points

## Request middleware

- Request IDs are propagated via the configured header, defaulting to `X-Request-Id`
- Observability middleware records request metrics and security headers
- Rotating logger middleware writes structured request/response logs to disk

## Data and async jobs

- MongoDB is the system of record for users, sessions, forms, conditions, rate-limit state, and audit data
- Redis is used for Celery transport and result storage
- Celery workers run inside the Flask application context through a custom task base
- Condition monitoring snapshots are retained with a MongoDB TTL index
