# Changelog

All notable changes to the **Unified Form Service** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Conventional Commits](https://www.conventionalcommits.org/).

Entries are grouped by release milestone. Since the project was unified from three
separate services into a single Flask application, all changes are tracked from the
point of unification onwards.

---

## [Unreleased]

> Changes that are merged to `main` but not yet tagged as a release.

---

## [1.5.0] — 2026-06-28

### Chore
- **Remove tracked `__pycache__` binaries** and add `.gitignore` rules to exclude
  compiled Python bytecode from version control going forward.
  *(commit `e35ed40`)*

### Added
- **`seed_all.py`** — unified seeding command that combines Form Builder and
  Form Analyser data seeding into a single entrypoint. Replaces the need to run
  `seed.py` and `seed_demo_data.py` individually.
  *(commit `7b5c737`)*

---

## [1.4.0] — 2026-06-28

### Added
- **Centralised JSON error handler** (`error_handling`) — a single error handler
  now manages all HTTP exceptions and database errors, returning consistent JSON
  error responses across all services. Previously each sub-service handled errors
  independently.
  *(commit `ba82f83`)*

- **Unified rate limiting** (`rate_limiter.py`) — Redis-backed rate limiter with
  automatic in-memory fallback. Applied uniformly across submission and
  authentication endpoints. Replaces ad-hoc per-service rate limiting.
  *(commit `f5a4478`)*

### Style
- **Uploads directory** added to `.gitignore` — the `uploads/` directory is now
  fully ignored to prevent generated receipts and uploaded files from being
  tracked.
  *(commit `62b6f63`)*

---

## [1.3.0] — 2026-06-28

### Refactored
- **Shared MongoDB connection** (`database`) — replaced per-service `MongoClient`
  instantiation with a single shared client across all services. Eliminates
  connection pool exhaustion under load and removes redundant `MONGO_URI` parsing
  scattered throughout the codebase.
  *(commit `75136e3`)*

---

## [1.2.0] — 2026-06-28

### Added
- **Structured JSON logging** (`json_logger.py`) — unified logging across all
  three services (builder, gateway, analyser). All log output is now machine-readable
  JSON, enabling easy ingestion by log aggregators (e.g., Datadog, ELK).
  *(commit `d3166ff`)*

- **Consolidated environment template** (`.env.example`) — all environment variables
  from the three previously separate services are merged into a single
  `.env.example` file with inline documentation for each variable group:
  Flask core, database & cache, auth, analyser, S3/email, and service URLs.
  *(commit `02ca8c4`)*

---

## [1.1.0] — 2026-06-28

### Added
- **Consolidated validation engine** (`validation`) — the Form Builder's field
  validator and the Response Gateway's payload validator are merged into a single
  `validator.py` module. Downstream services import from one canonical location.
  *(commit `98f7895`)*

- **Unified JWT & API-key authentication** (`auth.py`) — JWT bearer token and
  `x-api-key` header authentication are now handled by a single `auth.py` module
  used by all blueprints. Eliminates the previously duplicated auth logic between
  `builder_app.py` and the response gateway.
  *(commit `604cc5f`)*

### Refactored
- **UTC datetime modernisation** (`datetime`) — replaced deprecated
  `datetime.utcnow()` calls with timezone-aware `datetime.now(timezone.utc)`
  throughout the codebase, in preparation for Python 3.12+ compatibility.
  *(commit `4d55135`)*

---

## [1.0.0] — 2026-06-28  *(Unification Release)*

This is the foundational release in which three previously independent microservices
were merged into a single, cohesive Flask application (`unified-form-service`).

### Added
- **Unified Flask application** (`app.py`) — single entry point that registers
  blueprints for the Form Builder, Response Gateway, and Form Analyser.
  *(commit `8f1bac1`)*

- **Unified Dockerfile & `docker-compose.yml`** — single container build for
  the combined service with a `docker-compose.yml` that provisions MongoDB and
  Redis alongside the app.
  *(commit `f8ba6ff`)*

- **Database seeding scripts** included in the unified service — `seed.py`
  (builder data) and `seed_demo_data.py` (analyser data) are bundled with the
  unified service.
  *(commit `53621c3`)*

### Performance
- **Analyser sync optimisation** — in the unified app context, the analyser sync
  path now inserts data directly into the database rather than going through HTTP.
  Removes the latency and reliability overhead of an internal HTTP round-trip.
  *(commit `3f32387`)*

---

## [0.3.0] — 2026-06-28  *(Pre-unification: Form Builder fixes)*

### Fixed
- **Form Builder** (`form-builder`):
  - Added support for synchronous and asynchronous batch submissions.
  - Enabled comparison operators (`<`, `>`, `<=`, `>=`, `!=`) in
    `SafeFormulaEvaluator` — previously only equality was supported.
  - Isolated test environments to prevent test runs from polluting the
    development database.
  *(commit `0b982b3`)*

---

## [0.2.0] — 2026-06-28  *(Pre-unification: Response Gateway refactor)*

### Refactored
- **Form Response Gateway** (`form-response`):
  - Standardised exclusively on MongoDB — removed the SQLite dependency that had
    been left over from the initial prototype.
  - Secured all endpoints with authentication middleware.
  - Replaced the stub HTTP sync with a real HTTP call to the analyser service.
  *(commit `f234a8b`)*

---

## [0.1.0] — 2026-06-27  *(Initial implementation)*

### Added
- **Forms & Responses API endpoints** — initial implementation of:
  - `POST /forms` — form ingestion endpoint.
  - `GET /forms/<id>` — retrieve a form by ID.
  - `POST /responses` — submit answers to a form.
  - `PATCH /responses/<id>` — partial update of a response.
  - `GET /responses/<id>` — retrieve a response.
  - `POST /sync` — push response data to the external analyser service.
  - Unit tests covering persistence of forms and responses.
  *(commit `a40f0d4`)*

- **Receipt cleanup** — removed obsolete HTML receipt files from the
  `uploads/` directory left over from an earlier prototype.
  *(commit `d7fd6f0`)*

---

## [0.0.1] — 2026-06-26  *(First commit)*

- Initial repository scaffolding: project structure, base modules for
  `form-builder`, `form-response`, and `form-analyser` sub-services.
  *(commit `5f71898`)*

---

<!-- Links -->
[Unreleased]: https://github.com/your-org/form/compare/v1.5.0...HEAD
[1.5.0]: https://github.com/your-org/form/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/your-org/form/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/your-org/form/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/your-org/form/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/your-org/form/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/your-org/form/compare/v0.3.0...v1.0.0
[0.3.0]: https://github.com/your-org/form/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/your-org/form/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/your-org/form/compare/v0.0.1...v0.1.0
[0.0.1]: https://github.com/your-org/form/releases/tag/v0.0.1
