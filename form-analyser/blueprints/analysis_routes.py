"""
blueprints/analysis_routes.py
------------------------------
Full analysis definition API — CRUD, run, schedule, result cache, export, comparison.

Routes
------
  POST   /api/analysis                       Create & store a definition
  GET    /api/analysis                       List all definitions
  GET    /api/analysis/<id>                  Get one definition
  PUT    /api/analysis/<id>                  Update a definition
  DELETE /api/analysis/<id>                  Delete a definition

  POST   /api/analysis/run                   Run ad-hoc (not stored)
  POST   /api/analysis/<id>/run              Run a stored definition
                                             ?use_cache=true  → return latest cached result

  POST   /api/analysis/<id>/schedule         Enable / update cron schedule
  DELETE /api/analysis/<id>/schedule         Disable schedule
  GET    /api/analysis/scheduled             List all active scheduled jobs

  GET    /api/analysis/<id>/results                      Paginated run history
  GET    /api/analysis/<id>/results/latest               Most recent cached result
  DELETE /api/analysis/<id>/results                      Clear result history

  GET    /api/analysis/<id>/results/compare              Compare two runs
         ?run_a=<result_id>&run_b=<result_id>
  GET    /api/analysis/<id>/results/compare/latest       Compare the latest two runs

  GET    /api/analysis/<id>/results/latest/export        Export latest result (CSV or PDF)
         ?format=csv|pdf
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, Response, current_app, jsonify, request, g

from analysis_engine import run_analysis
from auth import require_api_key, require_auth
from exporter import export_to_csv, export_to_pdf, stream_csv_generator
from scheduler import (
    deregister_schedule,
    list_scheduled_jobs,
    register_schedule,
)
from webhook_dispatcher import fire_webhooks
from indexing import ensure_analysis_indexes
from redis_manager import (
    get_cached_result,
    set_cached_result,
    delete_cached_result,
    enqueue_analysis_run,
    get_job_status,
)

analysis_bp = Blueprint("analysis", __name__, url_prefix="/api/v1/analysis")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _MongoEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


def _json_response(data=None, message="OK", status=200):
    payload = {"status": "success" if status < 400 else "error", "message": message}
    if data is not None:
        payload["data"] = data
    body = json.dumps(payload, cls=_MongoEncoder)
    return Response(body, status=status, mimetype="application/json")


def _err(message, status=400):
    return _json_response(message=message, status=status)


def _parse_oid(raw: str) -> ObjectId:
    try:
        return ObjectId(raw)
    except (InvalidId, TypeError):
        raise ValueError(f"'{raw}' is not a valid document ID")


def _stringify(doc: dict) -> dict:
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


def _definitions_col():
    return current_app.extensions["definitions_col"]


def _results_col():
    return current_app.extensions["results_col"]


def _webhooks_col():
    return current_app.extensions["webhooks_col"]


def _cfg_schedule_args():
    """Return scheduler kwargs from current app config."""
    cfg = current_app.config
    return (
        cfg["MONGO_URI"],
        cfg["MONGO_DB_NAME"],
        cfg["ANALYSIS_DEFINITIONS_COLLECTION"],
        cfg["ANALYSIS_RESULTS_COLLECTION"],
        cfg["WEBHOOKS_COLLECTION"],
    )


def _save_result(definition_id: ObjectId, result: dict,
                 trigger: str, extra_filters: list):
    """Persist a run result to the analysis_results collection."""
    _results_col().insert_one({
        "definition_id": definition_id,
        "run_at": datetime.now(timezone.utc),
        "trigger": trigger,
        "extra_filters": extra_filters,
        "result": result,
    })


def _fire_webhooks_safe(definition_id, analysis_name, result,
                         run_status="success", error=None):
    """Fire webhooks without raising exceptions."""
    try:
        fire_webhooks(
            _webhooks_col(), definition_id, analysis_name,
            result, run_status, error,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Comparison helpers
# ---------------------------------------------------------------------------

def _compare_steps(result_a: dict, result_b: dict) -> dict:
    """Build a step-by-step diff between two analysis results."""
    steps_a = result_a.get("results", {})
    steps_b = result_b.get("results", {})
    all_ids = set(steps_a) | set(steps_b)

    comparison = {}
    for sid in all_ids:
        sa = steps_a.get(sid)
        sb = steps_b.get(sid)

        if sa is None:
            comparison[sid] = {"status": "new_in_b", "step": sb}
        elif sb is None:
            comparison[sid] = {"status": "removed", "step": sa}
        else:
            comparison[sid] = _diff_step(sa, sb)

    return comparison


def _diff_step(sa: dict, sb: dict) -> dict:
    stype = sa.get("type")
    base = {"type": stype, "label": sa.get("label"), "status": "compared"}

    if stype == "frequency":
        bd_a = {str(r["value"]): r for r in sa.get("breakdown", [])}
        bd_b = {str(r["value"]): r for r in sb.get("breakdown", [])}
        all_vals = set(bd_a) | set(bd_b)
        diff = []
        for val in all_vals:
            a = bd_a.get(val, {"count": 0, "percentage": 0})
            b = bd_b.get(val, {"count": 0, "percentage": 0})
            diff.append({
                "value": val,
                "count_a": a.get("count", 0),
                "count_b": b.get("count", 0),
                "count_diff": b.get("count", 0) - a.get("count", 0),
                "pct_a": a.get("percentage", 0),
                "pct_b": b.get("percentage", 0),
                "pct_diff": round(b.get("percentage", 0) - a.get("percentage", 0), 2),
            })
        diff.sort(key=lambda x: abs(x["count_diff"]), reverse=True)
        base.update({
            "total_a": sa.get("total_responses", 0),
            "total_b": sb.get("total_responses", 0),
            "diff": diff,
        })

    elif stype == "aggregate":
        va = sa.get("result") or 0
        vb = sb.get("result") or 0
        delta = vb - va
        pct = round(delta / va * 100, 2) if va else None
        base.update({
            "operation": sa.get("operation"),
            "field": sa.get("field"),
            "value_a": va,
            "value_b": vb,
            "diff": round(delta, 4),
            "pct_change": pct,
            "direction": "up" if delta > 0 else ("down" if delta < 0 else "unchanged"),
        })

    elif stype == "top_n":
        top_a = {str(r["value"]): {"count": r.get("count", 0), "rank": i + 1}
                 for i, r in enumerate(sa.get("top", []))}
        top_b = {str(r["value"]): {"count": r.get("count", 0), "rank": i + 1}
                 for i, r in enumerate(sb.get("top", []))}
        all_vals = set(top_a) | set(top_b)
        diff = []
        for val in all_vals:
            a_info = top_a.get(val, {"count": 0, "rank": None})
            b_info = top_b.get(val, {"count": 0, "rank": None})
            ra, rb = a_info["rank"], b_info["rank"]
            rank_change = (ra - rb) if (ra and rb) else None
            diff.append({
                "value": val,
                "count_a": a_info["count"],
                "count_b": b_info["count"],
                "rank_a": ra,
                "rank_b": rb,
                "rank_change": rank_change,
                "entry_status": (
                    "new" if ra is None else ("dropped" if rb is None else "present")
                ),
            })
        diff.sort(key=lambda x: (x["rank_b"] or 999, -(x["rank_a"] or 999)))
        base["diff"] = diff

    elif stype == "missing":
        base.update({
            "missing_a": sa.get("missing", 0),
            "missing_b": sb.get("missing", 0),
            "missing_diff": sb.get("missing", 0) - sa.get("missing", 0),
            "missing_pct_a": sa.get("missing_pct", 0),
            "missing_pct_b": sb.get("missing_pct", 0),
        })

    elif stype == "array_frequency":
        # Compare multi-select option distributions across two runs
        bd_a = {str(r["value"]): r for r in sa.get("breakdown", [])}
        bd_b = {str(r["value"]): r for r in sb.get("breakdown", [])}
        all_vals = set(bd_a) | set(bd_b)
        diff = []
        for val in all_vals:
            a = bd_a.get(val, {"count": 0, "percentage_of_selections": 0, "percentage_of_responses": 0})
            b = bd_b.get(val, {"count": 0, "percentage_of_selections": 0, "percentage_of_responses": 0})
            diff.append({
                "value": val,
                "count_a": a.get("count", 0),
                "count_b": b.get("count", 0),
                "count_diff": b.get("count", 0) - a.get("count", 0),
                "pct_selections_a": a.get("percentage_of_selections", 0),
                "pct_selections_b": b.get("percentage_of_selections", 0),
                "pct_selections_diff": round(
                    b.get("percentage_of_selections", 0) - a.get("percentage_of_selections", 0), 2
                ),
            })
        diff.sort(key=lambda x: abs(x["count_diff"]), reverse=True)
        base.update({
            "response_count_a": sa.get("response_count", 0),
            "response_count_b": sb.get("response_count", 0),
            "total_selections_a": sa.get("total_selections", 0),
            "total_selections_b": sb.get("total_selections", 0),
            "avg_per_response_a": sa.get("avg_selections_per_response", 0),
            "avg_per_response_b": sb.get("avg_selections_per_response", 0),
            "diff": diff,
        })

    elif stype == "crosstab":
        base.update({
            "note": "Full crosstab rows provided — compare cells manually.",
            "rows_a": sa.get("rows", []),
            "rows_b": sb.get("rows", []),
        })

    elif stype == "segment":
        base.update({
            "segment_count_a": sa.get("segment_count", 0),
            "segment_count_b": sb.get("segment_count", 0),
            "segment_diff": sb.get("segment_count", 0) - sa.get("segment_count", 0),
        })

    return base


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@analysis_bp.post("")
@require_auth(allowed_roles=["admin", "analyst"])
def create_definition():
    """Store a new analysis definition."""
    body = request.get_json(silent=True)
    if not body:
        return _err("Request body must be valid JSON")
    if "steps" not in body or not isinstance(body["steps"], list):
        return _err("Analysis definition must contain a 'steps' array")

    now = datetime.now(timezone.utc)
    body["created_at"] = now
    body["updated_at"] = now
    body["organization_id"] = g.user.get("organization_id")

    result = _definitions_col().insert_one(body)
    definition_id = str(result.inserted_id)
    body["_id"] = definition_id

    # Auto-indexing
    try:
        db = current_app.extensions["db"]
        indexed = ensure_analysis_indexes(db, body)
        if indexed:
            body["auto_indexed_fields"] = indexed
    except Exception as e:
        current_app.logger.error(f"Auto-indexing failed: {e}")

    if body.get("schedule"):
        try:
            register_schedule(definition_id, body["schedule"], *_cfg_schedule_args())
        except ValueError as e:
            body["schedule_warning"] = str(e)

    return _json_response(data=body, message="Analysis definition created", status=201)


@analysis_bp.get("")
@require_auth(allowed_roles=["admin", "analyst", "viewer"])
def list_definitions():
    """List all stored definitions for the user's organization."""
    org_id = g.user.get("organization_id")
    projection = {
        "name": 1, "description": 1, "form_id": 1,
        "source_collection": 1, "schedule": 1,
        "created_at": 1, "updated_at": 1,
        "organization_id": 1
    }
    docs = list(_definitions_col().find({"organization_id": org_id}, projection).sort("created_at", -1))
    for d in docs:
        d["_id"] = str(d["_id"])
    return _json_response(data=docs)


@analysis_bp.get("/scheduled")
@require_auth(allowed_roles=["admin", "analyst"])
def list_scheduled():
    """List all currently active scheduled jobs."""
    # Since jobs are scheduled at app level, we show all, but we could filter if we mapped job IDs.
    # For now, listing active job metadata is permitted for admin/analysts.
    return _json_response(data=list_scheduled_jobs())


@analysis_bp.get("/<definition_id>")
@require_auth(allowed_roles=["admin", "analyst", "viewer"])
def get_definition(definition_id: str):
    """Get one full analysis definition belonging to the user's organization."""
    try:
        oid = _parse_oid(definition_id)
    except ValueError as e:
        return _err(str(e))

    org_id = g.user.get("organization_id")
    doc = _definitions_col().find_one({"_id": oid, "organization_id": org_id})
    if not doc:
        return _err("Analysis definition not found", 404)
    return _json_response(data=_stringify(doc))


@analysis_bp.put("/<definition_id>")
@require_auth(allowed_roles=["admin", "analyst"])
def update_definition(definition_id: str):
    """Replace an existing analysis definition."""
    try:
        oid = _parse_oid(definition_id)
    except ValueError as e:
        return _err(str(e))

    body = request.get_json(silent=True)
    if not body:
        return _err("Request body must be valid JSON")

    body.pop("_id", None)
    org_id = g.user.get("organization_id")
    body["organization_id"] = org_id
    body["updated_at"] = datetime.now(timezone.utc)

    doc = _definitions_col().find_one_and_update(
        {"_id": oid, "organization_id": org_id}, {"$set": body}, return_document=True,
    )
    if not doc:
        return _err("Analysis definition not found", 404)

    # Auto-indexing
    try:
        db = current_app.extensions["db"]
        indexed = ensure_analysis_indexes(db, doc)
        if indexed:
            doc["auto_indexed_fields"] = indexed
    except Exception as e:
        current_app.logger.error(f"Auto-indexing failed: {e}")

    # Evict cache
    delete_cached_result(current_app.config.get("REDIS_URL"), definition_id)

    try:
        register_schedule(definition_id, doc.get("schedule", {}), *_cfg_schedule_args())
    except ValueError as e:
        doc["schedule_warning"] = str(e)

    return _json_response(data=_stringify(doc), message="Analysis definition updated")


@analysis_bp.delete("/<definition_id>")
@require_auth(allowed_roles=["admin"])
def delete_definition(definition_id: str):
    """Delete an analysis definition, its schedule, and its result history."""
    try:
        oid = _parse_oid(definition_id)
    except ValueError as e:
        return _err(str(e))

    org_id = g.user.get("organization_id")
    result = _definitions_col().delete_one({"_id": oid, "organization_id": org_id})
    if result.deleted_count == 0:
        return _err("Analysis definition not found", 404)

    deregister_schedule(definition_id)
    delete_cached_result(current_app.config.get("REDIS_URL"), definition_id)
    _results_col().delete_many({"definition_id": oid})
    return _json_response(message="Analysis definition and its results deleted")


# ---------------------------------------------------------------------------
# Run analysis
# ---------------------------------------------------------------------------

@analysis_bp.post("/run")
@require_api_key
def run_adhoc():
    """Run an analysis definition supplied in the request body (not stored)."""
    body = request.get_json(silent=True)
    if not body or "steps" not in body:
        return _err("Body must be a valid analysis definition JSON with a 'steps' array")

    try:
        db = current_app.extensions["db"]
        result = run_analysis(db, body)
    except ValueError as e:
        return _err(str(e))
    except Exception as e:
        return _err(f"Analysis failed: {e}", 500)

    return _json_response(data=result)


@analysis_bp.post("/<definition_id>/run")
@require_auth(allowed_roles=["admin", "analyst"])
def run_stored(definition_id: str):
    """
    Run a stored analysis definition.

    Query params:
      use_cache=true   →  return the latest cached result without re-querying
      async=true       →  offload run to the background queue

    Optional body:
      { "extra_filters": [...] }   →  additional filters merged at run-time
    """
    try:
        oid = _parse_oid(definition_id)
    except ValueError as e:
        return _err(str(e))

    org_id = g.user.get("organization_id")
    doc = _definitions_col().find_one({"_id": oid, "organization_id": org_id})
    if not doc:
        return _err("Analysis definition not found", 404)

    # --- Cache shortcut ---
    use_cache = request.args.get("use_cache", "false").lower() in ("true", "1", "yes")
    redis_url = current_app.config.get("REDIS_URL")
    
    if use_cache:
        # Try Redis Cache first
        cached_result = get_cached_result(redis_url, definition_id)
        if cached_result:
            return _json_response(data={"source": "cache_redis", "result": cached_result})
            
        # Try Mongo cache next
        cached = _results_col().find_one(
            {"definition_id": oid}, sort=[("run_at", -1)],
        )
        if cached:
            cached["_id"] = str(cached["_id"])
            cached["definition_id"] = str(cached["definition_id"])
            # Populate Redis cache for future reads
            if "result" in cached:
                set_cached_result(redis_url, definition_id, cached["result"])
            return _json_response(data={"source": "cache_mongo", "cached_result": cached})

    # --- Live run ---
    body = request.get_json(silent=True) or {}
    extra_filters = body.get("extra_filters", [])
    if extra_filters:
        doc.setdefault("filters", [])
        doc["filters"].extend(extra_filters)

    # Enforce Multi-Tenant Isolation by appending user's organization_id to filters
    doc.setdefault("filters", [])
    doc["filters"].append({"field": "organization_id", "operator": "eq", "value": org_id})

    # --- Async execution queue ---
    run_async = request.args.get("async", "false").lower() in ("true", "1", "yes")
    if run_async:
        cfg = current_app.config
        job_id = enqueue_analysis_run(
            redis_url,
            definition_id,
            cfg["MONGO_URI"],
            cfg["MONGO_DB_NAME"],
            cfg["ANALYSIS_DEFINITIONS_COLLECTION"],
            cfg["ANALYSIS_RESULTS_COLLECTION"],
            cfg["WEBHOOKS_COLLECTION"],
            extra_filters=extra_filters
        )
        return _json_response(
            data={"status": "queued", "job_id": job_id, "check_status_url": f"/api/analysis/jobs/{job_id}"},
            message="Analysis task queued in background.",
            status=202
        )

    # --- Synchronous execution ---
    try:
        db = current_app.extensions["db"]
        result = run_analysis(db, doc)
    except ValueError as e:
        _fire_webhooks_safe(oid, doc.get("name", ""), None, "failed", str(e))
        return _err(str(e))
    except Exception as e:
        _fire_webhooks_safe(oid, doc.get("name", ""), None, "failed", str(e))
        return _err(f"Analysis failed: {e}", 500)

    _save_result(oid, result, trigger="manual", extra_filters=extra_filters)
    set_cached_result(redis_url, definition_id, result)
    _fire_webhooks_safe(oid, doc.get("name", ""), result, "success")

    return _json_response(data={"source": "live", "result": result})


# ---------------------------------------------------------------------------
# Schedule management
# ---------------------------------------------------------------------------

@analysis_bp.post("/<definition_id>/schedule")
@require_api_key
def set_schedule(definition_id: str):
    """
    Enable or update the cron schedule.

    Body:
      {
        "enabled":  true,
        "cron":     "0 8 * * 1",        // every Monday 08:00
        "timezone": "Asia/Kolkata"       // optional, default UTC
      }
    """
    try:
        oid = _parse_oid(definition_id)
    except ValueError as e:
        return _err(str(e))

    schedule_cfg = request.get_json(silent=True)
    if not schedule_cfg or "enabled" not in schedule_cfg:
        return _err("Body must contain at least { 'enabled': true/false }")

    if not _definitions_col().find_one({"_id": oid}):
        return _err("Analysis definition not found", 404)

    _definitions_col().update_one(
        {"_id": oid},
        {"$set": {"schedule": schedule_cfg, "updated_at": datetime.now(timezone.utc)}},
    )

    try:
        register_schedule(definition_id, schedule_cfg, *_cfg_schedule_args())
    except ValueError as e:
        return _err(str(e))

    jobs = list_scheduled_jobs()
    job = next((j for j in jobs if definition_id in j["job_id"]), None)
    return _json_response(
        data={"schedule": schedule_cfg, "next_run": job["next_run"] if job else None},
        message="Schedule updated",
    )


@analysis_bp.delete("/<definition_id>/schedule")
@require_api_key
def remove_schedule(definition_id: str):
    """Disable the cron schedule."""
    try:
        oid = _parse_oid(definition_id)
    except ValueError as e:
        return _err(str(e))

    _definitions_col().update_one(
        {"_id": oid},
        {"$set": {"schedule.enabled": False, "updated_at": datetime.now(timezone.utc)}},
    )
    deregister_schedule(definition_id)
    return _json_response(message="Schedule disabled")


# ---------------------------------------------------------------------------
# Result history
# ---------------------------------------------------------------------------

@analysis_bp.get("/<definition_id>/results")
@require_api_key
def list_results(definition_id: str):
    """Paginated run history (no full result body — use /latest to get data)."""
    try:
        oid = _parse_oid(definition_id)
    except ValueError as e:
        return _err(str(e))

    limit = min(int(request.args.get("limit", 20)), 100)
    skip  = int(request.args.get("skip", 0))

    projection = {"definition_id": 1, "run_at": 1, "trigger": 1, "extra_filters": 1}
    docs = list(
        _results_col()
        .find({"definition_id": oid}, projection)
        .sort("run_at", -1).skip(skip).limit(limit)
    )
    total = _results_col().count_documents({"definition_id": oid})
    for d in docs:
        d["_id"] = str(d["_id"])
        d["definition_id"] = str(d["definition_id"])

    return _json_response(data={"total": total, "skip": skip, "limit": limit, "runs": docs})


@analysis_bp.get("/<definition_id>/results/latest")
@require_api_key
def get_latest_result(definition_id: str):
    """Return the most recently cached result."""
    try:
        oid = _parse_oid(definition_id)
    except ValueError as e:
        return _err(str(e))

    doc = _results_col().find_one({"definition_id": oid}, sort=[("run_at", -1)])
    if not doc:
        return _err("No cached results found. Run the analysis first.", 404)

    doc["_id"] = str(doc["_id"])
    doc["definition_id"] = str(doc["definition_id"])
    return _json_response(data=doc)


@analysis_bp.delete("/<definition_id>/results")
@require_api_key
def clear_results(definition_id: str):
    """Delete all cached run results for this definition."""
    try:
        oid = _parse_oid(definition_id)
    except ValueError as e:
        return _err(str(e))

    r = _results_col().delete_many({"definition_id": oid})
    return _json_response(message=f"{r.deleted_count} result(s) deleted")


# ---------------------------------------------------------------------------
# Comparison  ← NEW
# ---------------------------------------------------------------------------

@analysis_bp.get("/<definition_id>/results/compare/latest")
@require_api_key
def compare_latest_two(definition_id: str):
    """
    Compare the two most recent runs of this analysis side-by-side.
    At least two runs must exist (run the analysis twice with different data or timeframes).
    """
    try:
        oid = _parse_oid(definition_id)
    except ValueError as e:
        return _err(str(e))

    runs = list(
        _results_col()
        .find({"definition_id": oid}, sort=[("run_at", -1)])
        .limit(2)
    )
    if len(runs) < 2:
        return _err("Need at least 2 runs to compare. Run the analysis again first.", 404)

    run_b, run_a = runs[0], runs[1]  # run_b is newer
    return _build_comparison_response(run_a, run_b)


@analysis_bp.get("/<definition_id>/results/compare")
@require_api_key
def compare_two_runs(definition_id: str):
    """
    Compare two specific runs by their result document IDs.

    Query params:
      run_a=<result_id>   (earlier / baseline)
      run_b=<result_id>   (later / comparison)
    """
    try:
        oid = _parse_oid(definition_id)
    except ValueError as e:
        return _err(str(e))

    raw_a = request.args.get("run_a")
    raw_b = request.args.get("run_b")
    if not raw_a or not raw_b:
        return _err("Provide both ?run_a=<id>&run_b=<id>  (or use /compare/latest)")

    try:
        oid_a = _parse_oid(raw_a)
        oid_b = _parse_oid(raw_b)
    except ValueError as e:
        return _err(str(e))

    run_a = _results_col().find_one({"_id": oid_a, "definition_id": oid})
    run_b = _results_col().find_one({"_id": oid_b, "definition_id": oid})

    if not run_a:
        return _err(f"Run '{raw_a}' not found for this definition", 404)
    if not run_b:
        return _err(f"Run '{raw_b}' not found for this definition", 404)

    return _build_comparison_response(run_a, run_b)


def _build_comparison_response(run_a: dict, run_b: dict):
    result_a = run_a.get("result", {})
    result_b = run_b.get("result", {})

    comparison = _compare_steps(result_a, result_b)

    return _json_response(data={
        "analysis_name": result_a.get("name", ""),
        "run_a": {
            "_id": str(run_a["_id"]),
            "run_at": run_a.get("run_at"),
            "trigger": run_a.get("trigger"),
            "total_responses": result_a.get("total_matching_responses"),
        },
        "run_b": {
            "_id": str(run_b["_id"]),
            "run_at": run_b.get("run_at"),
            "trigger": run_b.get("trigger"),
            "total_responses": result_b.get("total_matching_responses"),
        },
        "response_diff": (
            (result_b.get("total_matching_responses") or 0) -
            (result_a.get("total_matching_responses") or 0)
        ),
        "comparison": comparison,
    })


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

@analysis_bp.get("/<definition_id>/results/latest/export")
@require_api_key
def export_latest(definition_id: str):
    """
    Export the latest cached result.
    Query param:  format=csv (default)  |  format=pdf
    """
    try:
        oid = _parse_oid(definition_id)
    except ValueError as e:
        return _err(str(e))

    fmt = request.args.get("format", "csv").lower()
    if fmt not in ("csv", "pdf"):
        return _err("'format' must be 'csv' or 'pdf'")

    doc = _results_col().find_one({"definition_id": oid}, sort=[("run_at", -1)])
    if not doc:
        return _err("No cached results. Run the analysis first.", 404)

    result = doc.get("result", {})
    slug = result.get("name", "analysis").replace(" ", "_").lower()

    if fmt == "csv":
        return Response(
            stream_csv_generator(result), status=200, mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={slug}.csv"},
        )
    else:
        try:
            data = export_to_pdf(result)
        except RuntimeError as e:
            return _err(str(e), 500)
        return Response(
            data, status=200, mimetype="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={slug}.pdf"},
        )


# ---------------------------------------------------------------------------
# Background Job Status
# ---------------------------------------------------------------------------

@analysis_bp.get("/jobs/<job_id>")
@require_api_key
def get_job_info(job_id: str):
    """Retrieve status of an async analysis task."""
    redis_url = current_app.config.get("REDIS_URL")
    status_info = get_job_status(redis_url, job_id)
    return _json_response(data=status_info)

