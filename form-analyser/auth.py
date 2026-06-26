"""
auth.py
-------
Authentication and authorization for Form Analyser API.
Supports both standard JWT session tokens and legacy API keys.
Implements Role-Based Access Control (RBAC) and Multi-Tenant Isolation.
"""

from __future__ import annotations
import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from functools import wraps
import jwt
from flask import current_app, jsonify, request, g

# Role Permissions Hierarchy
# admin: can perform all actions
# analyst: can run analyses and create/update definitions
# viewer: can only retrieve/view reports (read-only)
ROLE_PERMISSIONS = {
    "admin": ["admin", "analyst", "viewer"],
    "analyst": ["analyst", "viewer"],
    "viewer": ["viewer"]
}

def generate_api_key() -> str:
    """Generate a new random API key with the 'fa_' prefix."""
    return "fa_" + secrets.token_urlsafe(32)


def hash_key(key: str) -> str:
    """Return the SHA-256 hash of an API key (this is what gets stored)."""
    return hashlib.sha256(key.encode()).hexdigest()


def generate_token(user_id: str, username: str, role: str, organization_id: str) -> str:
    """Generate a JWT token for the user session."""
    secret = current_app.config.get("SECRET_KEY", "dev-secret-key")
    payload = {
        "user_id": user_id,
        "username": username,
        "role": role,
        "organization_id": organization_id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=24)
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_token(token: str) -> dict | None:
    """Decode and verify a JWT token."""
    secret = current_app.config.get("SECRET_KEY", "dev-secret-key")
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def require_auth(allowed_roles: list[str] | None = None):
    """
    Unified decorator that accepts JWT session tokens or API keys.
    Attaches user context (g.user) for multi-tenant data isolation.
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            # Bypass if auth is disabled (useful for local dev)
            if not current_app.config.get("AUTH_ENABLED", True):
                g.user = {
                    "user_id": "bypass",
                    "username": "bypass",
                    "role": "admin",
                    "organization_id": "bypass_org"
                }
                return f(*args, **kwargs)

            # 1. Try JWT Auth (Authorization: Bearer <token>)
            auth_header = request.headers.get("Authorization", "").strip()
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
                payload = decode_token(token)
                if payload:
                    g.user = payload
                else:
                    return jsonify({"status": "error", "message": "Invalid or expired JWT token"}), 401

            # 2. Try API Key Auth
            else:
                raw_key = request.headers.get("X-API-Key", "").strip()
                if not raw_key:
                    return jsonify({
                        "status": "error",
                        "message": "Authentication required. Provide a Bearer token or X-API-Key header.",
                    }), 401

                keys_col = current_app.extensions["keys_col"]
                doc = keys_col.find_one({
                    "key_hash": hash_key(raw_key),
                    "active": True,
                })
                if not doc:
                    return jsonify({
                        "status": "error",
                        "message": "Invalid or revoked API key.",
                    }), 401

                # API key documents now carry role and organization_id (tenant context)
                g.user = {
                    "user_id": str(doc["_id"]),
                    "username": doc.get("name", "API Key"),
                    "role": doc.get("role", "analyst"),
                    "organization_id": doc.get("organization_id", "default_org")
                }

                # Update last_used_at — fire and forget
                keys_col.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"last_used_at": datetime.now(timezone.utc)}},
                )

            # 3. Check Role Permissions (RBAC)
            if allowed_roles:
                user_role = g.user.get("role", "viewer")
                granted_roles = ROLE_PERMISSIONS.get(user_role, [])
                
                # Check if user's role grants permission for any of the allowed roles
                has_permission = any(r in granted_roles for r in allowed_roles)
                if not has_permission:
                    return jsonify({
                        "status": "error",
                        "message": f"Unauthorized. Role '{user_role}' does not have permission.",
                    }), 403

            return f(*args, **kwargs)
        return decorated
    return decorator


def require_api_key(f):
    """Legacy compatibility decorator for require_api_key."""
    return require_auth()(f)
