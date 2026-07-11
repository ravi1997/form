FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    HOME=/tmp \
    TMPDIR=/tmp \
    LOG_DIR=/app/logs \
    LOG_LEVEL=INFO \
    ENABLE_COMPRESSION=true \
    MONGODB_DB=form_prod

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app && \
    mkdir -p /var/log/form /app/logs /tmp && chown -R app:app /var/log/form /app/logs /tmp

COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir /wheels/* && rm -rf /wheels

COPY --chown=app:app app app

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=5 --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3)"

CMD ["python", "-m", "gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--timeout", "60", "--graceful-timeout", "30", "--access-logfile", "-", "--error-logfile", "-", "app.wsgi:app"]
