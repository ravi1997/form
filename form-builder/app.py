import os
import base64
import uuid
import random
import csv
import io
from datetime import datetime
from bson import ObjectId
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from pymongo import MongoClient
import jwt

from surveyjs_translator import SurveyJSTranslator
from validator import FormSubmissionValidator
from pipeline_engine import PipelineEngine
from s3_helper import S3Helper
from encryption_helper import EncryptionHelper
from anonymizer import DataAnonymizer
from drift_detector import SchemaDriftDetector
from pdf_generator import PDFGenerator
from task_manager import TaskManager

# Import auth helpers
from auth import AuthManager, login_required, roles_required
from git_version_control import GitVersionControl

import logging
logger = logging.getLogger("FormBuilderApp")

app = Flask(__name__)
CORS(app)

# Configuration
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("DB_NAME", "form_builder_db")
JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-key-change-in-prod")
UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "static/uploads")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# DB client (limiting pool sizes to prevent descriptor leaks)
client = MongoClient(MONGO_URI, maxPoolSize=50, minPoolSize=5, waitQueueTimeoutMS=5000)
db = client[DB_NAME]

from collections import defaultdict
import time
from functools import wraps

rate_limit_store = defaultdict(list)

def rate_limit(limit=5, window=60):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            import sys
            if "pytest" in sys.modules or os.getenv("REQUIRE_AUTH") != "true":
                return f(*args, **kwargs)


            ip = request.remote_addr
            now = time.time()
            rate_limit_store[ip] = [t for t in rate_limit_store[ip] if now - t < window]
            
            if len(rate_limit_store[ip]) >= limit:
                return jsonify({"error": "Too many requests. Please try again later."}), 429
                
            rate_limit_store[ip].append(now)
            return f(*args, **kwargs)
        return decorated
    return decorator



# Multi-Tenant dynamic database resolver
ACTIVE_TENANTS = {}  # org_id -> datetime
FROZEN_TENANTS = set()

def ensure_db_indexes(db):
    try:
        db["projects"].create_index([("organization_id", 1)])
        db["projects"].create_index([("created_at", -1)])
        db["forms"].create_index([("project_id", 1)])
        db["forms"].create_index([("organization_id", 1)])
        db["forms"].create_index([("theme_id", 1)])
        db["themes"].create_index([("organization_id", 1)])
        db["responses"].create_index([("form_id", 1), ("submitted_at", -1)])
        db["responses"].create_index([("organization_id", 1)])
        db["responses"].create_index([("form_id", 1), ("status", 1)])
        db["commits"].create_index([("form_id", 1), ("hash", 1)], unique=True)
        db["commits"].create_index([("timestamp", -1)])
    except Exception as e:
        logger.warning(f"Error ensuring indexes on DB {db.name}: {str(e)}")

def freeze_db_indexes(db):
    for col_name in ["projects", "forms", "themes", "responses", "commits"]:
        try:
            db[col_name].drop_indexes()
        except Exception:
            pass

def get_collections():
    org_id = get_organization_id()
    if os.getenv("TENANT_DB_ISOLATION") == "true":
        db_name = f"form_db_{org_id}"
        database = client[db_name]
        
        now = datetime.utcnow()
        is_first_access = org_id not in ACTIVE_TENANTS
        ACTIVE_TENANTS[org_id] = now
        
        if is_first_access or org_id in FROZEN_TENANTS:
            ensure_db_indexes(database)
            FROZEN_TENANTS.discard(org_id)
            
        limit = int(os.getenv("ACTIVE_DB_LIMIT", "5"))
        inactive_timeout = int(os.getenv("DB_INACTIVE_TIMEOUT", "300"))
        
        all_active = sorted(list(ACTIVE_TENANTS.items()), key=lambda x: x[1], reverse=True)
        to_keep_active = set()
        for idx, (oid, last_time) in enumerate(all_active):
            time_diff = (now - last_time).total_seconds()
            if idx < limit and time_diff < inactive_timeout:
                to_keep_active.add(oid)
            else:
                if oid not in FROZEN_TENANTS:
                    freeze_db_indexes(client[f"form_db_{oid}"])
                    FROZEN_TENANTS.add(oid)
                    
        for oid in list(ACTIVE_TENANTS.keys()):
            if oid not in to_keep_active:
                ACTIVE_TENANTS.pop(oid, None)
    else:
        database = client[DB_NAME]
    return database, database["projects"], database["forms"], database["themes"], database["responses"], database["audit_logs"]

# Serializer helper
def json_util_serialize(data):
    if isinstance(data, list):
        return [json_util_serialize(item) for item in data]
    if isinstance(data, dict):
        return {k: json_util_serialize(v) for k, v in data.items()}
    if isinstance(data, ObjectId):
        return str(data)
    if isinstance(data, datetime):
        return data.isoformat()
    return data

def get_organization_id():
    user_ctx = getattr(request, "user_context", None)
    if user_ctx:
        return user_ctx.get("organization_id", "default_org")
        
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            return payload.get("organization_id", "default_org")
        except Exception:
            return "invalid_token"
    return request.args.get("organization_id", "default_org")

def get_user_id():
    user_ctx = getattr(request, "user_context", None)
    if user_ctx:
        return user_ctx.get("user_id", "anonymous_user")
        
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            return payload.get("user_id", "anonymous_user")
        except Exception:
            return "anonymous_user"
    return "anonymous_user"

def get_user_roles():
    user_ctx = getattr(request, "user_context", None)
    if user_ctx:
        return user_ctx.get("roles", [])
        
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            return payload.get("roles", [])
        except Exception:
            return []
    return ["Admin"] if os.getenv("REQUIRE_AUTH") != "true" else []

def merge_response_answers(ancestor_answers, current_answers, client_answers):
    """
    Merges concurrent response edits using a 3-way merge strategy.
    """
    merged = {}
    conflicts = {}
    
    all_keys = set(ancestor_answers.keys()) | set(current_answers.keys()) | set(client_answers.keys())
    
    for key in all_keys:
        in_anc = key in ancestor_answers
        in_curr = key in current_answers
        in_cli = key in client_answers
        
        val_anc = ancestor_answers.get(key)
        val_curr = current_answers.get(key)
        val_cli = client_answers.get(key)
        
        if in_anc:
            modified_curr = in_curr and val_curr != val_anc
            modified_cli = in_cli and val_cli != val_anc
            
            if modified_curr and modified_cli:
                if val_curr == val_cli:
                    merged[key] = val_curr
                else:
                    conflicts[key] = {
                        "ancestor": val_anc,
                        "current_in_db": val_curr,
                        "submitted": val_cli
                    }
            elif modified_curr:
                if in_curr:
                    merged[key] = val_curr
            elif modified_cli:
                if in_cli:
                    merged[key] = val_cli
            else:
                if in_curr and in_cli:
                    merged[key] = val_curr
        else:
            # Added in both or either
            if in_curr and in_cli:
                if val_curr == val_cli:
                    merged[key] = val_curr
                else:
                    conflicts[key] = {
                        "ancestor": None,
                        "current_in_db": val_curr,
                        "submitted": val_cli
                    }
            elif in_curr:
                merged[key] = val_curr
            elif in_cli:
                merged[key] = val_cli
                
    return merged, conflicts

def record_audit_log(action, form_id=None, project_id=None, details=None):
    user_id = get_user_id()
    org_id = get_organization_id()
    _, _, _, _, _, audit_col = get_collections()
    
    log_doc = {
        "user_id": user_id,
        "organization_id": org_id,
        "action": action,
        "form_id": ObjectId(form_id) if isinstance(form_id, str) else form_id,
        "project_id": ObjectId(project_id) if isinstance(project_id, str) else project_id,
        "details": details or {},
        "timestamp": datetime.utcnow()
    }
    audit_col.insert_one(log_doc)

    # Periodically prune old audit logs (older than 90 days) to optimize DB space
    import random
    if random.randint(1, 100) == 1:
        try:
            from datetime import timedelta
            cutoff = datetime.utcnow() - timedelta(days=90)
            audit_col.delete_many({"timestamp": {"$lt": cutoff}})
        except Exception as e:
            logger.warning(f"Failed to auto-prune audit logs: {str(e)}")

def save_base64_image(base64_str):
    try:
        if "," in base64_str:
            header, base64_str_content = base64_str.split(",", 1)
        else:
            base64_str_content = base64_str

        img_data = base64.b64decode(base64_str_content)
        
        # 1. Enforce 5MB limit
        if len(img_data) > 5 * 1024 * 1024:
            raise ValueError("File size exceeds the 5MB security limit.")

        # 2. Magic bytes validation (PNG, JPEG, GIF, PDF)
        allowed_signatures = {
            b'\x89PNG\r\n\x1a\n': 'image/png',
            b'\xff\xd8\xff': 'image/jpeg',
            b'GIF87a': 'image/gif',
            b'GIF89a': 'image/gif',
            b'%PDF-': 'application/pdf'
        }
        
        is_valid_sig = False
        content_type = "image/png"
        ext = "png"
        for sig, mime in allowed_signatures.items():
            if img_data.startswith(sig):
                is_valid_sig = True
                content_type = mime
                ext = mime.split("/")[1]
                break
                
        if not is_valid_sig:
            raise ValueError("Invalid file type signature. Only PNG, JPEG, GIF and PDF files are allowed.")

        filename = f"camera_{uuid.uuid4().hex}.{ext}"
        s3_url = S3Helper.upload_file(img_data, filename, content_type=content_type)
        register_upload(s3_url)
        return s3_url
    except Exception as e:
        raise ValueError(f"Failed to process camera base64: {str(e)}")

def register_upload(filepath, response_id=None):
    try:
        db_ctx, _, _, _, _, _ = get_collections()
        db_ctx["upload_registry"].insert_one({
            "file_path": filepath,
            "response_id": response_id,
            "created_at": datetime.utcnow()
        })
        
        # 1 in 10 chance to prune orphaned uploads older than 24 hours
        if random.randint(1, 10) == 1:
            try:
                from datetime import timedelta
                cutoff = datetime.utcnow() - timedelta(hours=24)
                orphans = list(db_ctx["upload_registry"].find({
                    "created_at": {"$lt": cutoff},
                    "$or": [
                        {"response_id": None},
                        {"response_id": {"$exists": False}}
                    ]
                }))
                if orphans:
                    for o in orphans:
                        S3Helper.delete_file(o["file_path"])
                    db_ctx["upload_registry"].delete_many({
                        "_id": {"$in": [o["_id"] for o in orphans]}
                    })
            except Exception as pe:
                logger.warning(f"Failed to auto-prune orphaned uploads: {str(pe)}")
    except Exception as e:
        logger.warning(f"Failed to register upload {filepath}: {str(e)}")

def link_uploads_to_response(response_id, answers_dict):
    try:
        db_ctx, _, _, _, _, _ = get_collections()
        urls = []
        def extract_urls(val):
            if isinstance(val, str):
                if "uploads" in val or "s3" in val or val.startswith("http") or val.startswith("/static/"):
                    urls.append(val)
            elif isinstance(val, list):
                for item in val:
                    extract_urls(item)
            elif isinstance(val, dict):
                for k, v in val.items():
                    extract_urls(v)
        extract_urls(answers_dict)
        if urls:
            db_ctx["upload_registry"].update_many(
                {"file_path": {"$in": urls}},
                {"$set": {"response_id": response_id}}
            )
    except Exception as e:
        logger.warning(f"Failed to link uploads to response {response_id}: {str(e)}")

def cleanup_discarded_uploads(original_new_answers, final_answers):
    try:
        db_ctx, _, _, _, _, _ = get_collections()
        new_urls = []
        def extract_urls(val):
            if isinstance(val, str):
                if "uploads" in val or "s3" in val or val.startswith("http") or val.startswith("/static/"):
                    new_urls.append(val)
            elif isinstance(val, list):
                for item in val:
                    extract_urls(item)
            elif isinstance(val, dict):
                for k, v in val.items():
                    extract_urls(v)
        extract_urls(original_new_answers)
        
        final_urls = set()
        def extract_final_urls(val):
            if isinstance(val, str):
                if "uploads" in val or "s3" in val or val.startswith("http") or val.startswith("/static/"):
                    final_urls.add(val)
            elif isinstance(val, list):
                for item in val:
                    extract_final_urls(item)
            elif isinstance(val, dict):
                for k, v in val.items():
                    extract_final_urls(v)
        extract_final_urls(final_answers)
        
        discarded_urls = [u for u in new_urls if u not in final_urls]
        if discarded_urls:
            for url in discarded_urls:
                S3Helper.delete_file(url)
            db_ctx["upload_registry"].delete_many({"file_path": {"$in": discarded_urls}})
    except Exception as e:
        logger.warning(f"Failed to cleanup discarded uploads: {str(e)}")

def trigger_lookup_mv_update(db, form_id, org_id, answers):
    try:
        from lookup_resolver import LookupResolver
        for key in answers.keys():
            LookupResolver.update_materialized_view(db, form_id, key, org_id)
    except Exception as e:
        logger.warning(f"Failed to trigger lookup mv update: {str(e)}")

# Permission & ACL check helper
def check_permission(item_type, item_id, required_roles):
    """
    Checks if current request user has permission to access a form or project.
    item_type: 'form' or 'project'
    item_id: ObjectId or string ID
    required_roles: list of allowed roles (e.g. ['Analyst', 'Editor', 'Admin'])
    """
    if os.getenv("REQUIRE_AUTH") != "true":
        return True, None
    
    user_ctx = getattr(request, "user_context", None)
    if not user_ctx:
        return False, (jsonify({"error": "Authentication required"}), 401)
    
    user_id = user_ctx.get("user_id")
    org_id = user_ctx.get("organization_id")
    user_roles = user_ctx.get("roles", [])
    
    # System Admin / Org Admin bypass
    if "Admin" in user_roles:
        return True, None
        
    try:
        obj_id = ObjectId(item_id) if isinstance(item_id, str) else item_id
    except Exception:
        return False, (jsonify({"error": f"Invalid {item_type} ID format"}), 400)
        
    db_ctx, projects_col, forms_col, _, _, _ = get_collections()
    
    item = None
    project_item = None
    if item_type == "form":
        item = forms_col.find_one({"_id": obj_id})
        if item and "project_id" in item:
            # Look up project in db context
            project_item = projects_col.find_one({"_id": item["project_id"]})
    elif item_type == "project":
        item = projects_col.find_one({"_id": obj_id})
        
    if not item:
        return False, (jsonify({"error": f"{item_type.capitalize()} not found"}), 404)
        
    if item.get("organization_id") != org_id:
        return False, (jsonify({"error": "Access denied. Different organization"}), 403)
        
    # Check permissions matching
    shares = item.get("shares", [])
    user_share = next((s for s in shares if s.get("user_id") == user_id or s.get("email") == user_ctx.get("email")), None)
    
    resolved_role = None
    if user_share:
        resolved_role = user_share.get("role")
    elif project_item:
        # Try inheriting from project
        proj_shares = project_item.get("shares", [])
        proj_share = next((s for s in proj_shares if s.get("user_id") == user_id or s.get("email") == user_ctx.get("email")), None)
        if proj_share:
            resolved_role = proj_share.get("role")
            
    if not resolved_role:
        # Fallback to org default based on user system roles
        if "Editor" in user_roles:
            resolved_role = "Editor"
        elif "Analyst" in user_roles:
            resolved_role = "Analyst"
        else:
            resolved_role = "Respondent"
            
    role_priority = {"Admin": 4, "Editor": 3, "Analyst": 2, "Respondent": 1}
    resolved_priority = role_priority.get(resolved_role, 0)
    required_priorities = [role_priority.get(r, 0) for r in required_roles]
    max_required_priority = min(required_priorities) if required_priorities else 0
    
    if resolved_priority >= max_required_priority:
        return True, None
        
    return False, (jsonify({"error": "Insufficient workspace permissions"}), 403)



# ==========================================
# 🔑 IDENTITY & AUTHENTICATION ENDPOINTS
# ==========================================

@app.route("/api/auth/register", methods=["POST"])
@rate_limit(limit=5, window=60)
def register_user():
    data = request.json or {}
    email = data.get("email")
    password = data.get("password")
    first_name = data.get("first_name", "")
    last_name = data.get("last_name", "")
    organization_name = data.get("organization_name", "Acme Corp")
    allowed_email_domains = data.get("allowed_email_domains", [])

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    users_col = client[DB_NAME]["users"]
    orgs_col = client[DB_NAME]["organizations"]

    if users_col.find_one({"email": email}):
        return jsonify({"error": "User with this email already exists"}), 400

    # Create Organization
    org_doc = {
        "name": organization_name,
        "billing_plan": "Enterprise",
        "settings": {
            "allowed_email_domains": allowed_email_domains
        },
        "created_at": datetime.utcnow()
    }
    orgs_col.insert_one(org_doc)
    org_id = str(org_doc["_id"])

    # Create User
    pwd_hash = AuthManager.hash_password(password)
    user_doc = {
        "organization_id": org_id,
        "email": email,
        "password_hash": pwd_hash,
        "first_name": first_name,
        "last_name": last_name,
        "roles": ["Admin"],
        "status": "Active",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    users_col.insert_one(user_doc)
    user_id = str(user_doc["_id"])

    access_token, refresh_token = AuthManager.generate_tokens(user_id, org_id, ["Admin"])

    return jsonify({
        "message": "User registered successfully",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": {
            "id": user_id,
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "roles": ["Admin"]
        },
        "organization": {
            "id": org_id,
            "name": organization_name
        }
    }), 201

@app.route("/api/auth/login", methods=["POST"])
@rate_limit(limit=5, window=60)
def login():
    data = request.json or {}
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    users_col = client[DB_NAME]["users"]
    user = users_col.find_one({"email": email})

    if not user or user.get("status") == "Suspended":
        return jsonify({"error": "Invalid credentials or suspended account"}), 401

    if not AuthManager.verify_password(password, user["password_hash"]):
        return jsonify({"error": "Invalid credentials"}), 401

    orgs_col = client[DB_NAME]["organizations"]
    org = orgs_col.find_one({"_id": ObjectId(user["organization_id"])})
    org_name = org["name"] if org else "Default Org"

    access_token, refresh_token = AuthManager.generate_tokens(
        str(user["_id"]), 
        str(user["organization_id"]), 
        user.get("roles", ["Respondent"])
    )

    return jsonify({
        "message": "Login successful",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": {
            "id": str(user["_id"]),
            "email": user["email"],
            "first_name": user.get("first_name", ""),
            "last_name": user.get("last_name", ""),
            "roles": user.get("roles", ["Respondent"])
        },
        "organization": {
            "id": str(user["organization_id"]),
            "name": org_name
        }
    }), 200

@app.route("/api/auth/refresh", methods=["POST"])
def refresh():
    data = request.json or {}
    refresh_token = data.get("refresh_token")
    if not refresh_token:
        return jsonify({"error": "Refresh token is required"}), 400

    payload = AuthManager.verify_token(refresh_token)
    if not payload:
        return jsonify({"error": "Invalid or expired refresh token"}), 401

    user_id = payload.get("user_id")
    org_id = payload.get("organization_id")
    
    users_col = client[DB_NAME]["users"]
    user = users_col.find_one({"_id": ObjectId(user_id)})
    if not user or user.get("status") == "Suspended":
        return jsonify({"error": "User no longer active"}), 401

    access_token, new_refresh_token = AuthManager.generate_tokens(
        user_id, 
        org_id, 
        user.get("roles", ["Respondent"])
    )

    return jsonify({
        "access_token": access_token,
        "refresh_token": new_refresh_token
    }), 200

@app.route("/api/auth/reset-password", methods=["POST"])
@rate_limit(limit=5, window=60)
def reset_password():
    data = request.json or {}
    email = data.get("email")
    new_password = data.get("new_password")

    if not email or not new_password:
        return jsonify({"error": "Email and new password are required"}), 400

    users_col = client[DB_NAME]["users"]
    user = users_col.find_one({"email": email})
    if not user:
        return jsonify({"error": "User not found"}), 404

    pwd_hash = AuthManager.hash_password(new_password)
    users_col.update_one(
        {"_id": user["_id"]},
        {"$set": {"password_hash": pwd_hash, "updated_at": datetime.utcnow()}}
    )
    
    record_audit_log("reset_password", details={"email": email})
    return jsonify({"message": "Password reset successfully"}), 200



# ==========================================
# 👥 ORGANIZATION USER MANAGEMENT ENDPOINTS
# ==========================================

@app.route("/api/org/users", methods=["GET"])
@login_required
@roles_required(["Admin", "Editor"])
def list_org_users():
    org_id = get_organization_id()
    users_col = client[DB_NAME]["users"]
    users = list(users_col.find({"organization_id": org_id}))
    return jsonify(json_util_serialize(users)), 200

@app.route("/api/org/users", methods=["POST"])
@login_required
@roles_required(["Admin"])
def add_org_user():
    data = request.json or {}
    email = data.get("email")
    password = data.get("password")
    first_name = data.get("first_name", "")
    last_name = data.get("last_name", "")
    roles = data.get("roles", ["Respondent"])

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    org_id = get_organization_id()
    users_col = client[DB_NAME]["users"]
    if users_col.find_one({"email": email}):
        return jsonify({"error": "User already exists"}), 400

    pwd_hash = AuthManager.hash_password(password)
    user_doc = {
        "organization_id": org_id,
        "email": email,
        "password_hash": pwd_hash,
        "first_name": first_name,
        "last_name": last_name,
        "roles": roles,
        "status": "Active",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    users_col.insert_one(user_doc)
    user_doc["_id"] = str(user_doc["_id"])
    
    record_audit_log("add_org_user", details={"added_email": email})
    return jsonify(json_util_serialize(user_doc)), 201

@app.route("/api/org/users/<user_id>", methods=["PATCH"])
@login_required
@roles_required(["Admin"])
def update_org_user(user_id):
    try:
        user_obj_id = ObjectId(user_id)
    except Exception:
        return jsonify({"error": "Invalid user ID"}), 400

    org_id = get_organization_id()
    users_col = client[DB_NAME]["users"]
    user = users_col.find_one({"_id": user_obj_id, "organization_id": org_id})
    if not user:
        return jsonify({"error": "User not found in organization"}), 404

    data = request.json or {}
    updates = {}
    if "roles" in data:
        updates["roles"] = data["roles"]
    if "status" in data:
        updates["status"] = data["status"]
    if "first_name" in data:
        updates["first_name"] = data["first_name"]
    if "last_name" in data:
        updates["last_name"] = data["last_name"]

    if updates:
        updates["updated_at"] = datetime.utcnow()
        users_col.update_one({"_id": user_obj_id}, {"$set": updates})

    record_audit_log("update_org_user", details={"target_user_id": user_id, "updates": list(updates.keys())})
    return jsonify({"message": "User updated successfully"}), 200

@app.route("/api/org/users/<user_id>", methods=["DELETE"])
@login_required
@roles_required(["Admin"])
def delete_org_user(user_id):
    try:
        user_obj_id = ObjectId(user_id)
    except Exception:
        return jsonify({"error": "Invalid user ID"}), 400

    org_id = get_organization_id()
    users_col = client[DB_NAME]["users"]
    user = users_col.find_one({"_id": user_obj_id, "organization_id": org_id})
    if not user:
        return jsonify({"error": "User not found in organization"}), 404

    # Soft delete / Suspend
    users_col.update_one({"_id": user_obj_id}, {"$set": {"status": "Suspended", "updated_at": datetime.utcnow()}})
    
    record_audit_log("suspend_org_user", details={"target_user_id": user_id})
    return jsonify({"message": "User account suspended successfully"}), 200


# ==========================================
# 📂 PROJECT ENDPOINTS
# ==========================================

@app.route("/api/projects", methods=["POST"])
@login_required
@roles_required(["Admin", "Editor"])
def create_project():
    data = request.json or {}
    org_id = get_organization_id()
    _, projects_col, _, _, _, _ = get_collections()
    
    project_doc = {
        "organization_id": org_id,
        "name": data.get("name", "New Project"),
        "description": data.get("description", ""),
        "deleted": False,
        "shares": [],
        "created_at": datetime.utcnow()
    }
    result = projects_col.insert_one(project_doc)
    project_doc["_id"] = result.inserted_id
    
    record_audit_log("create_project", project_id=project_doc["_id"])
    return jsonify(json_util_serialize(project_doc)), 201

@app.route("/api/projects", methods=["GET"])
@login_required
def list_projects():
    org_id = get_organization_id()
    _, projects_col, _, _, _, _ = get_collections()
    projects = list(projects_col.find({"organization_id": org_id, "deleted": {"$ne": True}}))
    return jsonify(json_util_serialize(projects)), 200

@app.route("/api/projects/<project_id>", methods=["GET"])
@login_required
def get_project(project_id):
    permission_ok, err_res = check_permission("project", project_id, ["Analyst", "Editor", "Admin"])
    if not permission_ok:
        return err_res

    try:
        obj_id = ObjectId(project_id)
    except Exception:
        return jsonify({"error": "Invalid project ID format"}), 400
    
    _, projects_col, _, _, _, _ = get_collections()
    project = projects_col.find_one({"_id": obj_id, "deleted": {"$ne": True}})
    if not project:
        return jsonify({"error": "Project not found"}), 404
    return jsonify(json_util_serialize(project)), 200

@app.route("/api/projects/<project_id>", methods=["DELETE"])
@login_required
def delete_project(project_id):
    permission_ok, err_res = check_permission("project", project_id, ["Admin", "Editor"])
    if not permission_ok:
        return err_res

    try:
        obj_id = ObjectId(project_id)
    except Exception:
        return jsonify({"error": "Invalid project ID format"}), 400

    _, projects_col, _, _, _, _ = get_collections()
    project = projects_col.find_one({"_id": obj_id})
    if not project:
        return jsonify({"error": "Project not found"}), 404

    projects_col.update_one({"_id": obj_id}, {"$set": {"deleted": True}})
    record_audit_log("delete_project", project_id=obj_id)
    return jsonify({"message": "Project soft-deleted successfully"}), 200

@app.route("/api/projects/<project_id>/forms", methods=["GET"])
@login_required
def get_project_forms(project_id):
    permission_ok, err_res = check_permission("project", project_id, ["Analyst", "Editor", "Admin"])
    if not permission_ok:
        return err_res

    try:
        obj_id = ObjectId(project_id)
    except Exception:
        return jsonify({"error": "Invalid project ID format"}), 400
    
    _, _, forms_col, _, _, _ = get_collections()
    forms = list(forms_col.find({"project_id": obj_id, "deleted": {"$ne": True}}))
    return jsonify(json_util_serialize(forms)), 200


# ==========================================
# 🤝 PROJECT SHARING & ACL ENDPOINTS
# ==========================================

@app.route("/api/projects/<project_id>/share", methods=["POST"])
@login_required
def share_project(project_id):
    try:
        obj_id = ObjectId(project_id)
    except Exception:
        return jsonify({"error": "Invalid project ID"}), 400
    
    permission_ok, err_res = check_permission("project", project_id, ["Editor", "Admin"])
    if not permission_ok:
        return err_res
    
    data = request.json or {}
    email = data.get("email")
    role = data.get("role")
    if not email or not role or role not in ["Admin", "Editor", "Analyst", "Respondent"]:
        return jsonify({"error": "Email and valid role are required"}), 400
        
    user = client[DB_NAME]["users"].find_one({"email": email})
    user_id = str(user["_id"]) if user else None
    
    db_ctx, projects_col, _, _, _, _ = get_collections()
    projects_col.update_one(
        {"_id": obj_id},
        {"$pull": {"shares": {"email": email}}}
    )
    projects_col.update_one(
        {"_id": obj_id},
        {"$push": {"shares": {"user_id": user_id, "email": email, "role": role}}}
    )
    record_audit_log("share_project", project_id=obj_id, details={"email": email, "role": role})
    return jsonify({"message": f"Project shared with {email} as {role}"}), 200

@app.route("/api/projects/<project_id>/shares", methods=["GET"])
@login_required
def get_project_shares(project_id):
    try:
        obj_id = ObjectId(project_id)
    except Exception:
        return jsonify({"error": "Invalid project ID"}), 400
    
    permission_ok, err_res = check_permission("project", project_id, ["Analyst", "Editor", "Admin"])
    if not permission_ok:
        return err_res
        
    db_ctx, projects_col, _, _, _, _ = get_collections()
    project = projects_col.find_one({"_id": obj_id})
    shares = project.get("shares", [])
    return jsonify(json_util_serialize(shares)), 200

@app.route("/api/projects/<project_id>/share/<email>", methods=["DELETE"])
@login_required
def remove_project_share(project_id, email):
    try:
        obj_id = ObjectId(project_id)
    except Exception:
        return jsonify({"error": "Invalid project ID"}), 400
        
    permission_ok, err_res = check_permission("project", project_id, ["Editor", "Admin"])
    if not permission_ok:
        return err_res
        
    db_ctx, projects_col, _, _, _, _ = get_collections()
    projects_col.update_one(
        {"_id": obj_id},
        {"$pull": {"shares": {"email": email}}}
    )
    record_audit_log("remove_project_share", project_id=obj_id, details={"email": email})
    return jsonify({"message": f"Removed share access for {email}"}), 200


# ==========================================
# 📝 FORM CRUD & VERSION CONTROL ENDPOINTS
# ==========================================

@app.route("/api/forms", methods=["POST"])
@login_required
def create_form():
    data = request.json or {}
    project_id = data.get("project_id")
    if project_id:
        permission_ok, err_res = check_permission("project", project_id, ["Editor", "Admin"])
        if not permission_ok:
            return err_res

    org_id = get_organization_id()
    _, _, forms_col, _, _, _ = get_collections()
    
    if project_id:
        try:
            project_id = ObjectId(project_id)
        except Exception:
            return jsonify({"error": "Invalid project ID"}), 400

    theme_id = data.get("theme_id")
    if theme_id:
        try:
            theme_id = ObjectId(theme_id)
        except Exception:
            theme_id = None

    sections = data.get("sections", [])
    if not sections and "questions" in data:
        sections = [{
            "id": "default_section",
            "title": "General",
            "questions": data.get("questions", [])
        }]

    block_script = data.get("block_script")
    if block_script:
        from block_script_engine import BlockScriptEngine
        cycle = BlockScriptEngine.detect_cycles(block_script)
        if cycle:
            return jsonify({"error": f"Circular dependency detected in block scripts: {' -> '.join(cycle)}"}), 400

    form_doc = {
        "organization_id": org_id,
        "project_id": project_id,
        "title": data.get("title", "Untitled Form"),
        "description": data.get("description", ""),
        "theme_id": theme_id,
        "workflows": data.get("workflows", []),
        "block_script": data.get("block_script"),
        "ab_testing": data.get("ab_testing"),
        "start_date": data.get("start_date"),
        "end_date": data.get("end_date"),
        "max_submissions": data.get("max_submissions"),
        "deleted": False,
        "shares": [],
        "current_version": 1,
        "versions": [
            {
                "version_number": 1,
                "published": True,
                "created_at": datetime.utcnow(),
                "sections": sections,
                "block_script": data.get("block_script")
            }
        ],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    result = forms_col.insert_one(form_doc)
    form_doc["_id"] = result.inserted_id
    
    record_audit_log("create_form", form_id=form_doc["_id"], project_id=project_id)
    return jsonify(json_util_serialize(form_doc)), 201

@app.route("/api/forms/<form_id>", methods=["GET"])
@login_required
def get_form(form_id):
    permission_ok, err_res = check_permission("form", form_id, ["Analyst", "Editor", "Admin"])
    if not permission_ok:
        return err_res

    try:
        obj_id = ObjectId(form_id)
    except Exception:
        return jsonify({"error": "Invalid form ID format"}), 400

    _, _, forms_col, _, _, _ = get_collections()
    form = forms_col.find_one({"_id": obj_id, "deleted": {"$ne": True}})
    if not form:
        return jsonify({"error": "Form not found"}), 404

    return jsonify(json_util_serialize(form)), 200

@app.route("/api/forms/<form_id>", methods=["DELETE"])
@login_required
def delete_form(form_id):
    permission_ok, err_res = check_permission("form", form_id, ["Editor", "Admin"])
    if not permission_ok:
        return err_res

    try:
        obj_id = ObjectId(form_id)
    except Exception:
        return jsonify({"error": "Invalid form ID format"}), 400

    _, _, forms_col, _, _, _ = get_collections()
    form = forms_col.find_one({"_id": obj_id})
    if not form:
        return jsonify({"error": "Form not found"}), 404

    forms_col.update_one({"_id": obj_id}, {"$set": {"deleted": True}})
    record_audit_log("delete_form", form_id=obj_id)
    return jsonify({"message": "Form soft-deleted successfully"}), 200

@app.route("/api/forms/<form_id>/versions", methods=["POST"])
@login_required
def create_form_version(form_id):
    permission_ok, err_res = check_permission("form", form_id, ["Editor", "Admin"])
    if not permission_ok:
        return err_res

    try:
        obj_id = ObjectId(form_id)
    except Exception:
        return jsonify({"error": "Invalid form ID format"}), 400

    data = request.json or {}
    db_ctx, _, forms_col, _, _, _ = get_collections()
    form = forms_col.find_one({"_id": obj_id, "deleted": {"$ne": True}})
    if not form:
        return jsonify({"error": "Form not found"}), 404

    sections = data.get("sections", [])
    if not sections:
        return jsonify({"error": "Sections are required for version schemas"}), 400

    # --- SCHEMA DRIFT WARNING DETECTION ---
    drift_warnings = SchemaDriftDetector.detect_drift(form, sections)

    block_script = data.get("block_script")
    if block_script:
        from block_script_engine import BlockScriptEngine
        cycle = BlockScriptEngine.detect_cycles(block_script)
        if cycle:
            return jsonify({"error": f"Circular dependency detected in block scripts: {' -> '.join(cycle)}"}), 400

    versions = form.get("versions", [])
    next_ver = max([v.get("version_number", 1) for v in versions]) + 1 if versions else 1

    new_version_node = {
        "version_number": next_ver,
        "published": False,
        "created_at": datetime.utcnow(),
        "sections": sections,
        "block_script": data.get("block_script"),
        "drift_warnings": drift_warnings
    }

    forms_col.update_one(
        {"_id": obj_id},
        {
            "$push": {"versions": new_version_node},
            "$set": {"updated_at": datetime.utcnow()}
        }
    )
    
    record_audit_log("create_version", form_id=obj_id, details={"version": next_ver, "drift_warnings": drift_warnings})
    
    return jsonify(json_util_serialize(new_version_node)), 201

@app.route("/api/forms/<form_id>/publish", methods=["POST"])
@login_required
def publish_version(form_id):
    permission_ok, err_res = check_permission("form", form_id, ["Editor", "Admin"])
    if not permission_ok:
        return err_res

    try:
        obj_id = ObjectId(form_id)
    except Exception:
        return jsonify({"error": "Invalid form ID format"}), 400

    data = request.json or {}
    version_num = data.get("version_number")
    if not version_num:
        return jsonify({"error": "version_number is required"}), 400

    _, _, forms_col, _, _, _ = get_collections()
    form = forms_col.find_one({"_id": obj_id, "deleted": {"$ne": True}})
    if not form:
        return jsonify({"error": "Form not found"}), 404

    versions = form.get("versions", [])
    version_exists = any([v.get("version_number") == version_num for v in versions])
    if not version_exists:
        return jsonify({"error": "Version number not found"}), 404

    forms_col.update_one(
        {"_id": obj_id},
        {"$set": {"current_version": version_num, "updated_at": datetime.utcnow()}}
    )
    for v in versions:
        v["published"] = (v["version_number"] == version_num)
    
    forms_col.update_one(
        {"_id": obj_id},
        {"$set": {"versions": versions}}
    )

    # Delete responses/drafts on versions of the form that are not published
    db_ctx, _, _, _, responses_col, _ = get_collections()
    responses_col.delete_many({"form_id": obj_id, "version": {"$ne": version_num}})

    record_audit_log("publish_version", form_id=obj_id, details={"version": version_num})
    return jsonify({"message": f"Version {version_num} is now active"}), 200

@app.route("/api/forms/<form_id>/surveyjs", methods=["GET"])
@login_required
def get_form_surveyjs(form_id):
    permission_ok, err_res = check_permission("form", form_id, ["Respondent", "Analyst", "Editor", "Admin"])
    if not permission_ok:
        return err_res

    try:
        obj_id = ObjectId(form_id)
    except Exception:
        return jsonify({"error": "Invalid form ID format"}), 400

    db_ctx, _, forms_col, themes_col, _, _ = get_collections()
    form = forms_col.find_one({"_id": obj_id, "deleted": {"$ne": True}})
    if not form:
        return jsonify({"error": "Form not found"}), 404

    theme = None
    if form.get("theme_id"):
        theme = themes_col.find_one({"_id": form["theme_id"]})

    ab_config = form.get("ab_testing")
    active_version = form.get("current_version", 1)
    
    if ab_config and ab_config.get("enabled"):
        variants = ab_config.get("variants", [])
        if variants:
            weights = [v.get("weight", 50) for v in variants]
            chosen_variant = random.choices(variants, weights=weights, k=1)[0]
            active_version = chosen_variant.get("version", active_version)

    org_id = get_organization_id()
    
    form_copy = dict(form)
    form_copy["current_version"] = active_version

    surveyjs_schema = SurveyJSTranslator.translate_form(form_copy, theme, db=db_ctx, org_id=org_id)
    
    if ab_config and ab_config.get("enabled"):
        surveyjs_schema["ab_version_assigned"] = active_version

    return jsonify(surveyjs_schema), 200


# ==========================================
# 🤝 FORM SHARING & ACL ENDPOINTS
# ==========================================

@app.route("/api/forms/<form_id>/share", methods=["POST"])
@login_required
def share_form(form_id):
    try:
        obj_id = ObjectId(form_id)
    except Exception:
        return jsonify({"error": "Invalid form ID"}), 400
    
    permission_ok, err_res = check_permission("form", form_id, ["Editor", "Admin"])
    if not permission_ok:
        return err_res
    
    data = request.json or {}
    email = data.get("email")
    role = data.get("role")
    if not email or not role or role not in ["Admin", "Editor", "Analyst", "Respondent"]:
        return jsonify({"error": "Email and valid role are required"}), 400
        
    user = client[DB_NAME]["users"].find_one({"email": email})
    user_id = str(user["_id"]) if user else None
    
    db_ctx, _, forms_col, _, _, _ = get_collections()
    forms_col.update_one(
        {"_id": obj_id},
        {"$pull": {"shares": {"email": email}}}
    )
    forms_col.update_one(
        {"_id": obj_id},
        {"$push": {"shares": {"user_id": user_id, "email": email, "role": role}}}
    )
    record_audit_log("share_form", form_id=obj_id, details={"email": email, "role": role})
    return jsonify({"message": f"Form shared with {email} as {role}"}), 200

@app.route("/api/forms/<form_id>/shares", methods=["GET"])
@login_required
def get_form_shares(form_id):
    try:
        obj_id = ObjectId(form_id)
    except Exception:
        return jsonify({"error": "Invalid form ID"}), 400
    
    permission_ok, err_res = check_permission("form", form_id, ["Analyst", "Editor", "Admin"])
    if not permission_ok:
        return err_res
        
    db_ctx, _, forms_col, _, _, _ = get_collections()
    form = forms_col.find_one({"_id": obj_id})
    shares = form.get("shares", [])
    return jsonify(json_util_serialize(shares)), 200

@app.route("/api/forms/<form_id>/share/<email>", methods=["DELETE"])
@login_required
def remove_form_share(form_id, email):
    try:
        obj_id = ObjectId(form_id)
    except Exception:
        return jsonify({"error": "Invalid form ID"}), 400
        
    permission_ok, err_res = check_permission("form", form_id, ["Editor", "Admin"])
    if not permission_ok:
        return err_res
        
    db_ctx, _, forms_col, _, _, _ = get_collections()
    forms_col.update_one(
        {"_id": obj_id},
        {"$pull": {"shares": {"email": email}}}
    )
    record_audit_log("remove_form_share", form_id=obj_id, details={"email": email})
    return jsonify({"message": f"Removed share access for {email}"}), 200


# ==========================================
# 🎨 THEME ENDPOINTS
# ==========================================

@app.route("/api/themes", methods=["POST"])
@login_required
@roles_required(["Editor", "Admin"])
def create_theme():
    data = request.json or {}
    org_id = get_organization_id()
    _, _, _, themes_col, _, _ = get_collections()
    
    theme_doc = {
        "organization_id": org_id,
        "name": data.get("name", "New Theme"),
        "active": data.get("active", True),
        "style": data.get("style", {})
    }
    result = themes_col.insert_one(theme_doc)
    theme_doc["_id"] = result.inserted_id
    return jsonify(json_util_serialize(theme_doc)), 201

@app.route("/api/themes", methods=["GET"])
@login_required
def list_themes():
    org_id = get_organization_id()
    _, _, _, themes_col, _, _ = get_collections()
    themes = list(themes_col.find({"organization_id": org_id}))
    return jsonify(json_util_serialize(themes)), 200


# ==========================================
# 📥 RESPONSE SUBMISSION & STATE PATTERNS
# ==========================================

@app.route("/api/forms/<form_id>/submit", methods=["POST"])
@login_required
def submit_response(form_id):
    permission_ok, err_res = check_permission("form", form_id, ["Respondent", "Analyst", "Editor", "Admin"])
    if not permission_ok:
        return err_res

    try:
        obj_id = ObjectId(form_id)
    except Exception:
        return jsonify({"error": "Invalid form ID format"}), 400

    db_ctx, _, forms_col, _, responses_col, _ = get_collections()
    form = forms_col.find_one({"_id": obj_id, "deleted": {"$ne": True}})
    if not form:
        return jsonify({"error": "Form not found"}), 404

    # --- IDEMPOTENCY KEY CHECK ---
    idem_key = request.headers.get("X-Idempotency-Key")
    org_id = get_organization_id()
    if idem_key:
        existing_log = db_ctx["idempotency_keys"].find_one({"key": idem_key, "org_id": org_id})
        if existing_log:
            logger.info(f"Duplicate request detected for idempotency key: {idem_key}")
            return jsonify(json_util_serialize(existing_log["response_data"])), 200

    version_str = request.args.get("version")
    try:
        version_num = int(version_str) if version_str else form.get("current_version", 1)
    except ValueError:
        version_num = form.get("current_version", 1)

    data_payload = {}
    if request.is_json:
        data_payload = request.json or {}
    else:
        data_payload = request.form.to_dict()

    status = data_payload.get("status", "Submitted")
    is_draft = (status == "Draft")

    answers = {k: v for k, v in data_payload.items() if k not in ["status", "version", "organization_id"]}

    if not request.is_json:
        for key, file_storage in request.files.items():
            if file_storage and file_storage.filename:
                filename = f"file_{uuid.uuid4().hex}_{file_storage.filename}"
                file_bytes = file_storage.read()
                content_type = file_storage.content_type or "application/octet-stream"
                s3_url = S3Helper.upload_file(file_bytes, filename, content_type=content_type)
                answers[key] = s3_url
                register_upload(s3_url)

    validator = FormSubmissionValidator(form, version_num, is_draft=is_draft, db=db_ctx, org_id=org_id)
    active_sections = validator.get_active_sections()
    
    for sec in active_sections:
        for q in sec.get("questions", []):
            q_id = q.get("id")
            q_type = q.get("type")
            if q_type in ["camera", "signature"] and answers.get(q_id):
                base64_val = answers[q_id]
                if isinstance(base64_val, str) and (base64_val.startswith("data:") or len(base64_val) > 100):
                    try:
                        filepath = save_base64_image(base64_val)
                        answers[q_id] = filepath
                    except Exception as e:
                        cleanup_discarded_uploads(answers, {})
                        return jsonify({"error": f"Invalid camera or signature file content on {q_id}: {str(e)}"}), 400

    is_valid, validated_answers, errors = validator.validate_and_compute(answers)
    if not is_valid:
        cleanup_discarded_uploads(answers, {})
        return jsonify({"error": "Validation failed", "details": errors}), 400

    cleanup_discarded_uploads(answers, validated_answers)

    # --- DOCUMENT RECEIPT COMPILER ---
    receipt_url = None
    if not is_draft:
        # Generate and save receipt file
        temp_resp_id = str(ObjectId())
        theme_data = None
        if "theme_id" in form and form["theme_id"]:
            try:
                theme_data = db_ctx["themes"].find_one({"_id": ObjectId(form["theme_id"])})
            except Exception:
                pass
        receipt_url = PDFGenerator.generate_and_upload_receipt(form.get("title"), validated_answers, temp_resp_id, theme_data)

    response_doc = {
        "form_id": obj_id,
        "version": version_num,
        "status": status,
        "organization_id": org_id,
        "submitted_at": datetime.utcnow(),
        "answers": validated_answers,
        "receipt_url": receipt_url
    }

    result = responses_col.insert_one(response_doc)
    response_doc["_id"] = result.inserted_id
    link_uploads_to_response(result.inserted_id, validated_answers)
    if not is_draft:
        trigger_lookup_mv_update(db_ctx, obj_id, org_id, validated_answers)

    # Trigger DAG Pipeline on submission
    if not is_draft:
        workflows = form.get("workflows", [])
        for wf in workflows:
            PipelineEngine.execute_pipeline(wf, form, response_doc, db=db_ctx)

    warning = None
    if version_num < form.get("current_version", 1):
        warning = "DeprecationWarning: You submitted against an older version of the form."

    success_payload = {
        "message": "Response processed successfully",
        "response": response_doc
    }
    if warning:
        success_payload["warning"] = warning

    # Record idempotency log
    if idem_key:
        db_ctx["idempotency_keys"].insert_one({
            "key": idem_key,
            "org_id": org_id,
            "response_data": success_payload,
            "created_at": datetime.utcnow()
        })

    return jsonify(json_util_serialize(success_payload)), 201


@app.route("/api/responses/<response_id>", methods=["PATCH"])
@login_required
def update_draft_response(response_id):
    try:
        obj_id = ObjectId(response_id)
    except Exception:
        return jsonify({"error": "Invalid response ID format"}), 400

    db_ctx, _, forms_col, _, responses_col, _ = get_collections()
    existing_resp = responses_col.find_one({"_id": obj_id})
    if not existing_resp:
        return jsonify({"error": "Response not found"}), 404

    # Check permission on the associated form
    permission_ok, err_res = check_permission("form", existing_resp["form_id"], ["Respondent", "Analyst", "Editor", "Admin"])
    if not permission_ok:
        return err_res

    data = request.json or {}
    new_status = data.get("status", existing_resp.get("status", "Draft"))
    is_draft = (new_status == "Draft")

    form = forms_col.find_one({"_id": existing_resp["form_id"], "deleted": {"$ne": True}})
    if not form:
        return jsonify({"error": "Associated form not found"}), 404

    version_num = existing_resp.get("version", 1)

    updated_answers = existing_resp.get("answers", {})
    new_answers = data.get("answers", {})

    # Git-like 3-way merge conflict resolution on draft concurrent edits
    base_answers = data.get("base_answers")
    if base_answers is not None:
        merged_answers, conflicts = merge_response_answers(base_answers, updated_answers, new_answers)
        if conflicts:
            cleanup_discarded_uploads(new_answers, {})
            return jsonify({
                "error": "Merge conflict detected on concurrent edits.",
                "conflicts": conflicts
            }), 409
        updated_answers = merged_answers
    else:
        updated_answers.update(new_answers)

    org_id = get_organization_id()
    validator = FormSubmissionValidator(form, version_num, is_draft=is_draft, db=db_ctx, org_id=org_id)
    
    active_sections = validator.get_active_sections()
    for sec in active_sections:
        for q in sec.get("questions", []):
            q_id = q.get("id")
            q_type = q.get("type")
            if q_type in ["camera", "signature"] and updated_answers.get(q_id):
                base64_val = updated_answers[q_id]
                if isinstance(base64_val, str) and (base64_val.startswith("data:") or len(base64_val) > 100):
                    try:
                        filepath = save_base64_image(base64_val)
                        updated_answers[q_id] = filepath
                    except Exception as e:
                        cleanup_discarded_uploads(new_answers, {})
                        return jsonify({"error": f"Invalid camera or signature file content on {q_id}: {str(e)}"}), 400

    is_valid, validated_answers, errors = validator.validate_and_compute(updated_answers)
    if not is_valid:
        cleanup_discarded_uploads(new_answers, {})
        return jsonify({"error": "Validation failed", "details": errors}), 400

    cleanup_discarded_uploads(new_answers, validated_answers)

    receipt_url = existing_resp.get("receipt_url")
    if new_status == "Submitted" and existing_resp.get("status") == "Draft" and not receipt_url:
        theme_data = None
        if "theme_id" in form and form["theme_id"]:
            try:
                theme_data = db_ctx["themes"].find_one({"_id": ObjectId(form["theme_id"])})
            except Exception:
                pass
        receipt_url = PDFGenerator.generate_and_upload_receipt(form.get("title"), validated_answers, str(obj_id), theme_data)

    update_data = {
        "status": new_status,
        "answers": validated_answers,
        "submitted_at": datetime.utcnow(),
        "receipt_url": receipt_url
    }
    
    responses_col.update_one({"_id": obj_id}, {"$set": update_data})
    existing_resp.update(update_data)
    link_uploads_to_response(obj_id, validated_answers)
    if new_status == "Submitted":
        trigger_lookup_mv_update(db_ctx, existing_resp["form_id"], org_id, validated_answers)

    if new_status == "Submitted" and existing_resp.get("status") == "Draft":
        record_audit_log("promote_draft", form_id=form["_id"])
        workflows = form.get("workflows", [])
        for wf in workflows:
            PipelineEngine.execute_pipeline(wf, form, existing_resp, db=db_ctx)

    warning = None
    if version_num < form.get("current_version", 1):
        warning = "DeprecationWarning: You submitted against an older version of the form."

    payload = {
        "message": "Response updated successfully",
        "response": existing_resp
    }
    if warning:
        payload["warning"] = warning

    return jsonify(json_util_serialize(payload)), 200


# ==========================================
# ⚡ DRAFT BATCH SUBMISSION ENDPOINT
# ==========================================

@app.route("/api/forms/<form_id>/submit-batch", methods=["POST"])
@login_required
def submit_batch_responses(form_id):
    permission_ok, err_res = check_permission("form", form_id, ["Respondent", "Analyst", "Editor", "Admin"])
    if not permission_ok:
        return err_res

    try:
        obj_id = ObjectId(form_id)
    except Exception:
        return jsonify({"error": "Invalid form ID format"}), 400

    db_ctx, _, forms_col, _, responses_col, _ = get_collections()
    form = forms_col.find_one({"_id": obj_id, "deleted": {"$ne": True}})
    if not form:
        return jsonify({"error": "Form not found"}), 404

    data = request.json or {}
    submissions = data.get("submissions", [])
    if not isinstance(submissions, list):
        return jsonify({"error": "Submissions must be a list of answers."}), 400

    org_id = get_organization_id()
    version_num = form.get("current_version", 1)

    batch_responses = []
    batch_errors = {}

    for idx, ans_dict in enumerate(submissions):
        validator = FormSubmissionValidator(form, version_num, is_draft=False, db=db_ctx, org_id=org_id)
        is_ok, validated_ans, errors = validator.validate_and_compute(ans_dict)
        if not is_ok:
            batch_errors[f"index_{idx}"] = errors
        else:
            response_doc = {
                "form_id": obj_id,
                "version": version_num,
                "status": "Submitted",
                "organization_id": org_id,
                "submitted_at": datetime.utcnow(),
                "answers": validated_ans
            }
            batch_responses.append(response_doc)

    inserted_ids = []
    if batch_responses:
        session = None
        try:
            session = client.start_session()
            session.start_transaction()
            res = responses_col.insert_many(batch_responses, session=session)
            inserted_ids = res.inserted_ids
            session.commit_transaction()
        except Exception as e:
            if session:
                try:
                    session.abort_transaction()
                except Exception:
                    pass
                try:
                    session.end_session()
                except Exception:
                    pass
                session = None
            
            from pymongo.errors import OperationFailure
            if isinstance(e, OperationFailure) and ("replica set" in str(e) or "Transaction numbers" in str(e)):
                res = responses_col.insert_many(batch_responses)
                inserted_ids = res.inserted_ids
            else:
                raise e
        finally:
            if session:
                try:
                    session.end_session()
                except Exception:
                    pass

        for resp in batch_responses:
            if "_id" in resp:
                link_uploads_to_response(resp["_id"], resp["answers"])
                trigger_lookup_mv_update(db_ctx, obj_id, org_id, resp["answers"])

        record_audit_log("submit_batch", form_id=obj_id, details={"count": len(batch_responses)})

    if batch_errors:
        return jsonify(json_util_serialize({
            "message": "Some submissions failed validation",
            "inserted_count": len(batch_responses),
            "inserted_ids": [str(x) for x in inserted_ids],
            "details": batch_errors
        })), 207

    return jsonify(json_util_serialize({
        "message": "Batch processed successfully",
        "inserted_count": len(batch_responses),
        "inserted_ids": [str(x) for x in inserted_ids]
    })), 201



# ==========================================
# 🛠️ RULE ENGINE DEBUGGER
# ==========================================

@app.route("/api/forms/<form_id>/debug", methods=["POST"])
@login_required
def debug_rules_engine(form_id):
    permission_ok, err_res = check_permission("form", form_id, ["Editor", "Admin"])
    if not permission_ok:
        return err_res

    try:
        obj_id = ObjectId(form_id)
    except Exception:
        return jsonify({"error": "Invalid form ID format"}), 400

    db_ctx, _, forms_col, _, _, _ = get_collections()
    form = forms_col.find_one({"_id": obj_id, "deleted": {"$ne": True}})
    if not form:
        return jsonify({"error": "Form not found"}), 404

    data = request.json or {}
    answers = data.get("answers", {})

    org_id = get_organization_id()
    validator = FormSubmissionValidator(form, form.get("current_version", 1), is_draft=False, db=db_ctx, org_id=org_id)
    
    is_valid, validated_answers, errors = validator.validate_and_compute(answers)
    
    return jsonify(json_util_serialize({
        "is_valid": is_valid,
        "validated_answers": validated_answers,
        "validation_errors": errors
    })), 200


# ==========================================
# 📊 ASYNCHRONOUS DATA EXPORT TASK ROUTING
# ==========================================

@app.route("/api/forms/<form_id>/export/async", methods=["POST"])
@login_required
def trigger_async_export(form_id):
    permission_ok, err_res = check_permission("form", form_id, ["Analyst", "Admin"])
    if not permission_ok:
        return err_res

    try:
        obj_id = ObjectId(form_id)
    except Exception:
        return jsonify({"error": "Invalid form ID format"}), 400

    db_ctx, _, forms_col, _, _, _ = get_collections()
    form = forms_col.find_one({"_id": obj_id, "deleted": {"$ne": True}})
    if not form:
        return jsonify({"error": "Form not found"}), 404

    data = request.json or {}
    anonymize = data.get("anonymize", False)

    org_id = get_organization_id()
    user_id = get_user_id()
    task_id = TaskManager.create_export_task(db_ctx, form, org_id, anonymize=anonymize, user_id=user_id)

    return jsonify(json_util_serialize({
        "message": "Export task created successfully",
        "task_id": task_id,
        "status": "PENDING"
    })), 202

@app.route("/api/tasks/<task_id>", methods=["GET"])
@login_required
def get_task_status(task_id):
    try:
        obj_id = ObjectId(task_id)
    except Exception:
        return jsonify({"error": "Invalid task ID format"}), 400

    db_ctx, _, _, _, _, _ = get_collections()
    task = db_ctx["tasks"].find_one({"_id": obj_id})
    if not task:
        return jsonify({"error": "Task not found"}), 404

    return jsonify(json_util_serialize(task)), 200


# ==========================================
# 📊 SYNC DATA EXPORT ROUTING
# ==========================================

@app.route("/api/forms/<form_id>/export/csv", methods=["GET"])
@login_required
def export_form_csv(form_id):
    permission_ok, err_res = check_permission("form", form_id, ["Analyst", "Admin"])
    if not permission_ok:
        return err_res

    try:
        obj_id = ObjectId(form_id)
    except Exception:
        return jsonify({"error": "Invalid form ID format"}), 400

    db_ctx, _, forms_col, _, responses_col, _ = get_collections()
    form = forms_col.find_one({"_id": obj_id, "deleted": {"$ne": True}})
    if not form:
        return jsonify({"error": "Form not found"}), 404

    org_id = get_organization_id()
    responses = list(responses_col.find({
        "form_id": obj_id, 
        "organization_id": org_id,
        "status": "Submitted"
    }))

    headers = ["response_id", "submitted_at"]
    sensitive_keys = []

    for v in form.get("versions", []):
        for sec in v.get("sections", []):
            for q in sec.get("questions", []):
                q_id = q.get("id")
                if q_id not in headers:
                    headers.append(q_id)
                if q.get("properties", {}).get("sensitive", False) and q_id not in sensitive_keys:
                    sensitive_keys.append(q_id)

    anonymize = request.args.get("anonymize", "").lower() == "true"

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)

    for r in responses:
        answers = r.get("answers", {})
        if sensitive_keys:
            answers = EncryptionHelper.process_sensitive_fields(answers, sensitive_keys, action="decrypt")
        if anonymize and sensitive_keys:
            answers = DataAnonymizer.anonymize_answers(answers, sensitive_keys)

        row = [str(r["_id"]), r["submitted_at"].isoformat()]
        for h in headers[2:]:
            row.append(str(answers.get(h, "")))
        writer.writerow(row)

    record_audit_log("export_csv", form_id=obj_id, details={"anonymized": anonymize})

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename=form_{form_id}_responses.csv"}
    )


@app.route("/api/forms/<form_id>/export/json", methods=["GET"])
@login_required
def export_form_json(form_id):
    permission_ok, err_res = check_permission("form", form_id, ["Analyst", "Admin"])
    if not permission_ok:
        return err_res

    try:
        obj_id = ObjectId(form_id)
    except Exception:
        return jsonify({"error": "Invalid form ID format"}), 400

    db_ctx, _, forms_col, _, responses_col, _ = get_collections()
    form = forms_col.find_one({"_id": obj_id, "deleted": {"$ne": True}})
    if not form:
        return jsonify({"error": "Form not found"}), 404

    org_id = get_organization_id()
    responses = list(responses_col.find({
        "form_id": obj_id, 
        "organization_id": org_id,
        "status": "Submitted"
    }))

    sensitive_keys = []
    for v in form.get("versions", []):
        for sec in v.get("sections", []):
            for q in sec.get("questions", []):
                q_id = q.get("id")
                if q.get("properties", {}).get("sensitive", False) and q_id not in sensitive_keys:
                    sensitive_keys.append(q_id)

    processed_responses = []
    anonymize = request.args.get("anonymize", "").lower() == "true"

    for r in responses:
        answers = r.get("answers", {})
        if sensitive_keys:
            answers = EncryptionHelper.process_sensitive_fields(answers, sensitive_keys, action="decrypt")
        if anonymize and sensitive_keys:
            answers = DataAnonymizer.anonymize_answers(answers, sensitive_keys)
        
        r["answers"] = answers
        processed_responses.append(r)

    record_audit_log("export_json", form_id=obj_id, details={"anonymized": anonymize})
    return jsonify(json_util_serialize(processed_responses)), 200


# ==========================================
# 🛠️ GIT-LIKE FORM VERSION CONTROL ENDPOINTS
# ==========================================

@app.route("/api/forms/<form_id>/commit", methods=["POST"])
@login_required
def git_commit_form(form_id):
    permission_ok, err_res = check_permission("form", form_id, ["Editor", "Admin"])
    if not permission_ok:
        return err_res

    try:
        obj_id = ObjectId(form_id)
    except Exception:
        return jsonify({"error": "Invalid form ID"}), 400

    data = request.json or {}
    sections = data.get("sections")
    message = data.get("message", "Commit schema changes")
    branch = data.get("branch", "main")

    if not sections:
        return jsonify({"error": "Sections schema is required to commit"}), 400

    block_script = data.get("block_script")
    if block_script:
        from block_script_engine import BlockScriptEngine
        cycle = BlockScriptEngine.detect_cycles(block_script)
        if cycle:
            return jsonify({"error": f"Circular dependency detected in block scripts: {' -> '.join(cycle)}"}), 400

    db_ctx, _, forms_col, _, _, _ = get_collections()
    author_id = get_user_id()

    commit_hash, err = GitVersionControl.create_commit(forms_col, obj_id, branch, sections, message, author_id)
    if err:
        return jsonify({"error": err}), 400

    record_audit_log("git_commit", form_id=obj_id, details={"branch": branch, "commit_hash": commit_hash})
    return jsonify({"message": "Schema committed successfully", "commit_hash": commit_hash}), 201

@app.route("/api/forms/<form_id>/commits", methods=["GET"])
@login_required
def git_get_commits(form_id):
    permission_ok, err_res = check_permission("form", form_id, ["Analyst", "Editor", "Admin"])
    if not permission_ok:
        return err_res

    try:
        obj_id = ObjectId(form_id)
    except Exception:
        return jsonify({"error": "Invalid form ID"}), 400

    db_ctx, _, forms_col, _, _, _ = get_collections()
    form = forms_col.find_one({"_id": obj_id})
    if not form:
        return jsonify({"error": "Form not found"}), 404

    commits = list(db_ctx["commits"].find({"form_id": obj_id}).sort("timestamp", -1))
    return jsonify(json_util_serialize(commits)), 200

@app.route("/api/forms/<form_id>/branches", methods=["POST"])
@login_required
def git_create_branch(form_id):
    permission_ok, err_res = check_permission("form", form_id, ["Editor", "Admin"])
    if not permission_ok:
        return err_res

    try:
        obj_id = ObjectId(form_id)
    except Exception:
        return jsonify({"error": "Invalid form ID"}), 400

    data = request.json or {}
    new_branch = data.get("branch_name")
    source_branch = data.get("source_branch", "main")

    if not new_branch:
        return jsonify({"error": "branch_name is required"}), 400

    db_ctx, _, forms_col, _, _, _ = get_collections()
    success, err = GitVersionControl.create_branch(forms_col, obj_id, new_branch, source_branch)
    if not success:
        return jsonify({"error": err}), 400

    record_audit_log("git_create_branch", form_id=obj_id, details={"branch": new_branch, "source": source_branch})
    return jsonify({"message": f"Branch '{new_branch}' created successfully"}), 201

@app.route("/api/forms/<form_id>/branches", methods=["GET"])
@login_required
def git_list_branches(form_id):
    permission_ok, err_res = check_permission("form", form_id, ["Analyst", "Editor", "Admin"])
    if not permission_ok:
        return err_res

    try:
        obj_id = ObjectId(form_id)
    except Exception:
        return jsonify({"error": "Invalid form ID"}), 400

    db_ctx, _, forms_col, _, _, _ = get_collections()
    form = forms_col.find_one({"_id": obj_id})
    if not form:
        return jsonify({"error": "Form not found"}), 404

    branches = form.get("vcs_branches", {"main": None})
    return jsonify(json_util_serialize(branches)), 200

@app.route("/api/forms/<form_id>/diff", methods=["GET"])
@login_required
def git_diff_form(form_id):
    permission_ok, err_res = check_permission("form", form_id, ["Analyst", "Editor", "Admin"])
    if not permission_ok:
        return err_res

    try:
        obj_id = ObjectId(form_id)
    except Exception:
        return jsonify({"error": "Invalid form ID"}), 400

    from_ref = request.args.get("from_ref")
    to_ref = request.args.get("to_ref")

    if not from_ref or not to_ref:
        return jsonify({"error": "from_ref and to_ref query parameters are required"}), 400

    db_ctx, _, forms_col, _, _, _ = get_collections()
    diff_data, err = GitVersionControl.get_diff(forms_col, obj_id, from_ref, to_ref)
    if err:
        return jsonify({"error": err}), 400

    return jsonify(diff_data), 200

@app.route("/api/forms/<form_id>/merge", methods=["POST"])
@login_required
def git_merge_form(form_id):
    permission_ok, err_res = check_permission("form", form_id, ["Editor", "Admin"])
    if not permission_ok:
        return err_res

    try:
        obj_id = ObjectId(form_id)
    except Exception:
        return jsonify({"error": "Invalid form ID"}), 400

    data = request.json or {}
    source_branch = data.get("source_branch")
    target_branch = data.get("target_branch", "main")

    if not source_branch:
        return jsonify({"error": "source_branch is required"}), 400

    db_ctx, _, forms_col, _, _, _ = get_collections()
    author_id = get_user_id()

    merge_result, err = GitVersionControl.merge_branches(forms_col, obj_id, source_branch, target_branch, author_id)
    if err:
        return jsonify({"error": err}), 400

    record_audit_log("git_merge", form_id=obj_id, details={"source": source_branch, "target": target_branch, "result": merge_result})
    return jsonify(merge_result), 200

@app.route("/api/forms/<form_id>/revert", methods=["POST"])
@login_required
def git_revert_form(form_id):
    permission_ok, err_res = check_permission("form", form_id, ["Editor", "Admin"])
    if not permission_ok:
        return err_res

    try:
        obj_id = ObjectId(form_id)
    except Exception:
        return jsonify({"error": "Invalid form ID"}), 400

    data = request.json or {}
    commit_hash = data.get("commit_hash")
    branch = data.get("branch", "main")

    if not commit_hash:
        return jsonify({"error": "commit_hash is required"}), 400

    db_ctx, _, forms_col, _, _, _ = get_collections()
    form = forms_col.find_one({"_id": obj_id})
    if not form:
        return jsonify({"error": "Form not found"}), 404

    target_commit = db_ctx["commits"].find_one({"form_id": obj_id, "hash": commit_hash})
    if not target_commit:
        return jsonify({"error": "Commit hash not found"}), 404

    forms_col.update_one(
        {"_id": obj_id},
        {"$set": {f"vcs_branches.{branch}": commit_hash, "updated_at": datetime.utcnow()}}
    )

    record_audit_log("git_revert", form_id=obj_id, details={"branch": branch, "commit_hash": commit_hash})
    return jsonify({"message": f"Branch '{branch}' reverted to commit '{commit_hash}'"}), 200

@app.route("/api/forms/<form_id>/tags", methods=["POST"])
@login_required
def git_create_tag(form_id):
    permission_ok, err_res = check_permission("form", form_id, ["Editor", "Admin"])
    if not permission_ok:
        return err_res

    try:
        obj_id = ObjectId(form_id)
    except Exception:
        return jsonify({"error": "Invalid form ID"}), 400

    data = request.json or {}
    tag_name = data.get("tag_name")
    commit_hash = data.get("commit_hash")

    if not tag_name or not commit_hash:
        return jsonify({"error": "tag_name and commit_hash are required"}), 400

    db_ctx, _, forms_col, _, _, _ = get_collections()
    form = forms_col.find_one({"_id": obj_id})
    if not form:
        return jsonify({"error": "Form not found"}), 404

    commit_exists = db_ctx["commits"].find_one({"form_id": obj_id, "hash": commit_hash})
    if not commit_exists:
        return jsonify({"error": "Commit not found"}), 404

    forms_col.update_one(
        {"_id": obj_id},
        {"$pull": {"vcs_tags": {"name": tag_name}}}
    )
    forms_col.update_one(
        {"_id": obj_id},
        {
            "$push": {"vcs_tags": {"name": tag_name, "commit_hash": commit_hash}},
            "$set": {"updated_at": datetime.utcnow()}
        }
    )

    record_audit_log("git_tag", form_id=obj_id, details={"tag": tag_name, "commit_hash": commit_hash})
    return jsonify({"message": f"Tag '{tag_name}' created pointing to '{commit_hash}'"}), 201

@app.route("/api/forms/<form_id>/tags", methods=["GET"])
@login_required
def git_list_tags(form_id):
    permission_ok, err_res = check_permission("form", form_id, ["Analyst", "Editor", "Admin"])
    if not permission_ok:
        return err_res

    try:
        obj_id = ObjectId(form_id)
    except Exception:
        return jsonify({"error": "Invalid form ID"}), 400

    db_ctx, _, forms_col, _, _, _ = get_collections()
    form = forms_col.find_one({"_id": obj_id})
    if not form:
        return jsonify({"error": "Form not found"}), 404

    tags_list = form.get("vcs_tags", [])
    if isinstance(tags_list, dict):  # Fallback just in case
        tags_dict = tags_list
    else:
        tags_dict = {t["name"]: t["commit_hash"] for t in tags_list if "name" in t and "commit_hash" in t}
    return jsonify(json_util_serialize(tags_dict)), 200

@app.route("/api/forms/<form_id>/commits/purge", methods=["POST"])
@login_required
def git_purge_commits(form_id):
    permission_ok, err_res = check_permission("form", form_id, ["Editor", "Admin"])
    if not permission_ok:
        return err_res

    try:
        obj_id = ObjectId(form_id)
    except Exception:
        return jsonify({"error": "Invalid form ID"}), 400

    db_ctx, _, forms_col, _, _, _ = get_collections()
    purged_count = GitVersionControl.purge_old_commits(forms_col, obj_id)
    return jsonify({"message": f"Purged {purged_count} unpublished commits older than 3 days"}), 200

@app.route("/api/forms/<form_id>/commits/<commit_hash>/keep", methods=["PATCH"])
@login_required
def git_keep_commit(form_id, commit_hash):
    permission_ok, err_res = check_permission("form", form_id, ["Editor", "Admin"])
    if not permission_ok:
        return err_res

    try:
        obj_id = ObjectId(form_id)
    except Exception:
        return jsonify({"error": "Invalid form ID"}), 400

    data = request.json or {}
    keep_val = data.get("keep", True)

    db_ctx, _, forms_col, _, _, _ = get_collections()
    commits_col = db_ctx["commits"]
    result = commits_col.update_one(
        {"form_id": obj_id, "hash": commit_hash},
        {"$set": {"keep": bool(keep_val)}}
    )
    if result.matched_count == 0:
        return jsonify({"error": "Commit not found"}), 404

    return jsonify({"message": f"Commit keep status set to {keep_val}"}), 200



# ==========================================
# 🔄 SYSTEM LIFECYCLE MANAGEMENT ENDPOINTS
# ==========================================

@app.route("/api/forms/<form_id>/lifecycle", methods=["PATCH"])
@login_required
def update_form_lifecycle(form_id):
    permission_ok, err_res = check_permission("form", form_id, ["Editor", "Admin"])
    if not permission_ok:
        return err_res

    try:
        obj_id = ObjectId(form_id)
    except Exception:
        return jsonify({"error": "Invalid form ID format"}), 400

    data = request.json or {}
    status = data.get("lifecycle")
    if not status or status not in ["Draft", "Published", "Paused", "Archived"]:
        return jsonify({"error": "Invalid lifecycle status value"}), 400

    db_ctx, _, forms_col, _, _, _ = get_collections()
    forms_col.update_one(
        {"_id": obj_id},
        {"$set": {"lifecycle": status, "updated_at": datetime.utcnow()}}
    )

    record_audit_log("update_form_lifecycle", form_id=obj_id, details={"lifecycle": status})
    return jsonify({"message": f"Form lifecycle updated to {status}"}), 200

@app.route("/api/org/lifecycle", methods=["PATCH"])
@login_required
@roles_required(["Admin"])
def update_org_lifecycle():
    org_id = get_organization_id()
    data = request.json or {}
    status = data.get("lifecycle")
    if not status or status not in ["Active", "Suspended", "Trial", "Enterprise"]:
        return jsonify({"error": "Invalid lifecycle status value"}), 400

    orgs_col = client[DB_NAME]["organizations"]
    orgs_col.update_one(
        {"_id": ObjectId(org_id)},
        {"$set": {"lifecycle": status}}
    )

    record_audit_log("update_org_lifecycle", details={"lifecycle": status})
    return jsonify({"message": f"Organization lifecycle updated to {status}"}), 200

@app.route("/api/org/users/<user_id>/lifecycle", methods=["PATCH"])
@login_required
@roles_required(["Admin"])
def update_user_lifecycle(user_id):
    try:
        user_obj_id = ObjectId(user_id)
    except Exception:
        return jsonify({"error": "Invalid user ID"}), 400

    org_id = get_organization_id()
    users_col = client[DB_NAME]["users"]
    user = users_col.find_one({"_id": user_obj_id, "organization_id": org_id})
    if not user:
        return jsonify({"error": "User not found in organization"}), 404

    data = request.json or {}
    status = data.get("status")
    if not status or status not in ["Active", "Suspended", "Invited", "Archived"]:
        return jsonify({"error": "Invalid user status value"}), 400

    users_col.update_one(
        {"_id": user_obj_id},
        {"$set": {"status": status, "updated_at": datetime.utcnow()}}
    )

    record_audit_log("update_user_lifecycle", details={"user_id": user_id, "status": status})
    return jsonify({"message": f"User status updated to {status}"}), 200


# ==========================================
# ⛓️ WORKFLOW EXECUTION & RUN AUDITING
# ==========================================

@app.route("/api/forms/<form_id>/workflows/runs", methods=["GET"])
@login_required
def get_workflow_runs(form_id):
    permission_ok, err_res = check_permission("form", form_id, ["Analyst", "Editor", "Admin"])
    if not permission_ok:
        return err_res

    try:
        obj_id = ObjectId(form_id)
    except Exception:
        return jsonify({"error": "Invalid form ID"}), 400

    db_ctx, _, _, _, _, _ = get_collections()
    runs = list(db_ctx["workflow_runs"].find({"form_id": obj_id}))
    return jsonify(json_util_serialize(runs)), 200

@app.route("/api/forms/<form_id>/workflows/failed-runs", methods=["GET"])
@login_required
def get_failed_workflow_runs(form_id):
    permission_ok, err_res = check_permission("form", form_id, ["Analyst", "Editor", "Admin"])
    if not permission_ok:
        return err_res

    try:
        obj_id = ObjectId(form_id)
    except Exception:
        return jsonify({"error": "Invalid form ID"}), 400

    db_ctx, _, _, _, _, _ = get_collections()
    failed_runs = list(db_ctx["failed_workflow_runs"].find({"form_id": obj_id}).sort("timestamp", -1))
    return jsonify(json_util_serialize(failed_runs)), 200

@app.route("/api/forms/<form_id>/workflows/trigger", methods=["POST"])
@login_required
def manual_trigger_workflow(form_id):
    permission_ok, err_res = check_permission("form", form_id, ["Editor", "Admin"])
    if not permission_ok:
        return err_res

    try:
        obj_id = ObjectId(form_id)
    except Exception:
        return jsonify({"error": "Invalid form ID"}), 400

    db_ctx, _, forms_col, _, _, _ = get_collections()
    form = forms_col.find_one({"_id": obj_id, "deleted": {"$ne": True}})
    if not form:
        return jsonify({"error": "Form not found"}), 404

    data = request.json or {}
    workflow_id = data.get("workflow_id")
    response_payload = data.get("response_payload", {})

    workflows = form.get("workflows", [])
    workflow = next((w for w in workflows if w.get("id") == workflow_id), None)
    if not workflow:
        return jsonify({"error": f"Workflow '{workflow_id}' not found on this form"}), 404

    PipelineEngine.execute_pipeline(workflow, form, response_payload, db=db_ctx)

    record_audit_log("manual_trigger_workflow", form_id=obj_id, details={"workflow_id": workflow_id})
    return jsonify({"message": "Workflow run dispatched asynchronously."}), 202


def resume_running_workflows():
    """
    Finds and resumes all workflows that were in RUNNING state prior to shutdown.
    """
    try:
        db_names = client.list_database_names()
        for name in db_names:
            if name == DB_NAME or name.startswith("form_db_"):
                db_ctx = client[name]
                running_runs = list(db_ctx["workflow_runs"].find({"status": "RUNNING"}))
                for run in running_runs:
                    form = db_ctx["forms"].find_one({"_id": run["form_id"]})
                    response = db_ctx["responses"].find_one({"_id": run["response_id"]})
                    if form and response:
                        workflows = form.get("workflows", [])
                        workflow = next((w for w in workflows if w.get("id") == run["workflow_id"]), None)
                        if workflow:
                            logger.info(f"Resuming aborted workflow run: {run['_id']}")
                            PipelineEngine.execute_pipeline(workflow, form, response, db=db_ctx)
    except Exception as e:
        logger.error(f"Startup workflow resumption failed: {str(e)}")


# ==========================================
# 🔔 NOTIFICATIONS ENDPOINTS
# ==========================================

@app.route("/api/notifications", methods=["GET"])
@login_required
def get_notifications():
    org_id = get_organization_id()
    user_id = get_user_id()
    
    db_ctx, _, _, _, _, _ = get_collections()
    query = {
        "organization_id": ObjectId(org_id),
        "$or": [
            {"user_id": ObjectId(user_id)},
            {"user_id": None}
        ]
    }
    notifications = list(db_ctx["notifications"].find(query).sort("created_at", -1))
    return jsonify(json_util_serialize(notifications)), 200

@app.route("/api/notifications/<notification_id>/read", methods=["PATCH"])
@login_required
def mark_notification_read(notification_id):
    try:
        obj_id = ObjectId(notification_id)
    except Exception:
        return jsonify({"error": "Invalid notification ID format"}), 400

    db_ctx, _, _, _, _, _ = get_collections()
    result = db_ctx["notifications"].update_one(
        {"_id": obj_id},
        {"$set": {"read": True}}
    )
    if result.matched_count == 0:
        return jsonify({"error": "Notification not found"}), 404

    return jsonify({"message": "Notification marked as read"}), 200


# ==========================================
# 📝 RESPONSE ACCESS ENDPOINTS (Version Compatibility Aware)
# ==========================================

@app.route("/api/responses/<response_id>", methods=["GET"])
@login_required
def get_response(response_id):
    try:
        obj_id = ObjectId(response_id)
    except Exception:
        return jsonify({"error": "Invalid response ID format"}), 400

    db_ctx, _, forms_col, _, responses_col, _ = get_collections()
    response = responses_col.find_one({"_id": obj_id})
    if not response:
        return jsonify({"error": "Response not found"}), 404

    permission_ok, err_res = check_permission("form", response["form_id"], ["Respondent", "Analyst", "Editor", "Admin"])
    if not permission_ok:
        return err_res

    form = forms_col.find_one({"_id": response["form_id"]})
    if not form:
        return jsonify({"error": "Associated form not found"}), 404

    view_version = request.args.get("view_version", type=int)
    answers = dict(response.get("answers", {}))
    
    sensitive_fields = []
    for v in form.get("versions", []):
        for sec in v.get("sections", []):
            for q in sec.get("questions", []):
                if q.get("properties", {}).get("sensitive", False) and q.get("id") not in sensitive_fields:
                    sensitive_fields.append(q.get("id"))
                    
    for sec in form.get("sections", []):
        for q in sec.get("questions", []):
            if q.get("properties", {}).get("sensitive", False) and q.get("id") not in sensitive_fields:
                sensitive_fields.append(q.get("id"))

    user_roles = get_user_roles()
    if any(role in user_roles for role in ["Analyst", "Editor", "Admin"]):
        answers = EncryptionHelper.process_sensitive_fields(answers, sensitive_fields, action="decrypt")

    if view_version and view_version != response.get("version", 1):
        target_questions = {}
        target_version_sections = []
        for v in form.get("versions", []):
            if v.get("version_number") == view_version:
                target_version_sections = v.get("sections", [])
                break
        if not target_version_sections and view_version == form.get("current_version", 1):
            target_version_sections = form.get("sections", [])
            
        for sec in target_version_sections:
            for q in sec.get("questions", []):
                target_questions[q["id"]] = q
                
        aligned_answers = {}
        for q_id, q in target_questions.items():
            if q_id in answers:
                aligned_answers[q_id] = answers[q_id]
        
        for q_id, val in answers.items():
            if q_id not in aligned_answers:
                aligned_answers[q_id] = val
                
        answers = aligned_answers

    response_copy = dict(response)
    response_copy["answers"] = answers
    return jsonify(json_util_serialize(response_copy)), 200

@app.route("/api/forms/<form_id>/responses", methods=["GET"])
@login_required
def get_form_responses(form_id):
    try:
        obj_id = ObjectId(form_id)
    except Exception:
        return jsonify({"error": "Invalid form ID format"}), 400

    permission_ok, err_res = check_permission("form", obj_id, ["Analyst", "Editor", "Admin"])
    if not permission_ok:
        return err_res

    db_ctx, _, forms_col, _, responses_col, _ = get_collections()
    form = forms_col.find_one({"_id": obj_id})
    if not form:
        return jsonify({"error": "Form not found"}), 404

    responses = list(responses_col.find({"form_id": obj_id}))
    
    sensitive_fields = []
    for sec in form.get("sections", []):
        for q in sec.get("questions", []):
            if q.get("properties", {}).get("sensitive", False):
                sensitive_fields.append(q.get("id"))
                
    for r in responses:
        r["answers"] = EncryptionHelper.process_sensitive_fields(r.get("answers", {}), sensitive_fields, action="decrypt")
        
    return jsonify(json_util_serialize(responses)), 200


if __name__ == "__main__":
    resume_running_workflows()
    app.run(host="0.0.0.0", port=5000, debug=True)

