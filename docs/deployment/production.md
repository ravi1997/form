# Production Deployment

## Requirements

- MongoDB
- Redis
- A strong `JWT_SECRET_KEY`
- A secured `MONGODB_URI`
- `APP_ENV=production`

## Recommended runtime shape

- Run the API with Gunicorn
- Run Celery workers separately from the web process
- Keep logs on persistent storage or ship them to a log collector
- Use readiness checks against MongoDB before sending traffic
- Keep `LOG_LEVEL=INFO` in production unless debugging a live issue

## Compose stack

The compose stack defines `app`, `mongo`, `redis`, `worker`, and optional `beat`.

### Container roles

- `app` exposes the Flask API on port 8000
- `mongo` stores application data
- `redis` backs Celery and rate limiting
- `worker` runs Celery tasks
- `beat` is present for scheduled work but is optional and profiled behind `scheduler`

## Required secrets and connection values

```bash
JWT_SECRET_KEY=<strong-random-secret>
MONGO_INITDB_ROOT_PASSWORD=<strong-mongo-root-password>
MONGODB_URI=mongodb://formadmin:<password>@mongo:27017/form_prod?authSource=admin
MONGODB_DB=form_prod
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1
```

## Operational checks

- `GET /api/v1/health` should return `ok`
- `GET /api/v1/readiness` should return `ready` with database `ok`
- `GET /api/v1/metrics` should show queue and request metrics
- worker logs should confirm task pickup and completion

## Security checklist

- restrict `CORS_ALLOW_ORIGINS`
- keep MongoDB and Redis private to the application network
- use TLS termination at the load balancer or ingress
- rotate JWT keys using `JWT_ADDITIONAL_KEYS`
- mount `LOG_DIR` to persistent storage
