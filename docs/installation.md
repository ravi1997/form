# Installation

## Prerequisites

- Python 3.13+
- MongoDB 6+
- Redis 7+ for Celery and distributed rate limiting

## Local install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-test.txt
cp .env.example .env
```

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
export JWT_SECRET_KEY=change-me
export MONGO_INITDB_ROOT_PASSWORD=change-me-too
docker compose up --build
```
