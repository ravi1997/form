# Docker Deployment

## Build

```bash
docker build -t form-service:latest .
```

## Compose

```bash
export JWT_SECRET_KEY=change-me
export MONGO_INITDB_ROOT_PASSWORD=change-me-too
docker compose up --build
```

## Notes

- The app container exposes port 8000
- MongoDB and Redis each have health checks in compose
- The worker uses the same image as the API
