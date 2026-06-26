"""
app.py
------
Flask application factory — registers all blueprints and starts the scheduler.
"""

from __future__ import annotations

from flask import Flask, jsonify
from pymongo import MongoClient

from config import active_config
from scheduler import load_all_schedules, start_scheduler, shutdown_scheduler

from blueprints.auth_routes import auth_bp
from blueprints.analysis_routes import analysis_bp
from blueprints.response_routes import responses_bp
from blueprints.form_routes import forms_bp
from blueprints.schema_routes import schema_bp
from blueprints.webhook_routes import webhooks_bp
from metrics_manager import setup_metrics


def create_app(config=None) -> Flask:
    from json_logger import setup_json_logging
    setup_json_logging()

    app = Flask(__name__)
    cfg = config or active_config
    app.config.from_object(cfg)

    # ------------------------------------------------------------------
    # MongoDB — store all collections in app.extensions
    # ------------------------------------------------------------------
    client = MongoClient(cfg.MONGO_URI)
    db = client[cfg.MONGO_DB_NAME]

    app.extensions["db"]              = db
    app.extensions["responses_col"]   = db[cfg.FORM_RESPONSES_COLLECTION]
    app.extensions["definitions_col"] = db[cfg.ANALYSIS_DEFINITIONS_COLLECTION]
    app.extensions["results_col"]     = db[cfg.ANALYSIS_RESULTS_COLLECTION]
    app.extensions["keys_col"]        = db[cfg.API_KEYS_COLLECTION]
    app.extensions["webhooks_col"]    = db[cfg.WEBHOOKS_COLLECTION]
    app.extensions["forms_col"]       = db[cfg.FORMS_COLLECTION]
    app.extensions["users_col"]       = db["users"]

    # ------------------------------------------------------------------
    # Blueprints
    # ------------------------------------------------------------------
    app.register_blueprint(auth_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(responses_bp)
    app.register_blueprint(forms_bp)
    app.register_blueprint(schema_bp)
    app.register_blueprint(webhooks_bp)

    setup_metrics(app)

    # ------------------------------------------------------------------
    # Scheduler: reload active schedules from MongoDB then start
    # ------------------------------------------------------------------
    with app.app_context():
        load_all_schedules(
            app.extensions["definitions_col"],
            cfg.MONGO_URI,
            cfg.MONGO_DB_NAME,
            cfg.ANALYSIS_DEFINITIONS_COLLECTION,
            cfg.ANALYSIS_RESULTS_COLLECTION,
            cfg.WEBHOOKS_COLLECTION,
        )
    start_scheduler()

    import atexit
    atexit.register(shutdown_scheduler)

    # ------------------------------------------------------------------
    # Health check (no auth required)
    # ------------------------------------------------------------------
    @app.get("/api/health")
    def health():
        try:
            client.admin.command("ping")
            mongo_status = "connected"
        except Exception as exc:
            mongo_status = f"error: {exc}"

        redis_status = "disconnected"
        redis_workers = 0
        redis_url = app.config.get("REDIS_URL")
        if redis_url:
            try:
                from redis import Redis
                from rq import Worker
                r = Redis.from_url(redis_url)
                r.ping()
                redis_status = "connected"
                redis_workers = len(Worker.all(connection=r))
            except Exception as e:
                redis_status = f"error: {e}"

        from scheduler import get_scheduler, list_scheduled_jobs
        sched = get_scheduler()

        status = "ok"
        if "error" in mongo_status or "error" in redis_status:
            status = "unhealthy"

        return jsonify({
            "status": status,
            "mongo": mongo_status,
            "redis": redis_status,
            "rq_workers_active": redis_workers,
            "auth_enabled": cfg.AUTH_ENABLED,
            "scheduler": {
                "running": sched.running,
                "active_jobs": len(list_scheduled_jobs()),
            },
        })

    # ------------------------------------------------------------------
    # Error handlers
    # ------------------------------------------------------------------
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"status": "error", "message": "Route not found"}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"status": "error", "message": "Method not allowed"}), 405

    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    application = create_app()
    application.run(host="0.0.0.0", port=5000, debug=active_config.DEBUG)
