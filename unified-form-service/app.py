import os
import sys
from flask import Flask, jsonify
from pymongo import MongoClient

# Add current directory to path to ensure clean imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# 1. Import builder app to inherit its collections, variables, and routes
from builder_app import app

# 2. Setup response gateway (form-response)
from response_bootstrap import bootstrap_repository
from config import ResponseConfig
import routes.forms as response_forms_routes
import routes.responses as response_responses_routes
import routes.sync as response_sync_routes

# Initialize response repository on the same or distinct Mongo DB
response_db_url = os.getenv("RESPONSE_DATABASE_URL", "mongodb://localhost:27017/form_response")
response_repo = bootstrap_repository(response_db_url)
response_forms_routes.store = response_repo
response_responses_routes.store = response_repo
response_sync_routes.store = response_repo

# Register response blueprints
app.register_blueprint(response_forms_routes.forms_bp)
app.register_blueprint(response_responses_routes.responses_bp)
app.register_blueprint(response_sync_routes.sync_bp)

# 3. Setup analyser (form-analyser)
from config import active_config as analyser_cfg
from blueprints.auth_routes import auth_bp
from blueprints.analysis_routes import analysis_bp
from blueprints.response_routes import responses_bp as analyser_responses_bp
from blueprints.form_routes import forms_bp as analyser_forms_bp
from blueprints.schema_routes import schema_bp
from blueprints.webhook_routes import webhooks_bp
from metrics_manager import setup_metrics
from scheduler import load_all_schedules, start_scheduler

# Connect analyser MongoDB
analyser_client = MongoClient(analyser_cfg.MONGO_URI)
analyser_db = analyser_client[analyser_cfg.MONGO_DB_NAME]

# Populate app extensions for analyser blueprints
app.extensions["db"]              = analyser_db
app.extensions["responses_col"]   = analyser_db[analyser_cfg.FORM_RESPONSES_COLLECTION]
app.extensions["definitions_col"] = analyser_db[analyser_cfg.ANALYSIS_DEFINITIONS_COLLECTION]
app.extensions["results_col"]     = analyser_db[analyser_cfg.ANALYSIS_RESULTS_COLLECTION]
app.extensions["keys_col"]        = analyser_db[analyser_cfg.API_KEYS_COLLECTION]
app.extensions["webhooks_col"]    = analyser_db[analyser_cfg.WEBHOOKS_COLLECTION]
app.extensions["forms_col"]       = analyser_db[analyser_cfg.FORMS_COLLECTION]
app.extensions["users_col"]       = analyser_db["users"]

# Register analyser blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(analysis_bp)
app.register_blueprint(analyser_responses_bp)
app.register_blueprint(analyser_forms_bp)
app.register_blueprint(schema_bp)
app.register_blueprint(webhooks_bp)

# Setup metrics logging
setup_metrics(app)

# Load schedules & start scheduler
with app.app_context():
    try:
        load_all_schedules(analyser_db)
        start_scheduler()
    except Exception as e:
        print(f"Warning: Could not start scheduler: {e}")

# Consolidated Healthz endpoint
@app.get("/healthz")
def healthz():
    return jsonify({
        "status": "ok",
        "services": {
            "builder": "running",
            "response_gateway": "running",
            "analyser": "running"
        }
    }), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
