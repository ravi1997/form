from __future__ import annotations

from flask import Blueprint, redirect, request

from app.api.auth import auth_api
from app.api.health import health_api
from app.api.conditions import conditions_api
from app.api.rate_limit import create_rate_limit_api
from app.api.resources import resources_api
from app.api.ui_templates import ui_api

API_BLUEPRINTS = [health_api, auth_api, resources_api, conditions_api, ui_api]



def register_api_routes(app):
    blueprints = [*API_BLUEPRINTS, create_rate_limit_api(app)]
    for blueprint in blueprints:
        if hasattr(app, "register_api"):
            app.register_api(blueprint)
        else:
            app.register_blueprint(blueprint)
