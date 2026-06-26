import os
import hashlib
import hmac
import jwt
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify
from pymongo import MongoClient

JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-key-change-in-prod")
PASSWORD_SALT = os.getenv("PASSWORD_SALT", "secure-system-salt-key-change").encode()
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("DB_NAME", "form_builder_db")

# Setup db client within auth to avoid circular dependencies with app.py
client = MongoClient(MONGO_URI)
db = client[DB_NAME]

class AuthManager:
    @staticmethod
    def hash_password(password):
        """
        Hashes password securely using PBKDF2 HMAC SHA-256.
        """
        pwd_hash = hashlib.pbkdf2_hmac(
            "sha256", 
            password.encode("utf-8"), 
            PASSWORD_SALT, 
            100000
        )
        return pwd_hash.hex()

    @staticmethod
    def verify_password(password, hashed_pwd):
        return hmac.compare_digest(AuthManager.hash_password(password), hashed_pwd)

    @staticmethod
    def generate_tokens(user_id, organization_id, roles):
        """
        Generates short-lived Access Token and long-lived Refresh Token.
        """
        access_payload = {
            "user_id": str(user_id),
            "organization_id": str(organization_id),
            "roles": roles,
            "exp": datetime.utcnow() + timedelta(minutes=15)
        }
        
        refresh_payload = {
            "user_id": str(user_id),
            "organization_id": str(organization_id),
            "exp": datetime.utcnow() + timedelta(days=7)
        }

        access_token = jwt.encode(access_payload, JWT_SECRET, algorithm="HS256")
        refresh_token = jwt.encode(refresh_payload, JWT_SECRET, algorithm="HS256")
        
        return access_token, refresh_token

    @staticmethod
    def verify_token(token):
        try:
            return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        except Exception:
            return None


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # Allow testing bypass if REQUIRE_AUTH environment variable is not explicitly true
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            if os.getenv("REQUIRE_AUTH") != "true":
                request.user_context = {
                    "user_id": "test_user_id",
                    "organization_id": "default_org",
                    "roles": ["Admin"]
                }
                return f(*args, **kwargs)
            return jsonify({"error": "Authorization token required"}), 401
        
        token = auth_header.split(" ")[1]
        payload = AuthManager.verify_token(token)
        if not payload:
            return jsonify({"error": "Invalid or expired token"}), 401
        
        request.user_context = payload
        return f(*args, **kwargs)
    return decorated


def roles_required(allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            # If REQUIRE_AUTH not true, bypass
            if os.getenv("REQUIRE_AUTH") != "true":
                return f(*args, **kwargs)
                
            user_ctx = getattr(request, "user_context", None)
            if not user_ctx:
                return jsonify({"error": "Authentication context missing"}), 401
            
            user_roles = user_ctx.get("roles", [])
            # If the user is an Admin, they can access anything
            if "Admin" in user_roles:
                return f(*args, **kwargs)
                
            if not any(role in user_roles for role in allowed_roles):
                return jsonify({"error": "Access denied. Insufficient permissions"}), 403
            
            return f(*args, **kwargs)
        return decorated
    return decorator
