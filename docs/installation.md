# Installation

## Prerequisites

- Python 3.13+
- MongoDB 6+
- Redis 7+ for Celery and distributed rate limiting
- Docker and Docker Compose if you plan to run the full stack locally

## Local install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-test.txt
cp .env.example .env
```

After copying `.env.example`, set at least:

- `JWT_SECRET_KEY`
- `MONGO_INITDB_ROOT_PASSWORD`

For a pure local Python run, `MONGODB_URI` can point to a local MongoDB
instance and `CELERY_BROKER_URL` can point to a local Redis service.

## Run locally

```bash
gunicorn --bind 0.0.0.0:8000 app.wsgi:app
```

For development reloads:

```bash
python -m flask --app app.wsgi:app run --reload --port 8000
```

## Docker compose

```bash
cp .env.example .env
# edit .env with your local values
docker compose up --build
```

Recommended Docker commands:

```bash
make docker-dev
make docker-status-all
make docker-rebuild-clean
```

If you only want the production-style container layout without the source
mount, use:

```bash
make docker-prod
```
