"""
tasks.py
--------
Background tasks executed by RQ workers.
"""

from __future__ import annotations
import json
from datetime import datetime, timezone
from bson import ObjectId
from pymongo import MongoClient
from redis import Redis
from analysis_engine import run_analysis
from webhook_dispatcher import fire_webhooks
from json_logger import setup_json_logging

# Enable structured JSON logging in worker process
setup_json_logging()

def run_analysis_task(
    definition_id: str,
    mongo_uri: str,
    db_name: str,
    definitions_col_name: str,
    results_col_name: str,
    webhooks_col_name: str,
    redis_url: str,
    extra_filters: list | None = None
) -> dict:
    """RQ background task to run an analysis and update caches/webhooks."""
    client = MongoClient(mongo_uri)
    db = client[db_name]
    definitions_col = db[definitions_col_name]
    results_col = db[results_col_name]
    webhooks_col = db[webhooks_col_name]

    doc = definitions_col.find_one({"_id": ObjectId(definition_id)})
    if not doc:
        raise ValueError(f"Analysis definition '{definition_id}' not found.")

    if extra_filters:
        doc.setdefault("filters", [])
        doc["filters"].extend(extra_filters)

    # Enforce multi-tenant isolation
    org_id = doc.get("organization_id")
    if org_id:
        doc.setdefault("filters", [])
        doc["filters"].append({"field": "organization_id", "operator": "eq", "value": org_id})

    analysis_name = doc.get("name", definition_id)
    run_at = datetime.now(timezone.utc)

    try:
        result = run_analysis(db, doc)

        # 1. Save to MongoDB result history
        results_col.insert_one({
            "definition_id": ObjectId(definition_id),
            "run_at": run_at,
            "trigger": "async",
            "extra_filters": extra_filters or [],
            "result": result,
        })

        # 2. Save to Redis Cache (for fast read/sub-millisecond retrieval)
        try:
            r = Redis.from_url(redis_url)
            cache_key = f"cache:analysis:{definition_id}"
            r.setex(cache_key, 300, json.dumps(result))
        except Exception:
            pass  # fail-safe for cache failure

        # 3. Fire webhooks
        try:
            fire_webhooks(
                webhooks_col, definition_id, analysis_name,
                result, "success"
            )
        except Exception:
            pass

        return result

    except Exception as exc:
        results_col.insert_one({
            "definition_id": ObjectId(definition_id),
            "run_at": run_at,
            "trigger": "async",
            "extra_filters": extra_filters or [],
            "error": str(exc),
        })

        try:
            fire_webhooks(
                webhooks_col, definition_id, analysis_name,
                None, "failed", str(exc)
            )
        except Exception:
            pass

        raise exc


def fire_webhook_task(
    webhook_id: str,
    mongo_uri: str,
    db_name: str,
    webhooks_col_name: str,
    analysis_name: str,
    result: dict | None,
    run_status: str,
    error: str | None
):
    """Background task to fire a webhook with automatic retries handled by RQ."""
    client = MongoClient(mongo_uri)
    db = client[db_name]
    webhooks_col = db[webhooks_col_name]

    doc = webhooks_col.find_one({"_id": ObjectId(webhook_id)})
    if not doc or not doc.get("active", True):
        return

    from webhook_dispatcher import _dispatch
    
    fire_status = "success"
    fire_error = None
    try:
        _dispatch(
            doc["url"],
            doc.get("type", "generic"),
            analysis_name, result, run_status, error
        )
    except Exception as exc:
        fire_status = "error"
        fire_error = str(exc)
        raise exc
    finally:
        try:
            webhooks_col.update_one(
                {"_id": doc["_id"]},
                {
                    "$set": {
                        "last_fired_at": datetime.now(timezone.utc),
                        "last_status": fire_status,
                        "last_error": fire_error,
                    },
                    "$push": {
                        "delivery_logs": {
                            "$each": [{
                                "timestamp": datetime.now(timezone.utc),
                                "status": fire_status,
                                "error": fire_error
                            }],
                            "$slice": -50  # Keep the last 50 attempts
                        }
                    }
                }
            )
        except Exception:
            pass

