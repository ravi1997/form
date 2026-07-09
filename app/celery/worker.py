from __future__ import annotations

from app.celery.app import init_celery
from app.openapi import create_openapi_app


flask_app = create_openapi_app()
celery_app = init_celery(flask_app)

__all__ = ["celery_app", "flask_app"]
