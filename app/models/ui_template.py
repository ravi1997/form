from __future__ import annotations

from datetime import datetime, timezone

from mongoengine.errors import ValidationError

from app.extensions import db

TEMPLATE_SCOPE_CHOICES = ("global", "organization", "project")
TEMPLATE_VISIBILITY_CHOICES = ("private", "shared", "public")
TEMPLATE_STATUS_CHOICES = ("draft", "published", "archived", "deprecated")
TEMPLATE_REVISION_STATUS_CHOICES = ("draft", "published", "archived")


def _collect_revision_uuids(revisions):
    uuids = []
    for revision in revisions or []:
        if revision.uuid:
            uuids.append(revision.uuid)
    return uuids


def _collect_revision_versions(revisions):
    versions = []
    for revision in revisions or []:
        if revision.version:
            versions.append(revision.version)
    return versions


class TemplateRevision(db.EmbeddedDocument):
    uuid = db.StringField(required=True)
    version = db.IntField(required=True, min_value=1)
    schema_version = db.IntField(required=True, min_value=1, default=1)
    config = db.DictField(default=dict)
    change_note = db.StringField()
    created_by = db.ReferenceField("User")
    created_at = db.DateTimeField(default=lambda: datetime.now(timezone.utc))
    status = db.StringField(
        choices=TEMPLATE_REVISION_STATUS_CHOICES,
        default="draft",
    )

    def clean(self):
        if self.config is None:
            self.config = {}
        if not isinstance(self.config, dict):
            raise ValidationError("Template revision config must be an object")


class _BaseTemplate(db.Document):
    meta = {"abstract": True}

    uuid = db.StringField(required=True, unique=True)
    name = db.StringField(required=True)
    description = db.StringField()
    tags = db.ListField(db.StringField(), default=list)
    icon = db.StringField()

    scope_type = db.StringField(choices=TEMPLATE_SCOPE_CHOICES, default="global")
    scope_uuid = db.StringField()
    visibility = db.StringField(
        choices=TEMPLATE_VISIBILITY_CHOICES,
        default="private",
    )

    admins = db.ListField(db.ReferenceField("User"), default=list)
    editors = db.ListField(db.ReferenceField("User"), default=list)
    viewers = db.ListField(db.ReferenceField("User"), default=list)

    revisions = db.ListField(db.EmbeddedDocumentField(TemplateRevision), default=list)
    current_revision_uuid = db.StringField()
    usage_count = db.IntField(min_value=0, default=0)

    status = db.StringField(choices=TEMPLATE_STATUS_CHOICES, default="draft")
    created_at = db.DateTimeField(default=lambda: datetime.now(timezone.utc))
    updated_at = db.DateTimeField(default=lambda: datetime.now(timezone.utc))
    deleted_at = db.DateTimeField()
    deleted_by = db.ReferenceField("User")

    def clean(self):
        if self.scope_type == "global":
            self.scope_uuid = None
        elif not self.scope_uuid:
            raise ValidationError("scope_uuid is required for non-global templates")

        revision_uuids = _collect_revision_uuids(self.revisions)
        if len(revision_uuids) != len(set(revision_uuids)):
            raise ValidationError("Duplicate revision UUIDs are not allowed")

        revision_versions = _collect_revision_versions(self.revisions)
        if len(revision_versions) != len(set(revision_versions)):
            raise ValidationError("Duplicate revision versions are not allowed")

        if self.current_revision_uuid:
            matches = [
                revision
                for revision in (self.revisions or [])
                if revision.uuid == self.current_revision_uuid
            ]
            if not matches:
                raise ValidationError("current_revision_uuid must reference a revision")
            if self.status == "published" and matches[0].status != "published":
                raise ValidationError(
                    "current_revision_uuid must point to a published revision when template is published"
                )
        elif self.status == "published":
            raise ValidationError(
                "Published templates must have current_revision_uuid set"
            )

        if self.status == "deprecated":
            if not self.deleted_at:
                self.deleted_at = datetime.now(timezone.utc)
        elif self.status != "deprecated":
            self.deleted_at = None
            self.deleted_by = None

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now(timezone.utc)
        return super().save(*args, **kwargs)


class ThemeTemplate(_BaseTemplate):
    meta = {
        "collection": "theme_templates",  # type: ignore[dict-item]
        "indexes": [  # type: ignore[dict-item]
            "uuid",
            "status",
            "scope_type",
            "scope_uuid",
            "visibility",
            "tags",
            "current_revision_uuid",
            "usage_count",
        ],
    }


class LayoutTemplate(_BaseTemplate):
    meta = {
        "collection": "layout_templates",  # type: ignore[dict-item]
        "indexes": [  # type: ignore[dict-item]
            "uuid",
            "status",
            "scope_type",
            "scope_uuid",
            "visibility",
            "tags",
            "current_revision_uuid",
            "usage_count",
        ],
    }
