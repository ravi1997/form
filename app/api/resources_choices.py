"""Choice CRUD endpoints."""
from __future__ import annotations

from mongoengine.errors import NotUniqueError, ValidationError

from app.models.form import Choice, Condition
from app.schemas.choice import ChoiceCreateInput, ChoiceOutput, ChoiceUpdateInput
from app.schemas.mappers import to_json_ready, to_choice_output
from app.api.resources_schemas import (
    ChoiceListResponse, ChoicePath, ErrorResponse, ListQuery, MessageResponse, QuestionPath,
)
from app.api.resources_support import _error, resources_api, resources_tag
from app.api.resources_context import (
    _get_choice_for_question,
    _get_form_for_project,
    _get_project_or_error,
    _get_question_for_section,
    _get_section_for_form,
)
from app.api.resources_utils import (
    decode_index_cursor as _decode_index_cursor,
    encode_index_cursor as _encode_index_cursor,
)


@resources_api.post(
    "/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions/<question_uuid>/choices",
    tags=[resources_tag],
    responses={201: ChoiceOutput, 400: ErrorResponse, 404: ErrorResponse},
)
def create_choice(path: QuestionPath, body: ChoiceCreateInput):
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
    if any(str(choice.uuid) == body.uuid for choice in (question.choices or [])):
        return _error("Choice uuid already exists")
    choice = Choice(
        uuid=body.uuid,
        label=body.label,
        value=body.value,
        visibility_condition=(
            Condition.objects(uuid=body.visibility_condition).first()
            if body.visibility_condition else None
        ),
    )
    question.choices = list(question.choices or [])
    question.choices.append(choice)
    try:
        question.save()
    except (ValidationError, ValueError, NotUniqueError) as exc:
        return _error(str(exc))
    return to_json_ready(to_choice_output(choice)), 201


@resources_api.get(
    "/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions/<question_uuid>/choices",
    tags=[resources_tag],
    responses={200: ChoiceListResponse, 404: ErrorResponse},
)
def list_choices(path: QuestionPath, query: ListQuery):
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
    all_items = list(question.choices or [])
    total_items = len(all_items)
    next_cursor = None
    if query.cursor:
        try:
            start = _decode_index_cursor(query.cursor)
        except ValueError as exc:
            return _error(str(exc), 400)
        page = max(query.page, 1)
        page_size = max(query.page_size, 1)
        items = all_items[start: start + page_size]
        if start + page_size < total_items:
            next_cursor = _encode_index_cursor(start + page_size)
    elif query.offset is not None or query.limit is not None:
        page_size = query.limit or 50
        offset = query.offset or 0
        page = (offset // max(page_size, 1)) + 1
        items = all_items[offset: offset + page_size]
    else:
        page = max(query.page, 1)
        page_size = max(query.page_size, 1)
        start = (page - 1) * page_size
        items = all_items[start: start + page_size]
        if start + page_size < total_items:
            next_cursor = _encode_index_cursor(start + page_size)
    total_pages = (total_items + page_size - 1) // page_size if total_items else 0
    return to_json_ready(ChoiceListResponse(
        items=[to_choice_output(choice) for choice in items],
        page=page, page_size=page_size, total_items=total_items,
        total_pages=total_pages, next_cursor=next_cursor,
    ))


@resources_api.get(
    "/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions/<question_uuid>/choices/<choice_uuid>",
    tags=[resources_tag],
    responses={200: ChoiceOutput, 404: ErrorResponse},
)
def get_choice(path: ChoicePath):
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
    choice, _, choice_err = _get_choice_for_question(question, path.choice_uuid)
    if choice_err:
        return choice_err
    return to_json_ready(to_choice_output(choice))


@resources_api.patch(
    "/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions/<question_uuid>/choices/<choice_uuid>",
    tags=[resources_tag],
    responses={200: ChoiceOutput, 400: ErrorResponse, 404: ErrorResponse},
)
def update_choice(path: ChoicePath, body: ChoiceUpdateInput):
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
    choice, _, choice_err = _get_choice_for_question(question, path.choice_uuid)
    if choice_err:
        return choice_err
    if body.label is not None:
        choice.label = body.label
    if body.value is not None:
        choice.value = body.value
    if body.visibility_condition is not None:
        choice.visibility_condition = Condition.objects(uuid=body.visibility_condition).first()
    try:
        question.save()
    except (ValidationError, ValueError, NotUniqueError) as exc:
        return _error(str(exc))
    return to_json_ready(to_choice_output(choice))


@resources_api.delete(
    "/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions/<question_uuid>/choices/<choice_uuid>",
    tags=[resources_tag],
    responses={200: MessageResponse, 404: ErrorResponse},
)
def delete_choice(path: ChoicePath):
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
    _, index, choice_err = _get_choice_for_question(question, path.choice_uuid)
    if choice_err:
        return choice_err
    question.choices.pop(index)
    question.save()
    return to_json_ready(MessageResponse(message="choice_deleted"))
