from __future__ import annotations

from flask import request

from app.models.ui_template import LayoutTemplate, TemplateRevision, ThemeTemplate
from app.models.user import User
from app.schemas.common import SchemaModel
from app.services.auth import AuthError
from app.services.rbac import resolve_access_identity_from_header

try:
    from flask_openapi3 import APIBlueprint, Tag
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("flask-openapi3 is required") from exc


ui_tag = Tag(name="UI Templates", description="Theme and layout template APIs")
ui_api = APIBlueprint("ui_templates", __name__, url_prefix="/api/v1/ui")


class TemplateRevisionPath(SchemaModel):
    template_uuid: str
    revision_uuid: str


def _resolve_user_from_auth() -> User | None:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header:
        return None
    try:
        payload = resolve_access_identity_from_header(auth_header)
    except AuthError:
        return None
    user_uuid = (
        payload.get("user_id")
        or payload.get("user_uuid")
        or payload.get("sub")
        or payload.get("uuid")
    )
    if not user_uuid:
        return None
    return User.objects(uuid=user_uuid).first()


def _resolve_users(uuids: list[str]) -> list[User]:
    users = []
    for user_uuid in uuids or []:
        user = User.objects(uuid=user_uuid).first()
        if user:
            users.append(user)
    return users


def _serialize_template(template) -> dict:
    return {
        "uuid": template.uuid,
        "name": template.name,
        "scope_type": template.scope_type,
        "scope_uuid": template.scope_uuid,
        "visibility": template.visibility,
        "status": template.status,
        "admins": [user.uuid for user in template.admins or []],
        "editors": [user.uuid for user in template.editors or []],
        "viewers": [user.uuid for user in template.viewers or []],
        "current_revision_uuid": template.current_revision_uuid,
        "revisions": [
            {
                "uuid": revision.uuid,
                "version": revision.version,
                "schema_version": revision.schema_version,
                "config": dict(revision.config or {}),
                "status": revision.status,
            }
            for revision in template.revisions or []
        ],
    }


def _create_template(model):
    body = request.get_json(silent=True) or {}
    template = model(
        uuid=body.get("uuid"),
        name=body.get("name"),
        description=body.get("description"),
        tags=body.get("tags", []),
        icon=body.get("icon"),
        scope_type=body.get("scope_type", "global"),
        scope_uuid=body.get("scope_uuid"),
        visibility=body.get("visibility", "private"),
        admins=_resolve_users(body.get("admins", [])),
        editors=_resolve_users(body.get("editors", [])),
        viewers=_resolve_users(body.get("viewers", [])),
        status=body.get("status", "draft"),
    )

    initial_revision = body.get("initial_revision")
    if initial_revision:
        template.revisions = [
            TemplateRevision(
                uuid=initial_revision.get("uuid"),
                version=1,
                schema_version=initial_revision.get("schema_version", 1),
                config=initial_revision.get("config", {}),
                status=initial_revision.get("status", "draft"),
            )
        ]

    template.save()
    return _serialize_template(template), 201


def _publish_template(model, template_uuid: str, revision_uuid: str):
    template = model.objects(uuid=template_uuid).first()
    if not template:
        return {"message": "Template not found"}, 404

    actor = _resolve_user_from_auth()
    if not actor:
        return {"message": "Unauthorized"}, 401

    admin_uuids = {user.uuid for user in template.admins or []}
    if not actor.is_super_admin and actor.uuid not in admin_uuids:
        return {"message": "Forbidden"}, 403

    target_revision = None
    for revision in template.revisions or []:
        if revision.uuid == revision_uuid:
            target_revision = revision
            break
    if not target_revision:
        return {"message": "Revision not found"}, 404

    target_revision.status = "published"
    template.current_revision_uuid = revision_uuid
    template.status = "published"
    template.save()
    return _serialize_template(template)


@ui_api.post("/theme-templates", tags=[ui_tag])
def create_theme_template():
    return _create_template(ThemeTemplate)


@ui_api.post(
    "/theme-templates/<template_uuid>/revisions/<revision_uuid>/publish", tags=[ui_tag]
)
def publish_theme_revision(path: TemplateRevisionPath):
    return _publish_template(ThemeTemplate, path.template_uuid, path.revision_uuid)


@ui_api.post("/layout-templates", tags=[ui_tag])
def create_layout_template():
    return _create_template(LayoutTemplate)


@ui_api.post(
    "/layout-templates/<template_uuid>/revisions/<revision_uuid>/publish", tags=[ui_tag]
)
def publish_layout_revision(path: TemplateRevisionPath):
    return _publish_template(LayoutTemplate, path.template_uuid, path.revision_uuid)
