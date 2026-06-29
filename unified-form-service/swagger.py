"""
swagger.py
----------
Auto-generate Swagger/OpenAPI 2.0 documentation for the unified-form-service.
Served at: http://localhost:5000/apidocs/

Usage in app.py:
    from swagger import init_swagger
    init_swagger(app)
"""

from flasgger import Swagger

SWAGGER_TEMPLATE = {
    "swagger": "2.0",
    "info": {
        "title": "Unified Form Service API",
        "description": (
            "A single-process form platform combining a **Form Builder**, "
            "a **Response Gateway**, and a **Form Analyser** — all in one Flask app.\n\n"
            "## Authentication\n"
            "- **Builder & Gateway endpoints** → `Authorization: Bearer <JWT>`\n"
            "- **Analyser endpoints** → `X-API-Key: <key>` or `Authorization: Bearer <JWT>`"
        ),
        "version": "1.5.0",
        "contact": {
            "name": "API Support",
            "url": "https://github.com/your-org/unified-form-service"
        },
        "license": {
            "name": "MIT",
            "url": "https://opensource.org/licenses/MIT"
        }
    },
    "basePath": "/",
    "schemes": ["http", "https"],
    "securityDefinitions": {
        "BearerAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "Authorization",
            "description": "JWT token. Format: `Bearer <token>`"
        },
        "ApiKeyAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "API key for Analyser endpoints."
        }
    },
    "tags": [
        {"name": "Health",            "description": "Service health check"},
        {"name": "Auth (Builder)",    "description": "Builder user registration and login"},
        {"name": "Forms (Builder)",   "description": "Form creation, versioning, and publishing"},
        {"name": "Responses (Builder)", "description": "Form submissions and response management"},
        {"name": "VCS",               "description": "Git-style version control for form schemas"},
        {"name": "Workflows",         "description": "Workflow runs and triggers"},
        {"name": "Export (Builder)",  "description": "CSV/JSON/PDF export from builder"},
        {"name": "Gateway Forms",     "description": "Response gateway — form snapshot ingest"},
        {"name": "Gateway Responses", "description": "Response gateway — response collection"},
        {"name": "Gateway Sync",      "description": "Response gateway — analyser sync"},
        {"name": "Auth (Analyser)",   "description": "Analyser user login and API key management"},
        {"name": "Analysis",          "description": "Analysis definition CRUD, run, schedule"},
        {"name": "Webhooks",          "description": "Webhook CRUD and test delivery"},
        {"name": "Schema",            "description": "Auto-detect field schema from response data"},
        {"name": "Forms (Analyser)",  "description": "Analyser form registry"},
        {"name": "Raw Responses",     "description": "Analyser raw response store"},
    ]
}

SWAGGER_CONFIG = {
    "headers": [],
    "specs": [
        {
            "endpoint": "apispec",
            "route": "/apispec.json",
            "rule_filter": lambda rule: True,
            "model_filter": lambda tag: True,
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/apidocs/",
    "title": "Unified Form Service API",
    "uiversion": 3,
}


def init_swagger(app):
    """Register Flasgger (Swagger UI) on the Flask app."""
    Swagger(app, template=SWAGGER_TEMPLATE, config=SWAGGER_CONFIG)
    app.logger.info("Swagger UI available at /apidocs/")
