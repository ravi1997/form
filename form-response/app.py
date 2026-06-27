from flask import Flask

from config import Config
from bootstrap import bootstrap_repository
import routes.forms as forms_routes
import routes.responses as responses_routes
import routes.sync as sync_routes


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config())
    repo = bootstrap_repository(app.config["DATABASE_URL"])
    forms_routes.store = repo
    responses_routes.store = repo
    sync_routes.store = repo
    app.register_blueprint(forms_routes.forms_bp)
    app.register_blueprint(responses_routes.responses_bp)
    app.register_blueprint(sync_routes.sync_bp)

    @app.get("/healthz")
    def healthz():
        return {"status": "ok", "database": repo.health_check()}, 200

    return app


app = create_app()
