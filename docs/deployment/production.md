# Production Deployment

## Requirements

- MongoDB
- Redis
- A strong `JWT_SECRET_KEY`
- A secured `MONGODB_URI`

## Recommended runtime shape

- Run the API with Gunicorn
- Run Celery workers separately from the web process
- Keep logs on persistent storage or ship them to a log collector
- Use readiness checks against MongoDB before sending traffic

## Compose stack

The compose stack defines `app`, `mongo`, `redis`, `worker`, and optional `beat`.
