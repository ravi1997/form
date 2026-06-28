# Unified Form Service

> A single-process, full-stack form platform combining a **Form Builder**, a **Response Gateway**, and a **Form Analyser** — all running on one Flask application backed by MongoDB and Redis.

[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-2.2%2B-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![MongoDB](https://img.shields.io/badge/MongoDB-4%2B-47A248?logo=mongodb&logoColor=white)](https://www.mongodb.com/)
[![Redis](https://img.shields.io/badge/Redis-4%2B-DC382D?logo=redis&logoColor=white)](https://redis.io/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Features](#features)
3. [Project Structure](#project-structure)
4. [Prerequisites](#prerequisites)
5. [Quick Start](#quick-start)
6. [Environment Variables](#environment-variables)
7. [API Endpoints](#api-endpoints)
   - [Health Check](#health-check)
   - [Builder — Authentication](#builder--authentication)
   - [Builder — Organisation & Users](#builder--organisation--users)
   - [Builder — Projects](#builder--projects)
   - [Builder — Forms](#builder--forms)
   - [Builder — Form Submissions & Responses](#builder--form-submissions--responses)
   - [Builder — Export](#builder--export)
   - [Builder — Version Control (VCS)](#builder--version-control-vcs)
   - [Builder — Workflows](#builder--workflows)
   - [Builder — Notifications & Admin](#builder--notifications--admin)
   - [Response Gateway — Forms](#response-gateway--forms)
   - [Response Gateway — Responses](#response-gateway--responses)
   - [Response Gateway — Sync](#response-gateway--sync)
   - [Analyser — Authentication & API Keys](#analyser--authentication--api-keys)
   - [Analyser — Analysis Definitions](#analyser--analysis-definitions)
   - [Analyser — Run & Cache](#analyser--run--cache)
   - [Analyser — Schedules](#analyser--schedules)
   - [Analyser — Result History & Comparison](#analyser--result-history--comparison)
   - [Analyser — Export](#analyser--export)
   - [Analyser — Background Jobs](#analyser--background-jobs)
   - [Analyser — Webhooks](#analyser--webhooks)
   - [Analyser — Forms Registry](#analyser--forms-registry)
   - [Analyser — Raw Responses](#analyser--raw-responses)
   - [Analyser — Schema Detection](#analyser--schema-detection)
8. [Running Tests](#running-tests)
9. [Docker Deployment](#docker-deployment)
10. [Seeding Demo Data](#seeding-demo-data)
11. [Contributing](#contributing)
12. [License](#license)

---

## Architecture Overview

```
┌───────────────────────────────────────────────────────────┐
│                    unified-form-service                    │
│                      app.py  (port 5000)                  │
│                                                           │
│  ┌─────────────────┐  ┌──────────────────┐  ┌──────────┐ │
│  │  Form Builder   │  │ Response Gateway │  │ Analyser │ │
│  │ builder_app.py  │  │  routes/         │  │blueprints│ │
│  │                 │  │  forms.py        │  │          │ │
│  │ /api/auth       │  │  responses.py    │  │/api/v1/  │ │
│  │ /api/org        │  │  sync.py         │  │ analysis │ │
│  │ /api/projects   │  │                  │  │ auth     │ │
│  │ /api/forms      │  │ /forms/ingest    │  │ forms    │ │
│  │ /api/themes     │  │ /forms/<id>/     │  │ webhooks │ │
│  │ /api/responses  │  │   responses      │  │ schema   │ │
│  └─────────────────┘  └──────────────────┘  └──────────┘ │
│                                                           │
│  Shared: MongoClient · Redis · APScheduler · JWT Auth     │
└───────────────────────────────────────────────────────────┘
           │                    │                │
      MongoDB               MongoDB            Redis
   form_builder_db        form_response      Cache + Queue
     form_analyser
```

`app.py` is the single entry point. It:

1. **Imports** `builder_app.py` (Flask `app` object with all builder routes already registered).
2. **Bootstraps** the Response Gateway by wiring `routes/` blueprints to the shared `app` instance.
3. **Registers** the Analyser blueprints from `blueprints/` against the same `app` instance.
4. **Starts** the APScheduler for recurring analysis jobs.
5. **Exposes** a consolidated `/healthz` endpoint covering all three sub-services.

All three sub-services share a single MongoDB client and optionally per-tenant database isolation.

---

## Features

| Feature | Description |
|---|---|
| **Form Builder** | Create projects, forms with sections/questions, multi-version publishing, and theming |
| **SurveyJS Integration** | Export any form as a SurveyJS-compatible JSON schema |
| **Advanced Validation** | Per-question type validation, conditional logic, pipeline rules |
| **Response Collection** | Validated form submission with idempotency, batch submit, draft/submit lifecycle |
| **PDF Receipts** | Generate PDF submission receipts for respondents |
| **Field Encryption** | AES-based encryption for sensitive form fields with DEK rotation |
| **Data Anonymisation** | Strip PII from response data on export |
| **JWT Authentication** | Token-based auth for Builder + org-scoped user roles (Admin/Editor/Analyst/Viewer) |
| **API Key Auth** | HMAC-hashed API keys for programmatic Analyser access |
| **Rate Limiting** | Redis-backed per-IP/per-route rate limiting |
| **Multi-Tenancy** | Org-scoped data isolation; optional database-per-org mode |
| **Version Control (VCS)** | Git-style commits, branches, diffs, merges, reverts, and tags for form schemas |
| **Schema Drift Detection** | Automatic detection of breaking structural changes across form versions |
| **Workflow Engine** | Trigger conditional pipelines (notifications, webhooks, scripts) on submission |
| **Analytics Engine** | 10+ step types: frequency, aggregate, top-N, crosstab, segment, missing, array_frequency, percentile, correlation, lookup |
| **Cron Scheduling** | Per-definition cron schedules via APScheduler; survive restarts |
| **Background Async Runs** | Offload analysis to Redis queue; poll job status endpoint |
| **Result Comparison** | Side-by-side diff of any two historical analysis runs |
| **Webhooks** | Generic, Slack, and Microsoft Teams webhook delivery on analysis events |
| **CSV / PDF Export** | Stream CSV or generate PDF from latest analysis result |
| **Schema Auto-Detection** | Scan a response collection and generate a ready-to-use analysis definition |
| **Structured JSON Logging** | All services emit structured JSON logs via `json_logger.py` |
| **Docker Ready** | Single `docker-compose up --build` brings up app + MongoDB + Redis |

---

## Project Structure

```
unified-form-service/
│
├── app.py                      # 🚀 Unified entry point — mounts all three sub-services
├── builder_app.py              # Form Builder Flask app + all /api/* builder routes
├── analyser_app.py             # Standalone analyser app (used in isolation)
│
├── blueprints/                 # Analyser Flask blueprints
│   ├── analysis_routes.py      # Analysis CRUD, run, schedule, results, compare, export
│   ├── auth_routes.py          # User registration, login, JWT, API key management
│   ├── form_routes.py          # Form registry — register, list, detail, run-all
│   ├── response_routes.py      # Raw form response read/write for analyser
│   ├── schema_routes.py        # Schema auto-detection and field listing
│   └── webhook_routes.py       # Webhook CRUD + test delivery
│
├── routes/                     # Response Gateway blueprints
│   ├── forms.py                # Form snapshot ingest and retrieval
│   ├── responses.py            # Response create, list, get, patch
│   └── sync.py                 # Sync a response to the analyser
│
├── models/
│   └── core.py                 # FormSnapshot, ResponseRecord dataclasses
│
├── repositories/               # In-memory + MongoDB response store abstraction
│
├── services/
│   └── analyser_adapter.py     # Bridge: Response Gateway → Analyser sync
│
├── validators/                 # Modular validation sub-packages
│
├── analysis_engine.py          # Core analytics executor (10+ step types)
├── analyser_auth.py            # API key hashing, JWT generation, auth decorators
├── auth.py                     # Builder AuthManager, login_required, roles_required
├── validator.py                # FormSubmissionValidator — per-type, conditional rules
├── pipeline_engine.py          # Workflow pipeline executor (conditions + actions)
├── workflow_engine.py          # Workflow state machine and run tracking
├── scheduler.py                # APScheduler integration — register/deregister cron jobs
├── redis_manager.py            # Redis cache helpers + async job queue
├── webhook_dispatcher.py       # HTTP webhook delivery (generic, Slack, Teams)
├── exporter.py                 # CSV streaming + PDF export from analysis results
├── receipt_generator.py        # PDF submission receipt generation
├── encryption_helper.py        # AES field encryption / DEK management / key rotation
├── anonymizer.py               # PII anonymisation helper
├── drift_detector.py           # Schema drift detection across form versions
├── schema_detector.py          # Auto-detect field types from response collection
├── git_version_control.py      # Git-style VCS: commits, branches, tags, diff, merge
├── surveyjs_translator.py      # Translate internal form schema → SurveyJS JSON
├── s3_helper.py                # S3/MinIO file upload helper
├── rate_limiter.py             # Redis-backed rate-limit decorator
├── metrics_manager.py          # Request metrics setup
├── task_manager.py             # Async export task tracking
├── db_init.py                  # MongoDB index initialisation
├── indexing.py                 # Auto-index fields referenced in analysis steps
├── config.py                   # Centralised config with environment loading
├── json_logger.py              # Structured JSON logging setup
│
├── seed_all.py                 # 🌱 Combined seeding script (builder + analyser)
├── seed.py                     # Builder-specific seed helper
├── seed_demo_data.py           # Analyser demo response seeder
│
├── test_response_gateway.py    # Gateway integration tests
├── test_exception_handling.py  # Exception handler tests
├── test_more_types.py          # Extended field-type tests
├── test_rate_limiter.py        # Rate limiter unit tests
│
├── Dockerfile                  # Production Docker image
├── docker-compose.yml          # App + MongoDB + Redis stack
├── requirements.txt            # Python dependencies
└── .env.example                # Environment variable template
```

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.12+ | Tested on 3.12 |
| MongoDB | 6+ | Or MongoDB Atlas |
| Redis | 6+ | Required for caching, rate limiting, async queue |
| Docker & Compose | Latest | Optional — for containerised deployment |
| pip | Latest | `pip install --upgrade pip` |

---

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/your-org/unified-form-service.git
cd unified-form-service
```

### 2. Configure environment

```bash
cp .env.example .env
# Open .env and set your MongoDB URI, Redis URL, and secret keys
```

At minimum, update these values in `.env`:

```env
MONGO_URI=mongodb://localhost:27017/
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=<your-random-secret>
JWT_SECRET=<your-random-jwt-secret>
```

### 3. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Start MongoDB and Redis (local)

```bash
# MongoDB
mongod --dbpath /data/db

# Redis
redis-server
```

### 5. Run the application

```bash
python app.py
```

The service is available at **http://localhost:5000**.

### 6. Seed demo data (optional)

```bash
python seed_all.py --all
```

See the [Seeding](#seeding-demo-data) section for individual flags.

### 7. Verify health

```bash
curl http://localhost:5000/healthz
```

```json
{
  "status": "ok",
  "services": {
    "builder": "running",
    "response_gateway": "running",
    "analyser": "running"
  }
}
```

---

## Environment Variables

All variables are documented in [`.env.example`](.env.example). The table below is a complete reference.

### Flask & Core

| Variable | Default | Description |
|---|---|---|
| `FLASK_ENV` | `development` | Flask environment (`development`, `production`, `testing`) |
| `FLASK_DEBUG` | `True` | Enable Flask debug mode |
| `SERVICE_NAME` | `form-response-service` | Instance identifier for the Response Gateway |

### Database & Cache

| Variable | Default | Description |
|---|---|---|
| `MONGO_URI` | `mongodb://localhost:27017/` | Primary MongoDB connection URI (shared by Builder & Analyser) |
| `DB_NAME` | `form_builder_db` | Form Builder database name |
| `MONGO_DB_NAME` | `form_analyser` | Form Analyser database name |
| `DATABASE_URL` | `mongodb://localhost:27017/form_response` | Response Gateway database URL |
| `RESPONSE_DATABASE_URL` | `mongodb://mongodb:27017/form_response` | Response Gateway URL (Docker override) |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |

### Security & Authentication

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | *(change me)* | Flask session signing secret |
| `JWT_SECRET` | *(change me)* | Builder JWT signing secret |
| `PASSWORD_SALT` | *(change me)* | Password hashing salt for Builder users |
| `SECRET_ENCRYPTION_KEY` | *(change me)* | Primary AES field encryption key |
| `SECRET_ENCRYPTION_KEYS` | *(change me)* | Comma-separated list of encryption keys (key rotation) |
| `REQUIRE_AUTH` | `false` | Guard Builder endpoints with JWT auth |
| `AUTH_ENABLED` | `True` | Guard Analyser endpoints with API key auth |

### Multi-Tenancy (Builder)

| Variable | Default | Description |
|---|---|---|
| `TENANT_DB_ISOLATION` | `false` | Enable database-per-organisation isolation |
| `ACTIVE_DB_LIMIT` | `5` | Max active tenant DB connections in pool |
| `DB_INACTIVE_TIMEOUT` | `300` | Idle timeout (seconds) before closing tenant connection |

### File Storage & S3

| Variable | Default | Description |
|---|---|---|
| `UPLOAD_FOLDER` | `static/uploads` | Local fallback upload directory |
| `S3_ENDPOINT_URL` | `http://localhost:9000` | S3/MinIO endpoint |
| `S3_ACCESS_KEY` | `minioadmin` | S3 access key |
| `S3_SECRET_KEY` | `minioadmin` | S3 secret key |
| `S3_BUCKET_NAME` | `form-uploads` | S3 bucket name |
| `S3_REGION_NAME` | `us-east-1` | S3 region |

### MongoDB Collections (Analyser)

| Variable | Default | Description |
|---|---|---|
| `FORMS_COLLECTION` | `forms` | Registered forms collection |
| `FORM_RESPONSES_COLLECTION` | `form_responses` | Raw form responses collection |
| `ANALYSIS_DEFINITIONS_COLLECTION` | `analysis_definitions` | Analysis definition documents |
| `ANALYSIS_RESULTS_COLLECTION` | `analysis_results` | Cached analysis run results |
| `API_KEYS_COLLECTION` | `api_keys` | Hashed API keys |
| `WEBHOOKS_COLLECTION` | `webhooks` | Webhook configurations |

### Integration

| Variable | Default | Description |
|---|---|---|
| `ANALYSER_SYNC_MODE` | `local` | Gateway → Analyser sync mode (`local` or `remote`) |

---

## API Endpoints

All responses follow a consistent envelope:

```json
{ "status": "success|error", "message": "...", "data": {...} }
```

Builder routes use `Bearer <JWT>` authentication. Analyser routes accept either a `Bearer <JWT>` (for role-based endpoints) or an `X-API-Key: <key>` header.

---

### Health Check

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/healthz` | None | Returns status of all three sub-services |

---

### Builder — Authentication

> Base path: `/api/auth`

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/auth/register` | None | Register a new user account |
| `POST` | `/api/auth/login` | None | Authenticate and receive a JWT |
| `POST` | `/api/auth/refresh` | JWT | Refresh an expiring JWT |
| `POST` | `/api/auth/reset-password` | JWT | Reset user password |

---

### Builder — Organisation & Users

> Base path: `/api/org`

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/org/users` | JWT | List all users in the organisation |
| `POST` | `/api/org/users` | JWT Admin | Invite / create a user in the organisation |
| `PATCH` | `/api/org/users/<user_id>` | JWT Admin | Update user profile or role |
| `DELETE` | `/api/org/users/<user_id>` | JWT Admin | Remove a user from the organisation |
| `PATCH` | `/api/org/lifecycle` | JWT Admin | Update organisation lifecycle status |
| `PATCH` | `/api/org/users/<user_id>/lifecycle` | JWT Admin | Update a user's lifecycle status |

---

### Builder — Projects

> Base path: `/api/projects`

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/projects` | JWT | Create a new project |
| `GET` | `/api/projects` | JWT | List all projects in the organisation |
| `GET` | `/api/projects/<project_id>` | JWT | Get project details |
| `DELETE` | `/api/projects/<project_id>` | JWT Admin | Delete a project |
| `GET` | `/api/projects/<project_id>/forms` | JWT | List all forms within a project |
| `POST` | `/api/projects/<project_id>/share` | JWT Admin | Share project with another user/email |
| `GET` | `/api/projects/<project_id>/shares` | JWT | List all project shares |
| `DELETE` | `/api/projects/<project_id>/share/<email>` | JWT Admin | Revoke a project share |

---

### Builder — Forms

> Base path: `/api/forms` · `/api/themes`

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/forms` | JWT | Create a new form (with sections, questions, workflows) |
| `GET` | `/api/forms/<form_id>` | JWT | Get full form definition |
| `DELETE` | `/api/forms/<form_id>` | JWT Admin | Delete a form |
| `POST` | `/api/forms/<form_id>/versions` | JWT | Save a new draft version of the form |
| `POST` | `/api/forms/<form_id>/publish` | JWT | Publish a form version (makes it live) |
| `GET` | `/api/forms/<form_id>/surveyjs` | JWT | Export form as SurveyJS-compatible JSON |
| `POST` | `/api/forms/<form_id>/share` | JWT Admin | Share form with user/email |
| `GET` | `/api/forms/<form_id>/shares` | JWT | List all form shares |
| `DELETE` | `/api/forms/<form_id>/share/<email>` | JWT Admin | Revoke a form share |
| `PATCH` | `/api/forms/<form_id>/lifecycle` | JWT Admin | Update form lifecycle state |
| `POST` | `/api/forms/<form_id>/debug` | JWT | Debug-run validation on a form without storing |
| `POST` | `/api/themes` | JWT Admin | Create a new UI theme |
| `GET` | `/api/themes` | JWT | List all themes |

---

### Builder — Form Submissions & Responses

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/forms/<form_id>/submit` | JWT / public | Submit a form response (with validation + pipeline) |
| `POST` | `/api/forms/<form_id>/submit-batch` | JWT | Submit multiple responses in one request |
| `GET` | `/api/forms/<form_id>/responses` | JWT Analyst+ | List all responses for a form |
| `GET` | `/api/responses/<response_id>` | JWT | Get a single response (with decryption for analysts) |
| `PATCH` | `/api/responses/<response_id>` | JWT | Update draft response answers or status |

---

### Builder — Export

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/forms/<form_id>/export/csv` | JWT Analyst+ | Stream responses as CSV |
| `GET` | `/api/forms/<form_id>/export/json` | JWT Analyst+ | Export responses as JSON |
| `POST` | `/api/forms/<form_id>/export/async` | JWT Analyst+ | Enqueue a background export task |
| `GET` | `/api/tasks/<task_id>` | JWT | Poll async export task status |

---

### Builder — Version Control (VCS)

> Git-style schema versioning per form.

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/forms/<form_id>/commit` | JWT | Commit current form schema as a named snapshot |
| `GET` | `/api/forms/<form_id>/commits` | JWT | List all commits for the form |
| `POST` | `/api/forms/<form_id>/resolve-conflicts` | JWT | Resolve merge conflicts and commit resolution |
| `POST` | `/api/forms/<form_id>/branches` | JWT | Create a new branch from a commit |
| `GET` | `/api/forms/<form_id>/branches` | JWT | List all branches |
| `GET` | `/api/forms/<form_id>/diff` | JWT | Diff two commits (`?from=<hash>&to=<hash>`) |
| `POST` | `/api/forms/<form_id>/merge` | JWT | Merge a branch into main |
| `POST` | `/api/forms/<form_id>/revert` | JWT | Revert to a specific commit |
| `POST` | `/api/forms/<form_id>/tags` | JWT | Tag a commit with a label |
| `GET` | `/api/forms/<form_id>/tags` | JWT | List all tags |
| `POST` | `/api/forms/<form_id>/commits/purge` | JWT Admin | Purge old commits |
| `PATCH` | `/api/forms/<form_id>/commits/<commit_hash>/keep` | JWT Admin | Mark a commit as permanent (exclude from purge) |

---

### Builder — Workflows

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/forms/<form_id>/workflows/runs` | JWT Analyst+ | List all workflow run records for a form |
| `GET` | `/api/forms/<form_id>/workflows/failed-runs` | JWT Analyst+ | List failed workflow runs |
| `POST` | `/api/forms/<form_id>/workflows/trigger` | JWT Editor+ | Manually trigger a workflow with a test payload |

---

### Builder — Notifications & Admin

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/notifications` | JWT | Get notifications for the current user |
| `PATCH` | `/api/notifications/<notification_id>/read` | JWT | Mark a notification as read |
| `POST` | `/api/admin/rotate-master-key` | JWT Admin | Rotate the master encryption key (re-encrypts all DEKs) |

---

### Response Gateway — Forms

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/forms/ingest` | JWT | Ingest a form snapshot into the gateway store |
| `GET` | `/forms/<form_id>` | JWT | Retrieve a form snapshot (optionally at `?version=<n>`) |

---

### Response Gateway — Responses

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/forms/<form_id>/responses` | JWT | Create a validated form response |
| `GET` | `/forms/<form_id>/responses` | JWT | List all responses for a form |
| `GET` | `/responses/<response_id>` | JWT | Retrieve a single response |
| `PATCH` | `/responses/<response_id>` | JWT | Update answers or status on a response |

---

### Response Gateway — Sync

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/sync/analyser` | JWT | Push a response to the analyser (for real-time sync) |

---

### Analyser — Authentication & API Keys

> Base path: `/api/v1/auth`

| Method | Path | Auth | Required Role | Description |
|---|---|---|---|---|
| `POST` | `/api/v1/auth/register` | None | — | Register an analyser user in an organisation |
| `POST` | `/api/v1/auth/login` | None | — | Authenticate and receive a JWT |
| `POST` | `/api/v1/auth/keys` | JWT | admin, analyst | Generate a new API key |
| `GET` | `/api/v1/auth/keys` | JWT | admin | List all API keys (hashed — plaintext never returned) |
| `DELETE` | `/api/v1/auth/keys/<key_id>` | JWT | admin | Revoke an API key |

---

### Analyser — Analysis Definitions

> Base path: `/api/v1/analysis`

| Method | Path | Auth | Required Role | Description |
|---|---|---|---|---|
| `POST` | `/api/v1/analysis` | JWT | admin, analyst | Create and store an analysis definition |
| `GET` | `/api/v1/analysis` | JWT | admin, analyst, viewer | List all definitions for the organisation |
| `GET` | `/api/v1/analysis/<id>` | JWT | admin, analyst, viewer | Get a single definition |
| `PUT` | `/api/v1/analysis/<id>` | JWT | admin, analyst | Replace / update a definition |
| `DELETE` | `/api/v1/analysis/<id>` | JWT | admin | Delete definition, schedule, and all result history |

---

### Analyser — Run & Cache

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/v1/analysis/run` | API Key | Run an ad-hoc definition from the request body (not stored) |
| `POST` | `/api/v1/analysis/<id>/run` | JWT (admin/analyst) | Run a stored definition. `?use_cache=true` returns cached result; `?async=true` queues the run |

---

### Analyser — Schedules

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/analysis/scheduled` | JWT (admin/analyst) | List all active cron-scheduled jobs |
| `POST` | `/api/v1/analysis/<id>/schedule` | API Key | Set or update the cron schedule for a definition |
| `DELETE` | `/api/v1/analysis/<id>/schedule` | API Key | Disable the cron schedule |

---

### Analyser — Result History & Comparison

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/analysis/<id>/results` | API Key | Paginated run history (`?limit=&skip=`) |
| `GET` | `/api/v1/analysis/<id>/results/latest` | API Key | Most recent cached result |
| `DELETE` | `/api/v1/analysis/<id>/results` | API Key | Clear all cached run results |
| `GET` | `/api/v1/analysis/<id>/results/compare` | API Key | Compare two specific runs: `?run_a=<id>&run_b=<id>` |
| `GET` | `/api/v1/analysis/<id>/results/compare/latest` | API Key | Auto-compare the two most recent runs |

---

### Analyser — Export

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/analysis/<id>/results/latest/export` | API Key | Export latest result as `?format=csv` (default) or `?format=pdf` |

---

### Analyser — Background Jobs

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/analysis/jobs/<job_id>` | API Key | Retrieve status of an async analysis task |

---

### Analyser — Webhooks

> Base path: `/api/v1/webhooks`

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/v1/webhooks` | API Key | Create a webhook (types: `generic`, `slack`, `teams`) |
| `GET` | `/api/v1/webhooks` | API Key | List all webhooks |
| `GET` | `/api/v1/webhooks/<id>` | API Key | Get one webhook |
| `PUT` | `/api/v1/webhooks/<id>` | API Key | Update webhook configuration |
| `DELETE` | `/api/v1/webhooks/<id>` | API Key | Delete a webhook |
| `POST` | `/api/v1/webhooks/<id>/test` | API Key | Fire a test payload to the webhook URL |

---

### Analyser — Forms Registry

> Base path: `/api/v1/forms`

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/v1/forms` | API Key | Register a form for analysis tracking |
| `GET` | `/api/v1/forms` | API Key | List all registered forms (with response & analysis counts) |
| `GET` | `/api/v1/forms/<form_id>` | API Key | Get form detail + linked analyses + latest run info |
| `DELETE` | `/api/v1/forms/<form_id>` | API Key | Delete a form registry entry (`?delete_analyses=true` cascades) |
| `POST` | `/api/v1/forms/<form_id>/run-all` | API Key | Run all analysis definitions linked to this form |

---

### Analyser — Raw Responses

> Base path: `/api/v1/responses`

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/v1/responses/` | API Key | List responses with pagination (`?limit=&skip=`) and field filter (`?field=&value=`) |
| `GET` | `/api/v1/responses/<id>` | API Key | Get a single response document |
| `POST` | `/api/v1/responses/` | API Key | Insert one or many raw response documents |

---

### Analyser — Schema Detection

> Base path: `/api/v1/schema`

| Method | Path | Auth | Required Role | Description |
|---|---|---|---|---|
| `POST` | `/api/v1/schema/detect` | JWT | admin, analyst | Scan a collection and return a suggested analysis definition JSON |
| `GET` | `/api/v1/schema/fields` | JWT | admin, analyst, viewer | List all detected fields with types and sample values |

---

## Running Tests

The project uses standard `unittest` / `pytest`. Run all tests:

```bash
pytest -v
```

Or run individual test modules:

```bash
# Response Gateway integration tests
python -m pytest test_response_gateway.py -v

# Exception handling tests
python -m pytest test_exception_handling.py -v

# Additional field-type tests
python -m pytest test_more_types.py -v

# Rate limiter tests
python -m pytest test_rate_limiter.py -v
```

> **Note:** Tests use `mongomock` for an in-memory MongoDB — no running database instance required for the test suite.

---

## Docker Deployment

A complete stack (app + MongoDB + Redis) is defined in [`docker-compose.yml`](docker-compose.yml).

### Build and start

```bash
docker-compose up --build
```

This brings up:

| Service | Port | Description |
|---|---|---|
| `app` | `5000` | Unified Form Service |
| `mongodb` | `27017` | MongoDB with persistent volume |
| `redis` | `6379` | Redis (Alpine) |

### Stop and remove containers

```bash
docker-compose down
```

### Stop and remove containers + volumes

```bash
docker-compose down -v
```

### Configuration overrides

Override any environment variable at runtime:

```bash
docker-compose up -e SECRET_KEY=my-prod-secret -e AUTH_ENABLED=True
```

Or create a `.env` file in the project root — Docker Compose will automatically load it.

### Dockerfile notes

The [`Dockerfile`](Dockerfile) builds a minimal production image. Ensure all secrets are supplied via environment variables or Docker secrets — **never bake credentials into the image**.

---

## Seeding Demo Data

[`seed_all.py`](seed_all.py) is the unified seeding script. It seeds both the Builder and Analyser databases with realistic demo data.

### Seed everything

```bash
python seed_all.py --all
```

### Seed only the Builder (themes, forms, organisations)

```bash
python seed_all.py --builder
```

### Seed only the Analyser (response data + analysis definitions)

```bash
python seed_all.py --analyser
```

### What gets seeded

**Builder:**
- A "Midnight Ocean" UI theme
- A demo organisation
- A demo admin user
- A sample multi-section form with various question types

**Analyser:**
- 500+ synthetic form responses with demographic and rating data
- A complete analysis definition (frequency, aggregate, top-N, crosstab steps)
- Results cached and ready for immediate inspection

---

## Contributing

1. **Fork** the repository and create your feature branch:
   ```bash
   git checkout -b feat/my-feature
   ```
2. **Commit** your changes with a clear message:
   ```bash
   git commit -m "feat: add my feature"
   ```
3. **Push** to your fork and open a **Pull Request** targeting `main`.

### Code style guidelines

- Follow **PEP 8** for Python code.
- Keep route handlers thin — business logic belongs in dedicated modules.
- Add docstrings to all new public functions and route handlers.
- Include tests for all new endpoints or non-trivial logic.
- Never commit secrets or credentials; always use environment variables.

### Reporting issues

Open a [GitHub Issue](https://github.com/your-org/unified-form-service/issues) with:
- A clear description of the problem
- Steps to reproduce
- Expected vs actual behaviour
- Relevant logs or error messages

---

## License

This project is licensed under the **MIT License**. See the [LICENSE](LICENSE) file for details.
