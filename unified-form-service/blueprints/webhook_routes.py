"""
blueprints/webhook_routes.py
-----------------------------
Webhook management routes.

  POST   /api/webhooks              Create a webhook
  GET    /api/webhooks              List all webhooks
  GET    /api/webhooks/<id>         Get one webhook
  PUT    /api/webhooks/<id>         Update a webhook
  DELETE /api/webhooks/<id>         Delete a webhook
  POST   /api/webhooks/<id>/test    Send a test payload to the webhook URL

Webhook types:
  "generic"  →  plain JSON POST  (works with any HTTP endpoint)
  "slack"    →  Slack Incoming Webhook format
  "teams"    →  Microsoft Teams MessageCard format
"""

from __future__ import annotations

from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, current_app, jsonify, request

from analyser_auth import require_api_key
from webhook_dispatcher import send_test_webhook

webhooks_bp = Blueprint("webhooks", __name__, url_prefix="/api/v1/webhooks")


def _col():
    return current_app.extensions["webhooks_col"]


def _ok(data=None, message="OK", status=200):
    payload = {"status": "success", "message": message}
    if data is not None:
        payload["data"] = data
    return jsonify(payload), status


def _err(message, status=400):
    return jsonify({"status": "error", "message": message}), status


def _stringify(doc):
    if doc:
        doc["_id"] = str(doc["_id"])
        doc["analysis_ids"] = [str(i) for i in doc.get("analysis_ids", [])]
    return doc


def _parse_oid(raw):
    try:
        return ObjectId(raw)
    except (InvalidId, TypeError):
        raise ValueError(f"'{raw}' is not a valid ID")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@webhooks_bp.post("")
@require_api_key
def create_webhook():
    """
    Create a new webhook.

    Body:
    {
      "name":         "Slack Notifications",       // required
      "url":          "https://hooks.slack.com/...", // required
      "type":         "slack",                      // generic | slack | teams
      "events":       ["run_complete", "run_failed"], // which events trigger it
      "analysis_ids": [],     // [] = global (fires for ALL analyses)
                              // or list of analysis definition IDs to scope it
    }
    """
    body = request.get_json(silent=True)
    if not body:
        return _err("Request body must be valid JSON")
    if not body.get("name"):
        return _err("'name' is required")
    if not body.get("url"):
        return _err("'url' is required")

    wtype = body.get("type", "generic")
    if wtype not in ("generic", "slack", "teams"):
        return _err("'type' must be 'generic', 'slack', or 'teams'")

    # Convert string IDs to ObjectIds
    raw_ids = body.get("analysis_ids", [])
    try:
        analysis_oids = [ObjectId(i) for i in raw_ids]
    except Exception:
        return _err("'analysis_ids' contains an invalid ObjectId")

    valid_events = {"run_complete", "run_failed"}
    events = body.get("events", ["run_complete"])
    if not all(e in valid_events for e in events):
        return _err(f"'events' must only contain: {sorted(valid_events)}")

    doc = {
        "name": body["name"],
        "url": body["url"],
        "type": wtype,
        "events": events,
        "analysis_ids": analysis_oids,
        "active": body.get("active", True),
        "created_at": datetime.now(timezone.utc),
        "last_fired_at": None,
        "last_status": None,
        "last_error": None,
    }
    result = _col().insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    doc["analysis_ids"] = [str(i) for i in analysis_oids]

    return _ok(data=doc, message="Webhook created", status=201)


@webhooks_bp.get("")
@require_api_key
def list_webhooks():
    """List all webhooks."""
    docs = list(_col().find({}).sort("created_at", -1))
    for d in docs:
        _stringify(d)
    return _ok(data=docs)


@webhooks_bp.get("/<webhook_id>")
@require_api_key
def get_webhook(webhook_id: str):
    """Get one webhook by ID."""
    try:
        oid = _parse_oid(webhook_id)
    except ValueError as e:
        return _err(str(e))

    doc = _col().find_one({"_id": oid})
    if not doc:
        return _err("Webhook not found", 404)
    return _ok(data=_stringify(doc))


@webhooks_bp.put("/<webhook_id>")
@require_api_key
def update_webhook(webhook_id: str):
    """Update a webhook (name, url, type, events, active, analysis_ids)."""
    try:
        oid = _parse_oid(webhook_id)
    except ValueError as e:
        return _err(str(e))

    body = request.get_json(silent=True)
    if not body:
        return _err("Request body must be valid JSON")

    body.pop("_id", None)
    body.pop("created_at", None)

    # Convert analysis_ids to ObjectIds if provided
    if "analysis_ids" in body:
        try:
            body["analysis_ids"] = [ObjectId(i) for i in body["analysis_ids"]]
        except Exception:
            return _err("'analysis_ids' contains an invalid ObjectId")

    body["updated_at"] = datetime.now(timezone.utc)
    doc = _col().find_one_and_update(
        {"_id": oid}, {"$set": body}, return_document=True,
    )
    if not doc:
        return _err("Webhook not found", 404)

    return _ok(data=_stringify(doc), message="Webhook updated")


@webhooks_bp.delete("/<webhook_id>")
@require_api_key
def delete_webhook(webhook_id: str):
    """Delete a webhook."""
    try:
        oid = _parse_oid(webhook_id)
    except ValueError as e:
        return _err(str(e))

    result = _col().delete_one({"_id": oid})
    if result.deleted_count == 0:
        return _err("Webhook not found", 404)
    return _ok(message="Webhook deleted")


@webhooks_bp.post("/<webhook_id>/test")
@require_api_key
def test_webhook(webhook_id: str):
    """
    Fire a test payload to the webhook URL right now.
    Useful to verify the URL and format work before relying on it.
    """
    try:
        oid = _parse_oid(webhook_id)
    except ValueError as e:
        return _err(str(e))

    doc = _col().find_one({"_id": oid})
    if not doc:
        return _err("Webhook not found", 404)

    result = send_test_webhook(doc)
    if result["ok"]:
        return _ok(message="Test payload delivered successfully.")
    else:
        return _err(f"Test delivery failed: {result['error']}", 502)
