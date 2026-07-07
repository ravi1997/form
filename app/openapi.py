from __future__ import annotations

from typing import Any, Dict, Optional

from app.api import register_api_routes
from app.config import apply_app_config
from app.extensions import db
from app.middleware.request_id import register_request_id_middleware

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
    register_request_id_middleware(app)

    db.init_app(app)
    register_api_routes(app)
    return app
