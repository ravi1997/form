from flask import Blueprint, jsonify, request

from models.core import ResponseRecord, now_utc
from routes.forms import store
from validators.form_validator import validate_response_payload

responses_bp = Blueprint("responses", __name__)


@responses_bp.post("/forms/<form_id>/responses")
def create_response(form_id: str):
    form = store.get_form(form_id)
    if not form:
        return jsonify({"error": "Form not found"}), 404
    body = request.get_json(silent=True) or {}
    answers = body.get("answers", {})
    valid, errors = validate_response_payload(form.__dict__, answers)
    if not valid:
        return jsonify({"error": "Validation failed", "details": errors}), 400
    response = ResponseRecord(
        form_id=form_id,
        answers=answers,
        status=body.get("status", "draft"),
        submitted_at=now_utc() if body.get("status", "draft") != "draft" else None,
    )
    store.upsert_response(response)
    return jsonify({"status": "success", "response": response.__dict__}), 201


@responses_bp.get("/forms/<form_id>/responses")
def list_responses(form_id: str):
    data = [r.__dict__ for r in store.list_responses_by_form_id(form_id)]
    return jsonify({"status": "success", "responses": data}), 200


@responses_bp.get("/responses/<response_id>")
def get_response(response_id: str):
    response = store.get_response(response_id)
    if not response:
        return jsonify({"error": "Response not found"}), 404
    return jsonify({"status": "success", "response": response.__dict__}), 200


@responses_bp.patch("/responses/<response_id>")
def patch_response(response_id: str):
    response = store.get_response(response_id)
    if not response:
        return jsonify({"error": "Response not found"}), 404
    body = request.get_json(silent=True) or {}
    if "answers" in body:
        form = store.get_form(response.form_id)
        valid, errors = validate_response_payload(form.__dict__, body["answers"])
        if not valid:
            return jsonify({"error": "Validation failed", "details": errors}), 400
        response.answers = body["answers"]
    if "status" in body:
        response.status = body["status"]
        if response.status == "submitted" and not response.submitted_at:
            response.submitted_at = now_utc()
    response.updated_at = now_utc()
    store.upsert_response(response)
    return jsonify({"status": "success", "response": response.__dict__}), 200
