"""
blueprints/response_routes.py
------------------------------
Routes for reading and inserting raw form responses.

  GET  /api/responses            List responses (pagination + simple filter)
  GET  /api/responses/<id>       Get one response
  POST /api/responses            Insert one or many responses (for testing)
"""

from __future__ import annotations

from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, current_app, jsonify, request

from analyser_auth import require_api_key

responses_bp = Blueprint("responses", __name__, url_prefix="/api/v1/responses")


def _col():
    return current_app.extensions["responses_col"]


def _ok(data=None, message="OK", status=200):
    payload = {"status": "success", "message": message}
    if data is not None:
        payload["data"] = data
    return jsonify(payload), status


def _err(message, status=400):
    return jsonify({"status": "error", "message": message}), status


def _stringify(doc: dict) -> dict:
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@responses_bp.get("/")
@require_api_key
def list_responses():
    """
    List form responses.

    Query params:
      limit  (default 50)
      skip   (default 0)
      field  + value  →  simple equality filter  e.g. ?field=answers.region&value=North
    """
    limit = min(int(request.args.get("limit", 50)), 500)
    skip  = int(request.args.get("skip",  0))
    query = {}

    field = request.args.get("field")
    value = request.args.get("value")
    if field and value is not None:
        query[field] = value

    col = _col()
    docs = [_stringify(d) for d in col.find(query).skip(skip).limit(limit)]
    total = col.count_documents(query)

    return _ok(data={"total": total, "skip": skip, "limit": limit, "responses": docs})


@responses_bp.get("/<response_id>")
@require_api_key
def get_response(response_id: str):
    """Get a single form response by its MongoDB _id."""
    try:
        oid = ObjectId(response_id)
    except (InvalidId, TypeError):
        return _err(f"'{response_id}' is not a valid ID")

    doc = _col().find_one({"_id": oid})
    if not doc:
        return _err("Response not found", 404)

    return _ok(data=_stringify(doc))


@responses_bp.post("/")
@require_api_key
def insert_response():
    """
    Insert one or more form responses.
    Body: single response object  OR  array of response objects.
    """
    body = request.get_json(silent=True)
    if not body:
        return _err("Request body must be valid JSON")

    now = datetime.now(timezone.utc)
    col = _col()

    if isinstance(body, list):
        for doc in body:
            doc["inserted_at"] = now
        result = col.insert_many(body)
        return _ok(
            data={"inserted_ids": [str(i) for i in result.inserted_ids]},
            message=f"{len(result.inserted_ids)} response(s) inserted",
            status=201,
        )
    else:
        body["inserted_at"] = now
        result = col.insert_one(body)
        body["_id"] = str(result.inserted_id)
        return _ok(data=body, message="Response inserted", status=201)
