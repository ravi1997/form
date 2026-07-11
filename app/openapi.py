from __future__ import annotations

import atexit
from typing import Any, Dict, Optional

from app.api import register_api_routes
from app.config import apply_app_config, build_runtime_settings
from app.extensions import db
from app.middleware.observability import register_observability_middleware
from app.middleware.request_id import register_request_id_middleware
from app.middleware.rotating_logger_middleware import setup_rotating_logger_middleware
from app.services import get_rotating_logger

try:
    from flask_openapi3 import Info, OpenAPI
except ImportError as exc:  # pragma: no cover - evaluated only when package is missing
    raise RuntimeError(
        "flask-openapi3 is required for OpenAPI integration. Install with: pip install flask-openapi3"
    ) from exc


API_INFO = Info(
    title="Form Service API",
    version="1.0.0",
    description="OpenAPI-enabled endpoints for form, user, and response management.",
)


def create_openapi_app(config: Optional[Dict[str, Any]] = None):
    """Build a Flask OpenAPI app and register API routes."""
    app = OpenAPI(__name__, info=API_INFO)

    env_name = config.get("APP_ENV") if config else None
    apply_app_config(app, overrides=config, env_name=env_name)
    settings = build_runtime_settings(app.config)
    app.logger.setLevel(settings.log_level)
    register_request_id_middleware(app)
    register_observability_middleware(app)
    setup_rotating_logger_middleware(
        app,
        log_dir=settings.log_dir,
        max_bytes=settings.log_max_bytes,
        backup_count=settings.log_backup_count,
    )
    logger = get_rotating_logger(
        log_dir=settings.log_dir,
        max_bytes=settings.log_max_bytes,
        backup_count=settings.log_backup_count,
    )
    logger.log_app_event(
        "service_startup",
        context={
            "env": settings.env_name,
            "api_version": settings.api_version,
        },
    )

    if settings.enable_compression:
        from flask_compress import Compress

        Compress(app)

    db.init_app(app)

    # Initialize cache system and async execution layer
    from app.services.condition_cache import initialize_global_caches
    from app.celery.app import init_celery
    from app.services.condition_management_monitoring import (
        ensure_monitoring_stats_retention_index,
    )
    from pymongo.errors import PyMongoError

    initialize_global_caches(ttl_seconds=300, ttl_max_size=1000)
    init_celery(app)
    try:
        ensure_monitoring_stats_retention_index(
            settings.monitoring_stats_retention_days
        )
    except PyMongoError as exc:
        app.logger.warning(
            "monitoring_stats_retention_index_setup_failed: %s", exc
        )

    # Seed default superadmin if configured (skip during testing to prevent conflicts)
    if not app.config.get("TESTING") and app.config.get(
        "ENABLE_SUPERADMIN_BOOTSTRAP"
    ):
        try:
            from scripts.seed_superadmin import seed_superadmin
            seed_superadmin(app)
        except Exception as exc:
            app.logger.warning("superadmin_seeding_failed: %s", exc)

    register_api_routes(app)

    atexit.register(
        lambda: logger.log_app_event(
            "service_shutdown",
            context={"reason": "process_exit"},
        )
    )

    return app
