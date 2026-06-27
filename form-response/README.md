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

The service stores data in SQLite by default. Set `DATABASE_URL` to point at a different
local file if needed.

## Bootstrap

Initialize or verify the SQLite schema explicitly:

```bash
python bootstrap.py
```

This will create the parent directory for `DATABASE_URL`, initialize tables, and
ensure the file is writable before app startup.

The bootstrap step is idempotent. Running it multiple times only reasserts the schema
and indexes.

## Health check

The app exposes a simple readiness endpoint:

```bash
GET /healthz
```

It returns whether the SQLite database can be opened and queried.

## Container run

```bash
docker compose up --build
```

The container uses `sqlite:///data/form_response.db` by default, so the database file
is mounted on a volume and survives restarts.

## API

- `POST /forms/ingest`
- `GET /forms/<form_id>`
- `POST /forms/<form_id>/responses`
- `GET /forms/<form_id>/responses`
- `GET /responses/<response_id>`
- `PATCH /responses/<response_id>`
- `POST /sync/analyser`
