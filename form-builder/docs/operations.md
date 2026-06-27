# Operations Runbook

This document covers the common operational tasks for the backend.

## Services

The default local stack is defined in `docker-compose.yml`:

- `mongodb` on port `27017`
- `minio` on ports `9000` and `9001`
- `web` on port `5000`

## Local bootstrap

1. Copy `.env.example` to `.env`
2. Install dependencies with `make install`
3. Start dependencies:

```bash
docker compose up -d mongodb minio
```

4. Initialize collection indexes:

```bash
make init-db
```

5. Start the app:

```bash
make run
```

## Database initialization

`db_init.py` creates the baseline indexes for:

- `projects`
- `forms`
- `themes`
- `responses`
- `commits`

Use this after first setup or after recreating the local MongoDB volume.

## Storage behavior

`s3_helper.py` uses S3-compatible object storage when credentials are present.

- If `S3_ACCESS_KEY` and `S3_SECRET_KEY` are set, files are uploaded to S3 or MinIO.
- If credentials are missing, the helper falls back to local files under `static/uploads/`.
- Generated receipts and uploaded artifacts may appear there during local development.

## Tenant isolation

When `TENANT_DB_ISOLATION=true`:

- data is stored in `form_db_<organization_id>`
- `get_collections()` selects the tenant database dynamically
- index creation/freeze behavior is managed in `app.py`

## Common commands

```bash
make test
make test-auth
make test-vcs
make test-app
```

## Cleanup

To remove local runtime artifacts from the working tree:

```bash
make clean
```

This removes:

- `__pycache__` directories
- files under `static/uploads/`

## Troubleshooting

### MongoDB connection problems

- Confirm `MONGO_URI` matches the running container or host
- Check that `mongodb` is healthy and reachable on port `27017`

### MinIO / S3 upload issues

- Confirm `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, and `S3_BUCKET_NAME`
- If credentials are absent, local fallback storage should be used instead

### Auth failures

- Access routes expect `Authorization: Bearer <access_token>`
- Refresh routes require the `refresh_token` payload field
- `REQUIRE_AUTH=true` forces auth checks outside test mode

### Tenant DB spikes after inactivity

- The code currently freezes inactive tenant indexes to save memory
- First requests after inactivity may be slower while indexes are rebuilt

## Verification checklist

- `make init-db`
- `make test-auth`
- `make test-vcs`
- `make test-app`

