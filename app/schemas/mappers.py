from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.schemas.choice import ChoiceOutput, ChoiceRef
from app.schemas.condition import ConditionOutput, ConditionRef
from app.schemas.form import FormOutput, FormRef
from app.schemas.form_response import FormResponseOutput, FormResponseRef
from app.schemas.organization import OrganizationOutput, OrganizationRef
from app.schemas.project import ProjectOutput, ProjectRef
from app.schemas.question import QuestionOutput, QuestionRef
from app.schemas.response_item import ResponseItemOutput
from app.schemas.section import SectionOutput, SectionRef
from app.schemas.user import UserOutput, UserRef
from app.schemas.version import VersionOutput, VersionRef


def _get_uuid(value: Any) -> Optional[str]:
    if value is None:
        return None

    uuid = getattr(value, "uuid", None)
    if uuid:
        return str(uuid)

    if isinstance(value, str):
        return value

    identifier = getattr(value, "id", None)
    if identifier is not None:
        return str(identifier)

    return None


def _uuid_list(values: Optional[List[Any]]) -> List[str]:
    out: List[str] = []
    for item in values or []:
        item_uuid = _get_uuid(item)
        if item_uuid:
            out.append(item_uuid)
    return out


def _version_to_ref(version: Any) -> VersionRef:
    return VersionRef(uuid=str(version.uuid))


def to_version_output(version: Any) -> VersionOutput:
    return VersionOutput(
        uuid=str(version.uuid),
        major=version.major,
        minor=version.minor,
        patch=version.patch,
        created=version.created,
        created_by=_get_uuid(version.created_by),
        updated=version.updated,
        updated_by=_get_uuid(version.updated_by),
        status=version.status,
    )


def to_condition_output(condition: Any) -> ConditionOutput:
    return ConditionOutput(
        uuid=str(condition.uuid),
        conditionType=condition.conditionType,
        expression=condition.expression,
        targetField=condition.targetField,
        sourceSectionUuid=condition.sourceSectionUuid,
        operator=condition.operator,
        operands=list(condition.operands or []),
        isNegated=bool(condition.isNegated),
        subConditions=_uuid_list(condition.subConditions),
        logicalJoinType=condition.logicalJoinType,
        isActive=bool(condition.isActive),
        errorMessage=condition.errorMessage,
        description=condition.description,
        priority=int(condition.priority or 0),
        stopEvaluationIfTrue=bool(condition.stopEvaluationIfTrue),
        metadata=dict(condition.metadata or {}),
        created_at=condition.created_at,
        updated_at=condition.updated_at,
        status=condition.status,
    )


def to_condition_ref(condition: Any) -> ConditionRef:
    return ConditionRef(uuid=str(condition.uuid))


def to_choice_output(choice: Any) -> ChoiceOutput:
    return ChoiceOutput(
        uuid=str(choice.uuid),
        label=choice.label,
        value=choice.value,
        visibility_condition=_get_uuid(choice.visibility_condition),
    )


def to_choice_ref(choice: Any) -> ChoiceRef:
    return ChoiceRef(uuid=str(choice.uuid), value=choice.value)


def to_question_output(question: Any) -> QuestionOutput:
    return QuestionOutput(
        uuid=str(question.uuid),
        versions=[to_version_output(v) for v in (question.versions or [])],
        type=question.type,
        label=question.label,
        placeholder=question.placeholder,
        description=question.description,
        default_value=question.default_value,
        help_text=question.help_text,
        tooltip=question.tooltip,
        validation_conditions=_uuid_list(question.validation_conditions),
        validation_condition_messages=dict(question.validation_condition_messages or {}),
        visibility_conditions=_uuid_list(question.visibility_conditions),
        add_button=bool(question.add_button),
        is_repeatable=bool(question.is_repeatable),
        repeatable_condition=_get_uuid(question.repeatable_condition),
        check_repeat_on=question.check_repeat_on,
        min_repeatable_count=question.min_repeatable_count,
        max_repeatable_count=question.max_repeatable_count,
        isAction=bool(question.isAction),
        actionButtonType=question.actionButtonType,
        actionType=question.actionType,
        actionLabel=question.actionLabel,
        tags=list(question.tags or []),
        choices=[to_choice_output(c) for c in (question.choices or [])],
        hideButton=bool(question.hideButton),
        actionIcon=question.actionIcon,
        created_at=question.created_at,
        updated_at=question.updated_at,
        status=question.status,
    )


def to_question_ref(question: Any) -> QuestionRef:
    return QuestionRef(uuid=str(question.uuid), label=question.label, type=question.type)


def to_section_output(section: Any) -> SectionOutput:
    return SectionOutput(
        uuid=str(section.uuid),
        versions=[to_version_output(v) for v in (section.versions or [])],
        questions=dict(section.questions or {}),
        add_button=bool(section.add_button),
        is_repeatable=bool(section.is_repeatable),
        repeatable_condition=_get_uuid(section.repeatable_condition),
        check_repeat_on=section.check_repeat_on,
        min_repeatable_count=section.min_repeatable_count,
        max_repeatable_count=section.max_repeatable_count,
        title=section.title,
        description=section.description,
        isDeleted=bool(section.isDeleted),
        deletedBy=_get_uuid(section.deletedBy),
        deletedAt=section.deletedAt,
        deleted_at=section.deleted_at,
        deleted_by=_get_uuid(section.deleted_by),
        visibility_condition=_get_uuid(section.visibility_condition),
        validation_conditions=_uuid_list(section.validation_conditions),
        validation_condition_messages=dict(section.validation_condition_messages or {}),
        tags=list(section.tags or []),
        icon=section.icon,
        created_at=section.created_at,
        updated_at=section.updated_at,
        status=section.status,
    )


def to_section_ref(section: Any) -> SectionRef:
    return SectionRef(uuid=str(section.uuid), title=section.title)


def to_form_output(form: Any) -> FormOutput:
    return FormOutput(
        uuid=str(form.uuid),
        versions=[to_version_output(v) for v in (form.versions or [])],
        sections=dict(form.sections or {}),
        editors=_uuid_list(form.editors),
        viewers=_uuid_list(form.viewers),
        reviewers=_uuid_list(form.reviewers),
        approvers=_uuid_list(form.approvers),
        submitters=_uuid_list(form.submitters),
        requires_reviewer=bool(form.requires_reviewer),
        requires_approver=bool(form.requires_approver),
        min_reviewers_required=int(form.min_reviewers_required or 0),
        min_approvers_required=int(form.min_approvers_required or 0),
        validation_conditions=_uuid_list(form.validation_conditions),
        validation_condition_messages=dict(form.validation_condition_messages or {}),
        child_sections=_uuid_list(form.child_sections),
        tags=list(form.tags or []),
        icon=form.icon,
        created_at=form.created_at,
        updated_at=form.updated_at,
        status=form.status,
    )


def to_form_ref(form: Any) -> FormRef:
    return FormRef(uuid=str(form.uuid))


def to_project_output(project: Any) -> ProjectOutput:
    return ProjectOutput(
        uuid=str(project.uuid),
        name=project.name,
        versions=[to_version_output(v) for v in (project.versions or [])],
        admins=_uuid_list(project.admins),
        members=_uuid_list(project.members),
        viewers=_uuid_list(project.viewers),
        forms=_uuid_list(project.forms),
        organizations=_uuid_list(project.organizations),
        tags=list(project.tags or []),
        created_at=project.created_at,
        updated_at=project.updated_at,
        status=project.status,
    )


def to_project_ref(project: Any) -> ProjectRef:
    return ProjectRef(uuid=str(project.uuid), name=project.name)


def to_response_item_output(item: Any) -> ResponseItemOutput:
    return ResponseItemOutput(
        question_uuid=item.question_uuid,
        section_uuid=item.section_uuid,
        repeat_index=item.repeat_index,
        value=item.value,
        value_type=item.value_type,
        metadata=dict(item.metadata or {}),
    )


def to_form_response_output(response: Any) -> FormResponseOutput:
    return FormResponseOutput(
        uuid=str(response.uuid),
        form=_get_uuid(response.form),
        form_uuid=response.form_uuid,
        form_version_uuid=response.form_version_uuid,
        project=_get_uuid(response.project),
        project_uuid=response.project_uuid,
        organization=_get_uuid(response.organization),
        organization_uuid=response.organization_uuid,
        submitted_by=_get_uuid(response.submitted_by),
        submitted_by_uuid=response.submitted_by_uuid,
        status=response.status,
        responses=[to_response_item_output(i) for i in (response.responses or [])],
        response_map=dict(response.response_map or {}),
        score=response.score,
        validation_errors=dict(response.validation_errors or {}),
        submitted_at=response.submitted_at,
        reviewed_at=response.reviewed_at,
        reviewed_by=_uuid_list(response.reviewed_by),
        approved_at=response.approved_at,
        approved_by=_uuid_list(response.approved_by),
        created_at=response.created_at,
        updated_at=response.updated_at,
        deleted_at=response.deleted_at,
        deleted_by=_get_uuid(response.deleted_by),
        metadata=dict(response.metadata or {}),
    )


def to_form_response_ref(response: Any) -> FormResponseRef:
    return FormResponseRef(uuid=str(response.uuid), status=response.status)


def to_organization_output(organization: Any) -> OrganizationOutput:
    return OrganizationOutput(
        uuid=str(organization.uuid),
        name=organization.name,
        admins=_uuid_list(organization.admins),
        status=organization.status,
        created_at=organization.created_at,
        updated_at=organization.updated_at,
        deleted_at=organization.deleted_at,
        deleted_by=_get_uuid(organization.deleted_by),
    )


def to_organization_ref(organization: Any) -> OrganizationRef:
    return OrganizationRef(uuid=str(organization.uuid), name=organization.name)


def to_user_output(user: Any) -> UserOutput:
    return UserOutput(
        uuid=str(user.uuid),
        name=user.name,
        designation=user.designation,
        email=user.email,
        phone=user.phone,
        organizations=_uuid_list(user.organizations),
        roles=dict(user.roles or {}),
        status=user.status,
        auth_provider=user.auth_provider,
        is_email_verified=bool(user.is_email_verified),
        is_phone_verified=bool(user.is_phone_verified),
        is_organisation_admin=bool(user.is_organisation_admin),
        is_super_admin=bool(user.is_super_admin),
        is_mfa_enabled=bool(user.is_mfa_enabled),
        created_at=user.created_at,
        updated_at=user.updated_at,
        verified_at=user.verified_at,
        verified_by=user.verified_by,
        deleted_at=user.deleted_at,
        deleted_by=user.deleted_by,
        last_login_at=user.last_login_at,
        last_logout_at=user.last_logout_at,
        last_password_change_at=user.last_password_change_at,
    )


def to_user_ref(user: Any) -> UserRef:
    return UserRef(uuid=str(user.uuid), name=user.name, email=user.email)


def to_json_ready(schema_obj: Any) -> Dict[str, Any]:
    """Convert any schema model to a JSON-serializable dict for responses."""
    return schema_obj.model_dump(mode="json")
