# Configuration

## Source of truth

- `.env.example` lists the supported environment variables with comments
- `app/config.py` defines the defaults and validation rules
- `docker-compose.yml` shows the production container values used by the stack

## Runtime settings

- `APP_ENV` selects development or production behavior
- JWT settings control signing keys and token TTLs
- Rate-limit settings control auth and resource request windows
- MongoDB settings define the database connection and timeouts
- Celery settings control broker, backend, queue, and task timeouts
- Logging settings control log level, directory, rotation size, and backups
- `CORS_ALLOW_ORIGINS` sets allowed browser origins
- `ENABLE_COMPRESSION` enables `flask-compress`

## Validation behavior

- Unknown environment variables matching the sensitive config namespaces are warned about in development
- The same unknown keys fail fast in production
- Integer settings are range-checked by `app/config.py`
