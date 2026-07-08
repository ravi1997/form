from app.extensions import db
from datetime import datetime, timezone
from mongoengine.errors import ValidationError

RATE_LIMIT_SCOPES = (
    "global",  # Apply to all users
    "user",  # Per-user limit
    "route",  # Per-route limit
    "organization",  # Per-organization limit
)

RATE_LIMIT_UNITS = (
    "second",
    "minute",
    "hour",
    "day",
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RateLimitConfig(db.Document):
    """
    Stores rate limit configurations for routes and users.

    Hierarchy:
    1. User-specific overrides (highest priority)
    2. Organization-specific limits
    3. Route-specific defaults
    4. Global defaults (lowest priority)
    """

    # Unique identifier for this rate limit rule
    rule_id = db.StringField(required=True, unique=True)

    # Scope: global, user, route, organization
    scope = db.StringField(choices=RATE_LIMIT_SCOPES, default="global", required=True)

    # Target (empty for global, UUID for user/org, route path for route)
    target_id = db.StringField()  # user_uuid, org_uuid, or route_path

    # Rate limit parameters
    max_requests = db.IntField(required=True, min_value=1)
    window_size = db.IntField(required=True, min_value=1)  # Time window
    unit = db.StringField(choices=RATE_LIMIT_UNITS, default="minute", required=True)

    # HTTP method (optional, empty means all methods)
    http_method = db.StringField()  # GET, POST, PUT, DELETE, etc.

    # Route pattern (optional for global limits)
    route_pattern = db.StringField()

    # Description
    description = db.StringField()

    # Is this rule active?
    is_active = db.BooleanField(default=True)

    # Priority (higher number = higher priority)
    priority = db.IntField(default=0)

    # Created and updated timestamps
    created_at = db.DateTimeField(default=utcnow)
    updated_at = db.DateTimeField(default=utcnow)
    created_by = db.ReferenceField("User")
    updated_by = db.ReferenceField("User")

    meta = {
        "collection": "rate_limit_configs",
        "indexes": [
            "rule_id",
            "scope",
            "target_id",
            "route_pattern",
            "is_active",
            ("scope", "target_id"),
            ("route_pattern", "http_method"),
        ],
    }

    def clean(self):
        if self.scope == "global":
            self.target_id = None
        elif self.scope in ["user", "organization"] and not self.target_id:
            raise ValidationError(f"{self.scope} scope requires target_id")

        if self.http_method and self.http_method.upper() not in [
            "GET",
            "POST",
            "PUT",
            "DELETE",
            "PATCH",
            "HEAD",
            "OPTIONS",
        ]:
            raise ValidationError("Invalid HTTP method")

        if self.max_requests <= 0:
            raise ValidationError("max_requests must be greater than 0")

        if self.window_size <= 0:
            raise ValidationError("window_size must be greater than 0")

    def save(self, *args, **kwargs):
        self.updated_at = utcnow()
        return super().save(*args, **kwargs)

    def to_dict(self):
        return {
            "rule_id": self.rule_id,
            "scope": self.scope,
            "target_id": self.target_id,
            "max_requests": self.max_requests,
            "window_size": self.window_size,
            "unit": self.unit,
            "http_method": self.http_method,
            "route_pattern": self.route_pattern,
            "description": self.description,
            "is_active": self.is_active,
            "priority": self.priority,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class RateLimitLog(db.Document):
    """
    Logs rate limit hits for audit and analytics purposes.
    """

    user_id = db.StringField()  # User UUID who hit the limit
    organization_id = db.StringField()  # Organization UUID
    route_pattern = db.StringField()
    http_method = db.StringField()
    ip_address = db.StringField()

    # Rule that was applied
    rule_id = db.StringField()

    # Was the request allowed or blocked?
    blocked = db.BooleanField(default=False)

    # Current usage at time of request
    request_count = db.IntField()
    max_allowed = db.IntField()

    timestamp = db.DateTimeField(default=utcnow)

    meta = {
        "collection": "rate_limit_logs",
        "indexes": [
            "user_id",
            "organization_id",
            "route_pattern",
            "blocked",
            "timestamp",
            ("user_id", "timestamp"),
            ("organization_id", "timestamp"),
            ("route_pattern", "timestamp"),
            ("blocked", "timestamp"),
            ("rule_id", "timestamp"),
        ],
    }
