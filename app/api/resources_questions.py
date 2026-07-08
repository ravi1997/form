"""Question CRUD and version endpoints."""

from __future__ import annotations

from mongoengine.errors import NotUniqueError, ValidationError

from app.models.form import Choice, Condition, Question
from app.schemas.mappers import to_json_ready, to_question_output, to_version_output
from app.schemas.question import (
    QuestionCreateInput,
    QuestionOutput,
    QuestionUpdateInput,
)
from app.schemas.version import VersionCreateInput, VersionOutput, VersionUpdateInput
from app.api.resources_schemas import (
    ErrorResponse,
    ListQuery,
    MessageResponse,
    QuestionListResponse,
    QuestionPath,
    QuestionVersionPath,
    SectionPath,
    VersionLinkQuery,
)
from app.api.resources_support import _error, resources_api, resources_tag, version_tag
from app.api.resources_context import (
    _append_version,
    _apply_question_update,
    _get_form_for_project,
    _get_project_or_error,
    _get_question_for_section,
    _get_section_for_form,
    _resolve_refs,
    _resolve_version_key,
    _section_question_uuids,
    _update_version,
    _version_from_create,
)
from app.api.resources_utils import (
    build_action_definitions as _build_action_definitions,
    paginate_queryset as _paginate_queryset,
)


@resources_api.post(
    "/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions",
    tags=[resources_tag],
    responses={201: QuestionOutput, 400: ErrorResponse, 404: ErrorResponse},
)
def create_question(
    path: SectionPath, query: VersionLinkQuery, body: QuestionCreateInput
):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err
    section, section_err = _get_section_for_form(form, path.section_uuid)
    if section_err:
        return section_err
    try:
        version_key = _resolve_version_key(
            section.versions or [], section.questions or {}, query.version_uuid
        )
        choices = []
        for choice in body.choices:
            choices.append(
                Choice(
                    uuid=choice.uuid,
                    label=choice.label,
                    value=choice.value,
                    visibility_condition=(
                        Condition.objects(uuid=choice.visibility_condition).first()
                        if choice.visibility_condition
                        else None
                    ),
                )
            )
        question = Question(
            uuid=body.uuid,
            versions=[_version_from_create(v) for v in body.versions],
            type=body.type,
            label=body.label,
            placeholder=body.placeholder,
            description=body.description,
            default_value=body.default_value,
            help_text=body.help_text,
            tooltip=body.tooltip,
            validation_conditions=_resolve_refs(
                Condition, body.validation_conditions, "validation_condition"
            ),
            validation_condition_messages=body.validation_condition_messages,
            visibility_conditions=_resolve_refs(
                Condition, body.visibility_conditions, "visibility_condition"
            ),
            add_button=body.add_button,
            is_repeatable=body.is_repeatable,
            repeatable_condition=(
                Condition.objects(uuid=body.repeatable_condition).first()
                if body.repeatable_condition
                else None
            ),
            check_repeat_on=body.check_repeat_on,
            min_repeatable_count=body.min_repeatable_count,
            max_repeatable_count=body.max_repeatable_count,
            isAction=body.isAction,
            actionButtonType=body.actionButtonType,
            actionType=body.actionType,
            actionLabel=body.actionLabel,
            actions=_build_action_definitions(body.actions or []),
            tags=body.tags,
            choices=choices,
            hideButton=body.hideButton,
            actionIcon=body.actionIcon,
            status=body.status,
        ).save()
        section.questions = dict(section.questions or {})
        section.questions[version_key] = list(section.questions.get(version_key, []))
        if question.uuid not in section.questions[version_key]:
            section.questions[version_key].append(question.uuid)
        section.save()
    except (ValidationError, ValueError, NotUniqueError) as exc:
        return _error(str(exc))
    return to_json_ready(to_question_output(question)), 201


@resources_api.get(
    "/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions",
    tags=[resources_tag],
    responses={200: QuestionListResponse, 404: ErrorResponse},
)
def list_questions(path: SectionPath, query: ListQuery):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err
    section, section_err = _get_section_for_form(form, path.section_uuid)
    if section_err:
        return section_err
    uuids = list(_section_question_uuids(section))
    qs = Question.objects(uuid__in=uuids)
    if query.status:
        qs = qs(status=query.status)
    try:
        items, page, page_size, total_items, total_pages, next_cursor = (
            _paginate_queryset(qs, query)
        )
    except ValueError as exc:
        return _error(str(exc), 400)
    return to_json_ready(
        QuestionListResponse(
            items=[to_question_output(item) for item in items],
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
            next_cursor=next_cursor,
        )
    )


@resources_api.get(
    "/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions/<question_uuid>",
    tags=[resources_tag],
    responses={200: QuestionOutput, 404: ErrorResponse},
)
def get_question(path: QuestionPath):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err
    section, section_err = _get_section_for_form(form, path.section_uuid)
    if section_err:
        return section_err
    question, question_err = _get_question_for_section(section, path.question_uuid)
    if question_err:
        return question_err
    return to_json_ready(to_question_output(question))


@resources_api.patch(
    "/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions/<question_uuid>",
    tags=[resources_tag],
    responses={200: QuestionOutput, 400: ErrorResponse, 404: ErrorResponse},
)
def update_question(path: QuestionPath, body: QuestionUpdateInput):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err
    section, section_err = _get_section_for_form(form, path.section_uuid)
    if section_err:
        return section_err
    question, question_err = _get_question_for_section(section, path.question_uuid)
    if question_err:
        return question_err
    try:
        _apply_question_update(question, body)
        question.save()
    except (ValidationError, ValueError, NotUniqueError) as exc:
        return _error(str(exc))
    return to_json_ready(to_question_output(question))


@resources_api.delete(
    "/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions/<question_uuid>",
    tags=[resources_tag],
    responses={200: MessageResponse, 404: ErrorResponse},
)
def delete_question(path: QuestionPath):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err
    section, section_err = _get_section_for_form(form, path.section_uuid)
    if section_err:
        return section_err
    question, question_err = _get_question_for_section(section, path.question_uuid)
    if question_err:
        return question_err
    question.status = "deleted"
    question.save()
    section.questions = dict(section.questions or {})
    for key, values in section.questions.items():
        section.questions[key] = [v for v in (values or []) if v != question.uuid]
    section.save()
    return to_json_ready(MessageResponse(message="question_deleted"))


@resources_api.post(
    "/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions/<question_uuid>/versions",
    tags=[version_tag],
    responses={201: VersionOutput, 400: ErrorResponse, 404: ErrorResponse},
)
def create_question_version(path: QuestionPath, body: VersionCreateInput):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err
    section, section_err = _get_section_for_form(form, path.section_uuid)
    if section_err:
        return section_err
    question, question_err = _get_question_for_section(section, path.question_uuid)
    if question_err:
        return question_err
    try:
        _append_version(question, body)
        question.save()
    except (ValidationError, ValueError) as exc:
        return _error(str(exc))
    return to_json_ready(to_version_output(question.versions[-1])), 201


@resources_api.patch(
    "/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions/<question_uuid>/versions/<version_uuid>",
    tags=[version_tag],
    responses={200: VersionOutput, 400: ErrorResponse, 404: ErrorResponse},
)
def update_question_version(path: QuestionVersionPath, body: VersionUpdateInput):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err
    section, section_err = _get_section_for_form(form, path.section_uuid)
    if section_err:
        return section_err
    question, question_err = _get_question_for_section(section, path.question_uuid)
    if question_err:
        return question_err
    try:
        updated = _update_version(question, path.version_uuid, body)
        question.save()
    except (ValidationError, ValueError) as exc:
        if str(exc) == "Version not found":
            return _error(str(exc), 404)
        return _error(str(exc))
    return to_json_ready(to_version_output(updated))
