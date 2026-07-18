"""MongoEngine enterprise security and hardening models.

Collections:
- webhook_delivery_logs  : Tracks attempts, payload sizes, status codes, and latency for webhooks.
- logic_sub_graphs       : Reusable logic workflow sub-graphs with custom input/output signatures.
- tenant_residency_configs: Enterprise settings for data geographic pinning and local compliance standards.
- signed_audit_logs      : Tamper-evident audit logs secured with SHA-256 cryptographical hashes.
- active_session_presences: Collaboration controls tracking user editing presence and draft locks.
- data_retention_policies: Governance configs defining automatic archival and deletion schedules.
- webhook_policy_configs : Operational configs defining custom retries, timeouts, and warning levels.
"""

from __future__ import annotations
from datetime import datetime, timezone
import hashlib
from app.extensions import db


class WebhookDeliveryLog(db.Document):
    uuid = db.StringField(required=True, unique=True)
    webhook_config_uuid = db.StringField(required=True)
    form_uuid = db.StringField(required=True)
    event_type = db.StringField(required=True)
    url = db.StringField(required=True)
    request_headers = db.MapField(db.StringField(), default=dict)
    request_payload = db.DictField()
    response_status = db.IntField()
    response_headers = db.MapField(db.StringField(), default=dict)
    response_payload = db.StringField()
    duration_ms = db.IntField()
    status = db.StringField(required=True, choices=("success", "failed", "retrying"))
    attempt_number = db.IntField(default=1)
    max_attempts = db.IntField(default=5)
    error_message = db.StringField()
    created_at = db.DateTimeField(default=lambda: datetime.now(timezone.utc))
    updated_at = db.DateTimeField(default=lambda: datetime.now(timezone.utc))

    meta = {
        "collection": "webhook_delivery_logs",
        "indexes": [
            "uuid",
            "webhook_config_uuid",
            "form_uuid",
            "status",
            "created_at",
        ],
    }

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now(timezone.utc)
        return super().save(*args, **kwargs)


class LogicSubGraph(db.Document):
    uuid = db.StringField(required=True, unique=True)
    name = db.StringField(required=True)
    description = db.StringField()
    organization_id = db.StringField(required=True)
    input_ports = db.ListField(db.DictField(), default=list)
    output_ports = db.ListField(db.DictField(), default=list)
    nodes = db.ListField(db.DictField(), default=list)
    connections = db.ListField(db.DictField(), default=list)
    version = db.IntField(default=1)
    is_template = db.BooleanField(default=False)
    created_at = db.DateTimeField(default=lambda: datetime.now(timezone.utc))
    updated_at = db.DateTimeField(default=lambda: datetime.now(timezone.utc))

    meta = {
        "collection": "logic_sub_graphs",
        "indexes": [
            "uuid",
            "organization_id",
            "name",
            "is_template",
        ],
    }

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now(timezone.utc)
        return super().save(*args, **kwargs)


class TenantResidencyConfig(db.Document):
    organization_id = db.StringField(required=True, unique=True)
    primary_region = db.StringField(required=True, default="us-east")
    allowed_storage_regions = db.ListField(db.StringField(), default=list)
    compliance_standards = db.ListField(db.StringField(), default=list)
    local_encryption_key_arn = db.StringField()
    regional_backup_enabled = db.BooleanField(default=True)
    disaster_recovery_target = db.StringField()
    updated_at = db.DateTimeField(default=lambda: datetime.now(timezone.utc))

    meta = {
        "collection": "tenant_residency_configs",
        "indexes": [
            "organization_id",
        ],
    }

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now(timezone.utc)
        return super().save(*args, **kwargs)


class SignedAuditLog(db.Document):
    uuid = db.StringField(required=True, unique=True)
    response_uuid = db.StringField(required=True)
    actor_user_uuid = db.StringField()
    action = db.StringField(required=True)
    changes = db.DictField()
    timestamp = db.DateTimeField(default=lambda: datetime.now(timezone.utc))
    signature = db.StringField()  # Integrity hash (tamper evidence)
    previous_hash = db.StringField()  # Block-linked hash chain

    meta = {
        "collection": "signed_audit_logs",
        "indexes": [
            "uuid",
            "response_uuid",
            "actor_user_uuid",
            "timestamp",
        ],
    }

    def generate_hash(self) -> str:
        # Build deterministic payload string using string formatted time to avoid timezone offset shifts
        ts_val = self.timestamp.strftime("%Y-%m-%d %H:%M:%S") if self.timestamp else "0"
        payload = f"{self.uuid}:{self.response_uuid}:{self.actor_user_uuid}:{self.action}:{str(self.changes)}:{ts_val}:{self.previous_hash or ''}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def sign(self, prev_hash: str = ""):
        self.previous_hash = prev_hash
        self.signature = self.generate_hash()

    def verify(self) -> bool:
        return self.signature == self.generate_hash()


class ActiveSessionPresence(db.Document):
    uuid = db.StringField(required=True, unique=True)
    workspace_uuid = db.StringField(required=True)
    resource_uuid = db.StringField(required=True)
    user_uuid = db.StringField(required=True)
    user_name = db.StringField(required=True)
    active_section = db.StringField()
    is_locked = db.BooleanField(default=False)
    last_heartbeat = db.DateTimeField(default=lambda: datetime.now(timezone.utc))

    meta = {
        "collection": "active_session_presences",
        "indexes": [
            "uuid",
            "workspace_uuid",
            "resource_uuid",
            {"fields": ["last_heartbeat"], "expireAfterSeconds": 60},
        ],
    }


class DataRetentionPolicy(db.Document):
    uuid = db.StringField(required=True, unique=True)
    organization_id = db.StringField(required=True, unique=True)
    retention_days = db.IntField(default=365)
    archival_target = db.StringField(
        choices=("cold_storage", "delete"), default="delete"
    )
    consent_tracking_required = db.BooleanField(default=True)
    updated_at = db.DateTimeField(default=lambda: datetime.now(timezone.utc))

    meta = {
        "collection": "data_retention_policies",
    }


class WebhookPolicyConfig(db.Document):
    uuid = db.StringField(required=True, unique=True)
    webhook_config_uuid = db.StringField(required=True, unique=True)
    retry_policy = db.StringField(
        choices=("immediate", "exponential_backoff", "linear"),
        default="exponential_backoff",
    )
    timeout_seconds = db.IntField(default=30)
    failure_threshold_pct = db.IntField(default=15)
    alert_emails = db.ListField(db.StringField(), default=list)

    meta = {
        "collection": "webhook_policy_configs",
    }
