from flask import Blueprint, jsonify, request

import routes.forms as forms_routes
from services.analyser_adapter import AnalyserSyncService
from auth import login_required

sync_bp = Blueprint("sync", __name__)
adapter = AnalyserSyncService()


@sync_bp.post("/sync/analyser")
@login_required
def sync_analyser():
    body = request.get_json(silent=True) or {}
    response_id = body.get("response_id")
    response = forms_routes.store.get_response(response_id)
    if not response:
        return jsonify({"error": "Response not found"}), 404
    form = forms_routes.store.get_form(response.form_id)
    if not form:
        return jsonify({"error": "Form not found"}), 404
    result = adapter.sync(form.__dict__, response.__dict__)
    return jsonify({"status": "success", "sync": result}), 200
