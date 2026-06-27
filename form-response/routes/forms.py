from flask import Blueprint, jsonify, request

from repositories.memory import store
from models.core import FormSnapshot
from validators.form_validator import minimal_form_snapshot, build_question_index

forms_bp = Blueprint("forms", __name__)


@forms_bp.post("/forms/ingest")
def ingest_form():
    body = request.get_json(silent=True) or {}
    form_id = str(body.get("id") or body.get("_id") or "")
    if not form_id:
        return jsonify({"error": "Form id is required"}), 400
    snapshot = minimal_form_snapshot(body)
    form = FormSnapshot(
        form_id=snapshot["form_id"],
        title=snapshot["title"],
        sections=snapshot["sections"],
        question_index=build_question_index(body),
    )
    store.upsert_form(form)
    return jsonify({"status": "success", "form": form.__dict__}), 201


@forms_bp.get("/forms/<form_id>")
def get_form(form_id: str):
    form = store.get_form(form_id)
    if not form:
        return jsonify({"error": "Form not found"}), 404
    return jsonify({"status": "success", "form": form.__dict__}), 200
