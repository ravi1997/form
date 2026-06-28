# Form Response Service

Backend-only service for storing minimal form snapshots, validating responses, and
bridging response data to the analyser service.

## Scope

This service is intentionally narrow:

- ingest form JSON from the form-builder project
- persist the minimum snapshot needed to validate responses
- accept, update, retrieve, and lifecycle-manage responses
- expose an isolated analyser sync adapter
- document the storage-to-analyser transformation

It does not implement form authoring, auth, branching, publishing, workflows,
receipts, uploads, exports, or analyser logic.

## Contract boundary

Expected builder input:

- form `id`
- `title`
- `description`
- `sections`
- `questions`
- per-question validation metadata

Expected analyser output:

- `form_id`
- `response_id`
- `status`
- `submitted_at`
- normalized `answers`
- stored `form_snapshot_version`

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

Or use the standard library test runner:

```bash
python -m unittest discover -s tests -v
```

## Run locally

```bash
flask --app wsgi:app run --debug
```

The service stores data in MongoDB by default. Set `DATABASE_URL` to point at a different
connection string if needed.

## Bootstrap

Initialize or verify the MongoDB database indexes explicitly:

```bash
python bootstrap.py
```

This will connect to the MongoDB instance and initialize the forms and responses collections and indexes.

The bootstrap step is idempotent. Running it multiple times only reasserts the collections and indexes.

## Health check

The app exposes a simple readiness endpoint:

```bash
GET /healthz
```

It returns whether the MongoDB database is reachable and indexes are ready.

## Container run

```bash
docker compose up --build
```

The container uses `mongodb://host.docker.internal:27017/form_response` by default.

## API

- `POST /forms/ingest`
- `GET /forms/<form_id>`
- `POST /forms/<form_id>/responses`
- `GET /forms/<form_id>/responses`
- `GET /responses/<response_id>`
- `PATCH /responses/<response_id>`
- `POST /sync/analyser`
