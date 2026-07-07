from __future__ import annotations

from app.api.auth import auth_api
from app.api.health import health_api


API_BLUEPRINTS = [health_api, auth_api]


def register_api_routes(app):
    for blueprint in API_BLUEPRINTS:
        if hasattr(app, "register_api"):
            app.register_api(blueprint)
        else:
            app.register_blueprint(blueprint)
