"""
webhook_dispatcher.py
---------------------
Fire HTTP webhooks after analysis runs.

Webhook document structure (stored in MongoDB 'webhooks' collection):
{
  "name": "My Slack Bot",
  "url": "https://hooks.slack.com/services/...",
  "type": "generic" | "slack" | "teams",
  "events": ["run_complete", "run_failed"],
  "analysis_ids": [],    // empty list = global (fires for ALL analyses)
                         // or list of specific ObjectIds to scope it
  "active": true,
  "created_at": ...,
  "last_fired_at": ...,
  "last_status": "success" | "error",
  "last_error": null,
}
"""

from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
import os
from datetime import datetime, timezone

from bson import ObjectId
from redis import Redis
from rq import Queue, Retry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fire_webhooks(
    webhooks_col,
    definition_id: str | ObjectId,
    analysis_name: str,
    result: dict | None,
    run_status: str = "success",   # "success" | "failed"
    error: str | None = None,
):
    """
    Find all active webhooks relevant to this analysis and fire them.
    Errors are logged but never raised (webhooks must not break the main flow).

    Webhooks are matched if:
      - analysis_ids is empty (global webhook), OR
      - analysis_ids contains this definition's ObjectId
    """
    oid = ObjectId(definition_id) if isinstance(definition_id, str) else definition_id
    event = "run_complete" if run_status == "success" else "run_failed"

    webhooks = list(webhooks_col.find({
        "active": True,
        "events": event,
        "$or": [
            {"analysis_ids": {"$size": 0}},   # global
            {"analysis_ids": oid},              # scoped to this analysis
        ],
    }))

    for wh in webhooks:
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            try:
                r = Redis.from_url(redis_url)
                q = Queue("webhooks", connection=r)
                
                mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/form_analyser")
                db_name = os.getenv("MONGO_DB_NAME", "form_analyser")
                
                from tasks import fire_webhook_task
                
                q.enqueue(
                    fire_webhook_task,
                    args=(
                        str(wh["_id"]),
                        mongo_uri,
                        db_name,
                        webhooks_col.name,
                        analysis_name,
                        result,
                        run_status,
                        error
                    ),
                    retry=Retry(max=5, interval=[60, 300, 900, 1800, 3600]),
                    job_timeout="2m"
                )
                logger.info(f"Queued background webhook task for '{wh.get('name')}'")
                continue
            except Exception as e:
                logger.error(f"Failed to queue webhook task for '{wh.get('name')}': {e}. Falling back to sync.")

        _fire_one(wh, webhooks_col, analysis_name, result, run_status, error)


def send_test_webhook(webhook_doc: dict) -> dict:
    """
    Send a test payload to a webhook URL immediately.
    Returns {"ok": True} or {"ok": False, "error": "..."}.
    """
    try:
        _dispatch(
            webhook_doc["url"],
            webhook_doc.get("type", "generic"),
            "Test Analysis",
            {"name": "Test Analysis", "total_matching_responses": 42, "results": {}},
            "success",
            None,
        )
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _fire_one(webhook: dict, webhooks_col, analysis_name: str,
              result: dict | None, run_status: str, error: str | None):
    fire_status = "success"
    fire_error = None
    try:
        _dispatch(
            webhook["url"],
            webhook.get("type", "generic"),
            analysis_name, result, run_status, error,
        )
        logger.info(f"Webhook '{webhook.get('name')}' fired OK.")
    except Exception as exc:
        fire_status = "error"
        fire_error = str(exc)
        logger.warning(f"Webhook '{webhook.get('name')}' failed: {exc}")

    try:
        webhooks_col.update_one(
            {"_id": webhook["_id"]},
            {"$set": {
                "last_fired_at": datetime.now(timezone.utc),
                "last_status": fire_status,
                "last_error": fire_error,
            }},
        )
    except Exception:
        pass


def _dispatch(url: str, wtype: str, analysis_name: str,
              result: dict | None, run_status: str, error: str | None):
    if wtype == "slack":
        payload = _slack_payload(analysis_name, result, run_status, error)
    elif wtype == "teams":
        payload = _teams_payload(analysis_name, result, run_status, error)
    else:
        payload = _generic_payload(analysis_name, result, run_status, error)

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "FormAnalyser-Webhook/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        if resp.status >= 400:
            raise RuntimeError(f"Webhook endpoint returned HTTP {resp.status}")


# ---------------------------------------------------------------------------
# Payload formatters
# ---------------------------------------------------------------------------

def _generic_payload(name: str, result: dict | None,
                     run_status: str, error: str | None) -> dict:
    total = result.get("total_matching_responses", 0) if result else 0
    return {
        "event": "run_complete" if run_status == "success" else "run_failed",
        "status": run_status,
        "analysis_name": name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_matching_responses": total,
        "error": error,
        "summary": _build_summary(result) if result else None,
    }


def _slack_payload(name: str, result: dict | None,
                   run_status: str, error: str | None) -> dict:
    icon = "✅" if run_status == "success" else "❌"
    total = result.get("total_matching_responses", 0) if result else 0

    lines = [f"{icon} *{name}* — run {'completed' if run_status == 'success' else 'failed'}"]
    if run_status == "success":
        lines.append(f">Responses analysed: *{total}*")
        for item in _build_summary(result)[:5] if result else []:
            lines.append(f">{item}")
    else:
        lines.append(f">Error: _{error}_")

    return {"text": "\n".join(lines), "unfurl_links": False}


def _teams_payload(name: str, result: dict | None,
                   run_status: str, error: str | None) -> dict:
    """Microsoft Teams Incoming Webhook (legacy MessageCard format)."""
    color = "00cc00" if run_status == "success" else "cc0000"
    total = result.get("total_matching_responses", 0) if result else 0
    status_text = "Completed ✅" if run_status == "success" else f"Failed ❌: {error}"

    facts = [{"name": "Status", "value": status_text}]
    if run_status == "success":
        facts.append({"name": "Responses", "value": str(total)})
        for item in _build_summary(result)[:5] if result else []:
            facts.append({"name": "—", "value": item})

    return {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "themeColor": color,
        "summary": f"Analysis: {name}",
        "sections": [{
            "activityTitle": f"📊 {name}",
            "activitySubtitle": "Form Analyser",
            "facts": facts,
        }],
    }


def _build_summary(result: dict) -> list[str]:
    """Build a short bullet-point list summarising key step results."""
    lines = []
    for step_id, step in result.get("results", {}).items():
        label = step.get("label", step_id)
        stype = step.get("type")
        if stype == "frequency":
            top = (step.get("breakdown") or [{}])[0]
            lines.append(f"{label}: '{top.get('value')}' → {top.get('percentage', 0):.1f}%")
        elif stype == "aggregate":
            val = step.get("result")
            val_str = f"{val:.2f}" if isinstance(val, float) else str(val)
            lines.append(f"{label}: {val_str}")
        elif stype == "top_n":
            top = (step.get("top") or [{}])[0]
            lines.append(f"{label}: '{top.get('value')}' ({top.get('count')} times)")
    return lines
