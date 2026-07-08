from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


APPROVAL_STATE_CHOICES = ("draft", "review", "published", "deprecated", "archived")
ASYNC_JOB_STATE_CHOICES = ("queued", "running", "success", "failed", "timeout")


class ConditionPresetVersion(db.EmbeddedDocument):
    version = db.IntField(required=True, min_value=1)
    condition_snapshot = db.DictField(required=True)
    changelog = db.StringField()
    created_at = db.DateTimeField(default=lambda: datetime.now(timezone.utc))


class ConditionPreset(db.Document):
    uuid = db.StringField(required=True, unique=True)
    name = db.StringField(required=True)
    description = db.StringField()
    tags = db.ListField(db.StringField(), default=list)
    condition_uuid = db.StringField(required=True)
    condition_snapshot = db.DictField(required=True)
    references = db.ListField(db.StringField(), default=list)
    auto_update = db.BooleanField(default=False)
    status = db.StringField(
        default="active", choices=("active", "inactive", "archived")
    )
    current_version = db.IntField(default=1)
    versions = db.ListField(
        db.EmbeddedDocumentField(ConditionPresetVersion), default=list
    )
    created_by = db.StringField()
    updated_by = db.StringField()
    created_at = db.DateTimeField(default=lambda: datetime.now(timezone.utc))
    updated_at = db.DateTimeField(default=lambda: datetime.now(timezone.utc))

    meta = {
        "collection": "condition_presets",
        "indexes": ["uuid", "name", "condition_uuid", "status", "updated_at"],
    }

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now(timezone.utc)
        if not self.versions:
            self.versions = [
                ConditionPresetVersion(
                    version=self.current_version,
                    condition_snapshot=self.condition_snapshot,
                    changelog="initial",
                )
            ]
        return super().save(*args, **kwargs)


class ConditionVersion(db.Document):
    condition_uuid = db.StringField(required=True)
    version = db.IntField(required=True, min_value=1)
    snapshot = db.DictField(required=True)
    diff = db.DictField(default=dict)
    changelog = db.StringField()
    action = db.StringField(default="update")
    actor_user_uuid = db.StringField()
    created_at = db.DateTimeField(default=lambda: datetime.now(timezone.utc))

    meta = {
        "collection": "condition_versions",
        "indexes": ["condition_uuid", "version", "created_at"],
    }


class ConditionApprovalAudit(db.Document):
    condition_uuid = db.StringField(required=True)
    from_state = db.StringField(choices=APPROVAL_STATE_CHOICES)
    to_state = db.StringField(required=True, choices=APPROVAL_STATE_CHOICES)
    actor_user_uuid = db.StringField()
    note = db.StringField()
    validation_errors = db.ListField(db.StringField(), default=list)
    created_at = db.DateTimeField(default=lambda: datetime.now(timezone.utc))

    meta = {
        "collection": "condition_approval_audit",
        "indexes": ["condition_uuid", "created_at", "to_state"],
    }


class ConditionAsyncJob(db.Document):
    job_id = db.StringField(required=True, unique=True)
    condition_uuid = db.StringField(required=True)
    status = db.StringField(
        required=True, choices=ASYNC_JOB_STATE_CHOICES, default="queued"
    )
    context = db.DictField(default=dict)
    result = db.BooleanField()
    error = db.StringField()
    trace = db.ListField(db.DictField(), default=list)
    retries = db.IntField(default=0)
    fallback_result = db.BooleanField(default=False)
    timeout_ms = db.IntField(default=1000)
    started_at = db.DateTimeField()
    completed_at = db.DateTimeField()
    created_at = db.DateTimeField(default=lambda: datetime.now(timezone.utc))
    updated_at = db.DateTimeField(default=lambda: datetime.now(timezone.utc))

    meta = {
        "collection": "condition_async_jobs",
        "indexes": ["job_id", "condition_uuid", "status", "created_at"],
    }

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now(timezone.utc)
        return super().save(*args, **kwargs)


class ConditionEvaluationStat(db.Document):
    condition_uuid = db.StringField(required=True)
    endpoint = db.StringField()
    matched = db.BooleanField(required=True)
    duration_ms = db.FloatField(required=True)
    operator = db.StringField()
    condition_type = db.StringField()
    created_at = db.DateTimeField(default=lambda: datetime.now(timezone.utc))

    meta = {
        "collection": "condition_evaluation_stats",
        "indexes": [
            "condition_uuid",
            "created_at",
            "matched",
            "operator",
            "condition_type",
        ],
    }
