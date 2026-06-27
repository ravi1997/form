# Setup

## Prerequisites

- Python 3.12 or compatible
- MongoDB
- Optional: MinIO for local S3-compatible storage

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
docker compose up -d mongodb minio
python app.py
```

## Useful environment variables

- `REQUIRE_AUTH=true` to force auth checks in non-test runs
- `TENANT_DB_ISOLATION=true` to enable per-org databases
- `UPLOAD_FOLDER` to change the local artifact directory

## Verification

Run the focused tests that cover the most important flows:

```bash
python -m unittest test_auth_acl
python -m unittest test_vcs_lifecycles
python -m unittest test_app
```

