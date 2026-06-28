"""
blueprints/form_routes.py
--------------------------
Full form-level scoping — register forms, browse their analyses, run them all.

  POST   /api/forms                          Register a form (with metadata)
  GET    /api/forms                          List all registered forms
  GET    /api/forms/<form_id>                Form detail: metadata + linked analyses + latest results
  DELETE /api/forms/<form_id>                Delete form and optionally its analyses
  POST   /api/forms/<form_id>/run-all        Run every analysis definition linked to this form
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from bson import ObjectId
from flask import Blueprint, Response, current_app, jsonify, request

from analysis_engine import run_analysis
from analyser_auth import require_api_key

forms_bp = Blueprint("forms", __name__, url_prefix="/api/v1/forms")


class _Encoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


def _json(data=None, message="OK", status=200):
    payload = {"status": "success" if status < 400 else "error", "message": message}
    if data is not None:
        payload["data"] = data
    return Response(json.dumps(payload, cls=_Encoder), status=status, mimetype="application/json")


def _err(message, status=400):
    return _json(message=message, status=status)


def _forms_col():
    return current_app.extensions["forms_col"]


def _definitions_col():
    return current_app.extensions["definitions_col"]


def _results_col():
    return current_app.extensions["results_col"]


def _responses_col():
    return current_app.extensions["responses_col"]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@forms_bp.post("")
@require_api_key
def register_form():
    """
    Register a form so it can be browsed and managed as a unit.

    Body:
    {
      "form_id":     "customer_satisfaction_q1_2024",  // required — unique identifier
      "name":        "Customer Satisfaction Q1 2024",
      "description": "...",
      "id_field":    "survey_id"  // the field in form_responses that holds this form_id
                                   // defaults to "survey_id"
    }
    """
    body = request.get_json(silent=True)
    if not body:
        return _err("Request body must be valid JSON")
    if not body.get("form_id"):
        return _err("'form_id' is required")

    # Prevent duplicates
    if _forms_col().find_one({"form_id": body["form_id"]}):
        return _err(f"A form with form_id '{body['form_id']}' is already registered", 409)

    now = datetime.now(timezone.utc)
    doc = {
        "form_id": body["form_id"],
        "name": body.get("name", body["form_id"]),
        "description": body.get("description", ""),
        "id_field": body.get("id_field", "survey_id"),   # field in responses collection
        "created_at": now,
        "updated_at": now,
    }
    result = _forms_col().insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return _json(data=doc, message="Form registered", status=201)


@forms_bp.get("")
@require_api_key
def list_forms():
    """
    List all registered forms along with:
    - how many responses exist for each form
    - how many analysis definitions are linked to each form
    """
    forms = list(_forms_col().find({}).sort("created_at", -1))

    for form in forms:
        fid = form["form_id"]
        id_field = form.get("id_field", "survey_id")

        # Response count
        form["response_count"] = _responses_col().count_documents({id_field: fid})

        # Analysis definition count
        form["analysis_count"] = _definitions_col().count_documents({"form_id": fid})

        form["_id"] = str(form["_id"])

    return _json(data=forms)


@forms_bp.get("/<path:form_id>")
@require_api_key
def get_form(form_id: str):
    """
    Get full detail for a form:
    - Form metadata
    - All linked analysis definitions (name + latest run info)
    - Total response count
    """
    form = _forms_col().find_one({"form_id": form_id})
    if not form:
        return _err(f"Form '{form_id}' not found. Register it first via POST /api/forms", 404)

    id_field = form.get("id_field", "survey_id")
    form["_id"] = str(form["_id"])

    # Response count
    form["response_count"] = _responses_col().count_documents({id_field: form_id})

    # Linked analyses with latest result metadata
    analyses = list(
        _definitions_col().find(
            {"form_id": form_id},
            {"name": 1, "description": 1, "schedule": 1, "created_at": 1},
        ).sort("created_at", -1)
    )

    for analysis in analyses:
        aid = analysis["_id"]
        analysis["_id"] = str(aid)

        # Latest cached result summary
        latest = _results_col().find_one(
            {"definition_id": aid},
            sort=[("run_at", -1)],
            projection={"run_at": 1, "trigger": 1, "result.total_matching_responses": 1},
        )
        if latest:
            analysis["latest_run"] = {
                "run_at": latest.get("run_at"),
                "trigger": latest.get("trigger"),
                "total_responses": (latest.get("result") or {}).get("total_matching_responses"),
            }
        else:
            analysis["latest_run"] = None

    form["analyses"] = analyses
    form["analysis_count"] = len(analyses)
    return _json(data=form)


@forms_bp.delete("/<path:form_id>")
@require_api_key
def delete_form(form_id: str):
    """
    Delete a registered form.

    Query params:
      delete_analyses=true   also delete all linked analysis definitions + their results
    """
    form = _forms_col().find_one({"form_id": form_id})
    if not form:
        return _err(f"Form '{form_id}' not found", 404)

    _forms_col().delete_one({"form_id": form_id})

    deleted_analyses = 0
    deleted_results = 0

    if request.args.get("delete_analyses", "false").lower() in ("true", "1", "yes"):
        analysis_docs = list(_definitions_col().find({"form_id": form_id}, {"_id": 1}))
        analysis_oids = [d["_id"] for d in analysis_docs]

        if analysis_oids:
            r = _results_col().delete_many({"definition_id": {"$in": analysis_oids}})
            deleted_results = r.deleted_count
            r = _definitions_col().delete_many({"form_id": form_id})
            deleted_analyses = r.deleted_count

    return _json(message=(
        f"Form '{form_id}' deleted. "
        f"Analyses deleted: {deleted_analyses}. Results deleted: {deleted_results}."
    ))


@forms_bp.post("/<path:form_id>/run-all")
@require_api_key
def run_all_analyses(form_id: str):
    """
    Run every analysis definition linked to this form and cache all results.

    Optional body:
      { "extra_filters": [...] }   applied to every analysis in this run

    Returns per-analysis results keyed by definition _id.
    """
    form = _forms_col().find_one({"form_id": form_id})
    if not form:
        return _err(f"Form '{form_id}' not found", 404)

    body = request.get_json(silent=True) or {}
    extra_filters = body.get("extra_filters", [])

    analyses = list(_definitions_col().find({"form_id": form_id}))
    if not analyses:
        return _err(f"No analysis definitions linked to form '{form_id}'. "
                    "Create definitions with 'form_id': '{form_id}' to link them.", 404)

    db = current_app.extensions["db"]
    now = datetime.now(timezone.utc)
    run_results = {}

    for analysis in analyses:
        aid = analysis["_id"]
        aid_str = str(aid)

        # Merge extra filters
        if extra_filters:
            analysis.setdefault("filters", [])
            analysis["filters"].extend(extra_filters)

        try:
            result = run_analysis(db, analysis)

            # Cache result
            _results_col().insert_one({
                "definition_id": aid,
                "run_at": now,
                "trigger": "manual_run_all",
                "extra_filters": extra_filters,
                "result": result,
            })

            run_results[aid_str] = {
                "status": "success",
                "name": analysis.get("name"),
                "total_matching_responses": result.get("total_matching_responses"),
            }

        except Exception as exc:
            run_results[aid_str] = {
                "status": "failed",
                "name": analysis.get("name"),
                "error": str(exc),
            }

    success_count = sum(1 for r in run_results.values() if r["status"] == "success")
    fail_count = len(run_results) - success_count

    return _json(
        data={
            "form_id": form_id,
            "analyses_run": len(analyses),
            "success": success_count,
            "failed": fail_count,
            "results": run_results,
        },
        message=f"Ran {len(analyses)} analyses: {success_count} succeeded, {fail_count} failed.",
    )
