from __future__ import annotations

from flask import Blueprint, redirect, request

from app.api.auth import auth_api
from app.api.health import health_api
from app.api.resources import resources_api


API_BLUEPRINTS = [health_api, auth_api, resources_api]

legacy_api_compat = Blueprint("legacy_api_compat", __name__)


def _redirect_compat(target_path: str):
    query = request.query_string.decode("utf-8")
    if query:
        target_path = f"{target_path}?{query}"
    return redirect(target_path, code=308)


@legacy_api_compat.route("/api/health", methods=["GET"])
def _legacy_health():
    return _redirect_compat("/api/v1/health")


@legacy_api_compat.route("/api/schemas/echo-form", methods=["POST"])
def _legacy_echo_form():
    return _redirect_compat("/api/v1/schemas/echo-form")


@legacy_api_compat.route(
    "/api/auth",
    defaults={"subpath": ""},
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
@legacy_api_compat.route(
    "/api/auth/<path:subpath>",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
def _legacy_auth(subpath: str):
    target = "/api/v1/auth"
    if subpath:
        target = f"{target}/{subpath}"
    return _redirect_compat(target)


@legacy_api_compat.route(
    "/api/projects",
    defaults={"subpath": ""},
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
@legacy_api_compat.route(
    "/api/projects/<path:subpath>",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
def _legacy_projects(subpath: str):
    target = "/api/v1/projects"
    if subpath:
        target = f"{target}/{subpath}"
    return _redirect_compat(target)


def register_api_routes(app):
    app.register_blueprint(legacy_api_compat)
    for blueprint in API_BLUEPRINTS:
        if hasattr(app, "register_api"):
            app.register_api(blueprint)
        else:
            app.register_blueprint(blueprint)
