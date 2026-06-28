from flask import Blueprint, jsonify, request

from repositories.memory import store
from models.core import FormSnapshot
from validators.form_validator import minimal_form_snapshot, build_question_index
from auth import login_required

forms_bp = Blueprint("forms", __name__)


@forms_bp.post("/forms/ingest")
@login_required
def ingest_form():
    body = request.get_json(silent=True) or {}
    form_id = str(body.get("id") or body.get("_id") or "")
    if not form_id:
        return jsonify({"error": "Form id is required"}), 400
    snapshot = minimal_form_snapshot(body)
    
    # Retrieve existing latest version to see if structure has changed
    existing = store.get_form(form_id)
    if existing:
        # Check if the title or sections changed
        structure_changed = (
            existing.title != snapshot["title"] or
            existing.sections != snapshot["sections"]
        )
        if structure_changed:
            version = existing.snapshot_version + 1
        else:
            version = existing.snapshot_version
    else:
        version = 1

    form = FormSnapshot(
        form_id=snapshot["form_id"],
        title=snapshot["title"],
        sections=snapshot["sections"],
        question_index=build_question_index(body),
        snapshot_version=version,
    )
    store.upsert_form(form)
    return jsonify({"status": "success", "form": form.__dict__}), 201


@forms_bp.get("/forms/<form_id>")
@login_required
def get_form(form_id: str):
    version_str = request.args.get("version")
    version = int(version_str) if version_str and version_str.isdigit() else None
    form = store.get_form(form_id, snapshot_version=version)
    if not form:
        return jsonify({"error": "Form not found"}), 404
    return jsonify({"status": "success", "form": form.__dict__}), 200
