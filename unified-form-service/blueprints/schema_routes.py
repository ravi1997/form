"""
blueprints/schema_routes.py
----------------------------
Schema auto-detection routes.

  POST /api/schema/detect     Scan a collection and return a suggested analysis definition
  GET  /api/schema/fields     List all detected fields with types and sample values
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request, g

from analyser_auth import require_auth
from schema_detector import detect_schema, get_field_list
from rate_limiter import rate_limit

schema_bp = Blueprint("schema", __name__, url_prefix="/api/v1/schema")


def _ok(data=None, message="OK", status=200):
    payload = {"status": "success", "message": message}
    if data is not None:
        payload["data"] = data
    return jsonify(payload), status


def _err(message, status=400):
    return jsonify({"status": "error", "message": message}), status


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@schema_bp.post("/detect")
@require_auth(allowed_roles=["admin", "analyst"])
@rate_limit(limit=5, period=60)
def detect():
    """
    Scan a collection and return a complete, ready-to-use analysis definition JSON.
    Limited to documents belonging to the user's organization.
    """
    body = request.get_json(silent=True) or {}

    cfg = current_app.config
    collection_name = body.get("collection", cfg["FORM_RESPONSES_COLLECTION"])
    db = current_app.extensions["db"]
    collection = db[collection_name]
    org_id = g.user.get("organization_id")

    try:
        result = detect_schema(
            collection,
            sample_size=int(body.get("sample_size", 200)),
            id_field=body.get("id_field"),
            form_id_value=body.get("form_id_value"),
            extra_skip_fields=body.get("skip_fields", []),
            organization_id=org_id,
        )
    except Exception as exc:
        return _err(f"Detection failed: {exc}", 500)

    return _ok(
        data=result,
        message=f"Detected {result.get('_detection_meta', {}).get('steps_suggested', 0)} steps "
                f"from {result.get('_detection_meta', {}).get('sample_size', 0)} documents.",
    )


@schema_bp.get("/fields")
@require_auth(allowed_roles=["admin", "analyst", "viewer"])
@rate_limit(limit=10, period=60)
def list_fields():
    """
    List all detected fields in a collection with type info and sample values.
    Limited to documents belonging to the user's organization.
    """
    cfg = current_app.config
    collection_name = request.args.get("collection", cfg["FORM_RESPONSES_COLLECTION"])
    db = current_app.extensions["db"]
    collection = db[collection_name]
    org_id = g.user.get("organization_id")

    try:
        fields = get_field_list(
            collection,
            sample_size=int(request.args.get("sample_size", 200)),
            id_field=request.args.get("id_field"),
            form_id_value=request.args.get("form_id_value"),
            organization_id=org_id,
        )
    except Exception as exc:
        return _err(f"Field detection failed: {exc}", 500)

    return _ok(data={
        "collection": collection_name,
        "field_count": len(fields),
        "fields": fields,
    })
