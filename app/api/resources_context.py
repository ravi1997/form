"""Shared helper functions for resources route handlers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Type


from app.models.form import Condition, Form, Project, Question, Section, Version
from app.models.user import User
from app.api.resources_support import _error
from app.schemas.version import VersionCreateInput, VersionUpdateInput


def _resolve_refs(model: Type[Any], uuids: List[str], label: str) -> List[Any]:
    resolved = []
    for value in uuids or []:
        doc = model.objects(uuid=value).first()
        if not doc:
            raise ValueError(f"{label} uuid not found: {value}")
        resolved.append(doc)
    return resolved


def _resolve_user(user_uuid: Optional[str]) -> Optional[User]:
    if not user_uuid:
        return None
    return User.objects(uuid=user_uuid).first()


def _version_from_create(version: VersionCreateInput) -> Version:
    return Version(
        uuid=version.uuid,
        major=version.major,
        minor=version.minor,
        patch=version.patch,
        status=version.status,
        created=datetime.now(timezone.utc),
        created_by=_resolve_user(version.created_by),
    )


def _apply_version_update(version: Version, body: VersionUpdateInput) -> None:
    if body.major is not None:
        version.major = body.major
    if body.minor is not None:
        version.minor = body.minor
    if body.patch is not None:
        version.patch = body.patch
    if body.status is not None:
        version.status = body.status
    if body.updated_by is not None:
        version.updated_by = _resolve_user(body.updated_by)
    version.updated = datetime.now(timezone.utc)


def _append_version(doc: Any, body: VersionCreateInput) -> None:
    if any(v.uuid == body.uuid for v in (doc.versions or [])):
        raise ValueError("Version uuid already exists")
    doc.versions.append(_version_from_create(body))


def _update_version(doc: Any, version_uuid: str, body: VersionUpdateInput) -> Version:
    for version in doc.versions or []:
        if version.uuid == version_uuid:
            _apply_version_update(version, body)
            return version
    raise ValueError("Version not found")


def _project_form_uuids(project: Project) -> set[str]:
    return {
        str(getattr(form, "uuid", ""))
        for form in (project.forms or [])
        if getattr(form, "uuid", None)
    }


def _form_section_uuids(form: Form) -> set[str]:
    uuids: set[str] = set()
    for section_ids in (form.sections or {}).values():
        for section_uuid in section_ids or []:
            uuids.add(str(section_uuid))
    return uuids


def _section_question_uuids(section: Section) -> set[str]:
    uuids: set[str] = set()
    for question_ids in (section.questions or {}).values():
        for question_uuid in question_ids or []:
            uuids.add(str(question_uuid))
    return uuids


def _resolve_version_key(
    versions: list[Any], versioned_map: Dict[str, list[str]], requested: Optional[str]
) -> str:
    available = [str(v.uuid) for v in (versions or []) if getattr(v, "uuid", None)]

    if requested:
        if requested not in available:
            raise ValueError(f"Unknown version_uuid: {requested}")
        return requested

    if len(available) == 1:
        return available[0]

    existing_keys = list((versioned_map or {}).keys())
    if len(existing_keys) == 1:
        return str(existing_keys[0])

    raise ValueError("version_uuid is required when multiple versions exist")


def _get_project_or_error(project_uuid: str):
    project = Project.objects(uuid=project_uuid).first()
    if not project:
        return None, _error("Project not found", 404)
    return project, None


def _get_form_for_project(project: Project, form_uuid: str):
    if form_uuid not in _project_form_uuids(project):
        return None, _error("Form not found under project", 404)
    form = Form.objects(uuid=form_uuid).first()
    if not form:
        return None, _error("Form not found", 404)
    return form, None


def _get_section_for_form(form: Form, section_uuid: str):
    if section_uuid not in _form_section_uuids(form):
        return None, _error("Section not found under form", 404)
    section = Section.objects(uuid=section_uuid).first()
    if not section:
        return None, _error("Section not found", 404)
    return section, None


def _get_question_for_section(section: Section, question_uuid: str):
    if question_uuid not in _section_question_uuids(section):
        return None, _error("Question not found under section", 404)
    question = Question.objects(uuid=question_uuid).first()
    if not question:
        return None, _error("Question not found", 404)
    return question, None


def _get_choice_for_question(question: Question, choice_uuid: str):
    for index, choice in enumerate(question.choices or []):
        if str(choice.uuid) == choice_uuid:
            return choice, index, None
    return None, None, _error("Choice not found", 404)


def _get_condition_or_error(condition_uuid: str):
    condition = Condition.objects(uuid=condition_uuid).first()
    if not condition:
        return None, _error("Condition not found", 404)
    return condition, None


def _apply_project_update(project: Project, body) -> None:
    data = body.model_dump(exclude_none=True)
    from app.models.user import Organization

    if "name" in data:
        project.name = data["name"]
    if "admins" in data:
        project.admins = _resolve_refs(User, data["admins"], "admin")
    if "members" in data:
        project.members = _resolve_refs(User, data["members"], "member")
    if "viewers" in data:
        project.viewers = _resolve_refs(User, data["viewers"], "viewer")
    if "forms" in data:
        project.forms = _resolve_refs(Form, data["forms"], "form")
    if "organizations" in data:
        project.organizations = _resolve_refs(
            Organization, data["organizations"], "organization"
        )
    if "tags" in data:
        project.tags = data["tags"]
    if "status" in data:
        project.status = data["status"]


def _apply_form_update(form: Form, body) -> None:
    data = body.model_dump(exclude_none=True)
    if "sections" in data:
        form.sections = data["sections"]
    if "editors" in data:
        form.editors = _resolve_refs(User, data["editors"], "editor")
    if "viewers" in data:
        form.viewers = _resolve_refs(User, data["viewers"], "viewer")
    if "reviewers" in data:
        form.reviewers = _resolve_refs(User, data["reviewers"], "reviewer")
    if "approvers" in data:
        form.approvers = _resolve_refs(User, data["approvers"], "approver")
    if "submitters" in data:
        form.submitters = _resolve_refs(User, data["submitters"], "submitter")
    if "requires_reviewer" in data:
        form.requires_reviewer = data["requires_reviewer"]
    if "requires_approver" in data:
        form.requires_approver = data["requires_approver"]
    if "min_reviewers_required" in data:
        form.min_reviewers_required = data["min_reviewers_required"]
    if "min_approvers_required" in data:
        form.min_approvers_required = data["min_approvers_required"]
    if "validation_conditions" in data:
        form.validation_conditions = _resolve_refs(
            Condition, data["validation_conditions"], "validation_condition"
        )
    if "validation_condition_messages" in data:
        form.validation_condition_messages = data["validation_condition_messages"]
    if "child_sections" in data:
        form.child_sections = _resolve_refs(Section, data["child_sections"], "section")
    for key in (
        "tags",
        "icon",
        "theme_template_uuid",
        "theme_revision_uuid",
        "layout_template_uuid",
        "layout_revision_uuid",
        "ui_overrides",
        "is_public",
        "status",
    ):
        if key in data:
            setattr(form, key, data[key])


def _apply_section_update(section: Section, body) -> None:
    data = body.model_dump(exclude_none=True)
    for key in (
        "questions",
        "add_button",
        "is_repeatable",
        "check_repeat_on",
        "min_repeatable_count",
        "max_repeatable_count",
        "title",
        "description",
        "isDeleted",
        "deletedAt",
        "deleted_at",
        "tags",
        "icon",
        "status",
        "validation_condition_messages",
    ):
        if key in data:
            setattr(section, key, data[key])
    if "repeatable_condition" in data:
        section.repeatable_condition = Condition.objects(
            uuid=data["repeatable_condition"]
        ).first()
    if "visibility_condition" in data:
        section.visibility_condition = Condition.objects(
            uuid=data["visibility_condition"]
        ).first()
    if "validation_conditions" in data:
        section.validation_conditions = _resolve_refs(
            Condition, data["validation_conditions"], "validation_condition"
        )
    if "deletedBy" in data:
        section.deletedBy = User.objects(uuid=data["deletedBy"]).first()
    if "deleted_by" in data:
        section.deleted_by = User.objects(uuid=data["deleted_by"]).first()


def _apply_question_update(question: Question, body) -> None:
    from app.api.resources_utils import build_action_definitions

    data = body.model_dump(exclude_none=True)
    for key in (
        "type",
        "label",
        "placeholder",
        "description",
        "default_value",
        "help_text",
        "tooltip",
        "add_button",
        "is_repeatable",
        "check_repeat_on",
        "min_repeatable_count",
        "max_repeatable_count",
        "isAction",
        "actionButtonType",
        "actionType",
        "actionLabel",
        "tags",
        "hideButton",
        "actionIcon",
        "status",
        "validation_condition_messages",
    ):
        if key in data:
            setattr(question, key, data[key])
    if "validation_conditions" in data:
        question.validation_conditions = _resolve_refs(
            Condition, data["validation_conditions"], "validation_condition"
        )
    if "visibility_conditions" in data:
        question.visibility_conditions = _resolve_refs(
            Condition, data["visibility_conditions"], "visibility_condition"
        )
    if "repeatable_condition" in data:
        question.repeatable_condition = Condition.objects(
            uuid=data["repeatable_condition"]
        ).first()
    if "choices" in data:
        choices = []
        for choice in body.choices or []:
            choices.append(
                {
                    "uuid": choice.uuid,
                    "label": choice.label,
                    "value": choice.value,
                    "visibility_condition": (
                        Condition.objects(uuid=choice.visibility_condition).first()
                        if choice.visibility_condition
                        else None
                    ),
                }
            )
        question.choices = choices
    if "actions" in data:
        question.actions = build_action_definitions(body.actions or [])
