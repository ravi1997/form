"""
blueprints/auth_routes.py
--------------------------
Routes for managing API keys.

  POST   /api/auth/keys          Generate a new API key
  GET    /api/auth/keys          List all keys (metadata — never plaintext)
  DELETE /api/auth/keys/<id>     Revoke a key
"""

from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, current_app, jsonify, request, g
from werkzeug.security import generate_password_hash, check_password_hash

from auth import generate_api_key, hash_key, require_auth, generate_token

auth_bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


def _keys_col():
    return current_app.extensions["keys_col"]


def _users_col():
    return current_app.extensions["users_col"]


def _ok(data=None, message="OK", status=200):
    payload = {"status": "success", "message": message}
    if data is not None:
        payload["data"] = data
    return jsonify(payload), status


def _err(message, status=400):
    return jsonify({"status": "error", "message": message}), status


# ---------------------------------------------------------------------------
# Registration and Login
# ---------------------------------------------------------------------------

@auth_bp.post("/register")
def register():
    """Register a new user inside an organization."""
    body = request.get_json(silent=True) or {}
    username = body.get("username", "").strip()
    password = body.get("password", "").strip()
    organization_id = body.get("organization_id", "").strip()
    role = body.get("role", "viewer").strip().lower()

    if not username or not password or not organization_id:
        return _err("Username, password, and organization_id are required.")

    if role not in ("admin", "analyst", "viewer"):
        return _err("Invalid role. Must be 'admin', 'analyst', or 'viewer'.")

    users_col = _users_col()
    if users_col.find_one({"username": username}):
        return _err("Username already exists.", 409)

    user_doc = {
        "username": username,
        "password_hash": generate_password_hash(password),
        "organization_id": organization_id,
        "role": role,
        "created_at": datetime.now(timezone.utc)
    }
    result = users_col.insert_one(user_doc)

    return _ok(
        data={
            "user_id": str(result.inserted_id),
            "username": username,
            "organization_id": organization_id,
            "role": role
        },
        message="User registered successfully",
        status=201
    )


@auth_bp.post("/login")
def login():
    """Authenticate user and return a JWT token."""
    body = request.get_json(silent=True) or {}
    username = body.get("username", "").strip()
    password = body.get("password", "").strip()

    if not username or not password:
        return _err("Username and password are required.")

    users_col = _users_col()
    user = users_col.find_one({"username": username})

    if not user or not check_password_hash(user["password_hash"], password):
        return _err("Invalid username or password.", 401)

    token = generate_token(
        str(user["_id"]),
        user["username"],
        user["role"],
        user["organization_id"]
    )

    return _ok(
        data={
            "token": token,
            "username": user["username"],
            "role": user["role"],
            "organization_id": user["organization_id"]
        },
        message="Login successful"
    )


# ---------------------------------------------------------------------------
# API Key Management (Protected)
# ---------------------------------------------------------------------------

@auth_bp.post("/keys")
@require_auth(allowed_roles=["admin", "analyst"])
def create_key():
    """
    Generate a new API key within the user's organization.

    Body options:
      { "name": "Integration Key", "description": "...", "role": "analyst" }
    """
    body = request.get_json(silent=True) or {}
    plaintext = generate_api_key()

    req_role = body.get("role", "analyst").strip().lower()
    if req_role not in ("admin", "analyst", "viewer"):
        return _err("Invalid role. Must be 'admin', 'analyst', or 'viewer'.")

    # Prevent escalation: User can't generate a key with a role stronger than their own
    current_role = g.user.get("role")
    if current_role == "analyst" and req_role == "admin":
        return _err("Analysts cannot create Admin API keys.", 403)

    doc = {
        "name": body.get("name", "Unnamed Key"),
        "description": body.get("description", ""),
        "key_hash": hash_key(plaintext),
        "active": True,
        "role": req_role,
        "organization_id": g.user.get("organization_id"),
        "created_at": datetime.now(timezone.utc),
        "last_used_at": None,
    }
    result = _keys_col().insert_one(doc)

    return _ok(
        data={
            "_id": str(result.inserted_id),
            "name": doc["name"],
            "role": doc["role"],
            "organization_id": doc["organization_id"],
            "key": plaintext,
            "warning": "Save this key now — it will not be shown again.",
        },
        message="API key created",
        status=201,
    )


@auth_bp.get("/keys")
@require_auth(allowed_roles=["admin"])
def list_keys():
    """List all API keys belonging to the user's organization."""
    org_id = g.user.get("organization_id")
    docs = list(_keys_col().find({"organization_id": org_id}, {"key_hash": 0}))
    for d in docs:
        d["_id"] = str(d["_id"])
    return _ok(data=docs)


@auth_bp.delete("/keys/<key_id>")
@require_auth(allowed_roles=["admin"])
def revoke_key(key_id: str):
    """Revoke an API key belonging to the user's organization."""
    try:
        oid = ObjectId(key_id)
    except (InvalidId, TypeError):
        return _err(f"'{key_id}' is not a valid key ID")

    org_id = g.user.get("organization_id")
    result = _keys_col().find_one_and_update(
        {"_id": oid, "organization_id": org_id},
        {"$set": {"active": False}},
    )
    if not result:
        return _err("API key not found or doesn't belong to your organization", 404)

    return _ok(message=f"API key '{result.get('name', key_id)}' revoked")
