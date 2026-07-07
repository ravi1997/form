from datetime import datetime

from app.extensions import db


class UserSession(db.Document):
    session_uuid = db.StringField(required=True, unique=True)
    user_uuid = db.StringField(required=True)
    email = db.StringField(required=True)

    refresh_jti = db.StringField(required=True)
    refresh_token_hash = db.StringField(required=True)
    refresh_expires_at = db.DateTimeField(required=True)

    device_name = db.StringField()
    user_agent = db.StringField()
    ip_address = db.StringField()

    created_at = db.DateTimeField(default=datetime.utcnow)
    last_seen_at = db.DateTimeField(default=datetime.utcnow)

    is_active = db.BooleanField(default=True)
    revoked_at = db.DateTimeField()
    revoked_reason = db.StringField()

    meta = {
        "collection": "user_sessions",
        "indexes": [
            "session_uuid",
            "user_uuid",
            "is_active",
            "last_seen_at",
            "refresh_jti",
            "refresh_token_hash",
        ],
    }


class RateLimitCounter(db.Document):
    scope = db.StringField(required=True)
    key = db.StringField(required=True)
    bucket_epoch = db.IntField(required=True)
    window_seconds = db.IntField(required=True)
    count = db.IntField(default=0)
    expires_at = db.DateTimeField(required=True)

    meta = {
        "collection": "rate_limit_counters",
        "indexes": [
            {"fields": ["scope", "key", "bucket_epoch"], "unique": True},
            {"fields": ["expires_at"], "expireAfterSeconds": 0},
        ],
    }


class SessionAuditLog(db.Document):
    actor_user_uuid = db.StringField(required=True)
    target_user_uuid = db.StringField(required=True)
    session_uuid = db.StringField()
    action = db.StringField(required=True)
    reason = db.StringField()
    ip_address = db.StringField()
    user_agent = db.StringField()
    metadata = db.DictField()
    created_at = db.DateTimeField(default=datetime.utcnow)

    meta = {
        "collection": "session_audit_logs",
        "indexes": [
            "actor_user_uuid",
            "target_user_uuid",
            "session_uuid",
            "action",
            "created_at",
        ],
    }


class TokenBlocklist(db.Document):
    jti = db.StringField(required=True, unique=True)
    token_hash = db.StringField(required=True, unique=True)
    user_uuid = db.StringField(required=True)
    token_type = db.StringField(choices=("refresh",), default="refresh")
    revoked_at = db.DateTimeField(default=datetime.utcnow)
    expires_at = db.DateTimeField(required=True)
    reason = db.StringField(default="logout")

    meta = {
        "collection": "token_blocklist",
        "indexes": [
            "jti",
            "token_hash",
            "user_uuid",
            "token_type",
            {"fields": ["expires_at"], "expireAfterSeconds": 0},
        ],
    }
