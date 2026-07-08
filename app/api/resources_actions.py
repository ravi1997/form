"""Action trigger and execution list endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4

from flask import g
from mongoengine.errors import NotUniqueError, ValidationError

from app.models.form import ActionExecution, FormResponse
from app.schemas.action import (
    ActionExecutionListResponse,
    ActionTriggerRequest,
    ActionTriggerResponse,
)
from app.schemas.mappers import to_json_ready
from app.services.condition_evaluator import ConditionEvaluationError, ConditionEvaluator
from app.api.resources_schemas import (
    ErrorResponse, ListQuery, QuestionActionPath, ResponseActionExecutionPath,
)
from app.api.resources_support import _error, resources_api, resources_tag
from app.api.resources_context import (
    _get_form_for_project,
    _get_project_or_error,
    _get_question_for_section,
    _get_section_for_form,
)
from app.api.resources_utils import (
    paginate_queryset as _paginate_queryset,
    resolve_action_definition as _resolve_action_definition,
    to_action_execution_output as _to_action_execution_output,
)


@resources_api.post(
    "/projects/<project_uuid>/forms/<form_uuid>/sections/<section_uuid>/questions/<question_uuid>/actions/<action_id>/trigger",
    tags=[resources_tag],
    responses={
        200: ActionTriggerResponse,
        400: ErrorResponse,
        404: ErrorResponse,
        409: ErrorResponse,
    },
)
def trigger_question_action(path: QuestionActionPath, body: ActionTriggerRequest):
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

    action = _resolve_action_definition(question, path.action_id)
    if not action:
        return _error("Action not found", 404)

    response = None
    if body.response_uuid:
        response = FormResponse.objects(uuid=body.response_uuid, form_uuid=form.uuid).first()
        if not response:
            return _error("Form response not found", 404)

    if body.idempotency_key:
        existing = ActionExecution.objects(
            question_uuid=question.uuid,
            action_id=path.action_id,
            response_uuid=body.response_uuid,
            idempotency_key=body.idempotency_key,
        ).first()
        if existing:
            return to_json_ready(ActionTriggerResponse(
                execution=_to_action_execution_output(existing),
                frontend_steps=existing.frontend_steps or [],
                idempotent=True,
            ))

    if action.confirmation_message and not body.confirmed:
        return _error("Action confirmation required", 409)

    eval_context: Dict[str, Any] = dict(body.response_snapshot or {})
    if response:
        eval_context.setdefault("status", response.status)
        eval_context.update(dict(response.metadata or {}))

    evaluator = ConditionEvaluator(context=eval_context)
    if action.visibility_condition and not evaluator.evaluate(action.visibility_condition):
        return _error("Action is not visible in current context", 409)
    if action.enabled_condition and not evaluator.evaluate(action.enabled_condition):
        return _error("Action is disabled in current context", 409)

    step_results: List[Dict[str, Any]] = []
    frontend_steps: List[Dict[str, Any]] = []
    execution_status = "success"
    execution_error = None

    for step in action.steps or []:
        step_payload = {
            "id": step.id,
            "target": step.target,
            "type": step.type,
            "config": dict(step.config or {}),
            "on_error": step.on_error,
        }
        now = datetime.now(timezone.utc)

        if step.target == "frontend":
            frontend_steps.append(step_payload)
            step_results.append({
                "step_id": step.id, "target": step.target, "type": step.type,
                "status": "success", "output": {"deferred_to_frontend": True},
                "error": None, "executed_at": now,
            })
            continue

        try:
            output: Dict[str, Any] = {}
            if step.type == "response.status.set":
                if not response:
                    raise ValueError("response_uuid is required for response.status.set")
                status_value = step.config.get("status")
                if not status_value:
                    raise ValueError("response.status.set requires config.status")
                response.status = status_value
                response.save()
                output = {"status": response.status}
            elif step.type == "response.metadata.merge":
                if not response:
                    raise ValueError("response_uuid is required for response.metadata.merge")
                patch = step.config.get("patch", {})
                merged = dict(response.metadata or {})
                merged.update(dict(patch))
                response.metadata = merged
                response.save()
                output = {"metadata": merged}
            else:
                output = {"skipped": True}
            step_results.append({
                "step_id": step.id, "target": step.target, "type": step.type,
                "status": "success", "output": output, "error": None, "executed_at": now,
            })
        except (ConditionEvaluationError, ValidationError, NotUniqueError, ValueError, KeyError, TypeError) as exc:
            execution_status = "failed"
            execution_error = str(exc)
            step_results.append({
                "step_id": step.id, "target": step.target, "type": step.type,
                "status": "failed", "output": {}, "error": str(exc), "executed_at": now,
            })
            if step.on_error != "continue":
                break
            execution_status = "partial"

    execution = ActionExecution(
        uuid=str(uuid4()),
        project_uuid=project.uuid,
        form_uuid=form.uuid,
        section_uuid=section.uuid,
        question_uuid=question.uuid,
        action_id=path.action_id,
        response_uuid=body.response_uuid,
        actor_user_uuid=getattr(g, "user_id", None) or "anonymous",
        idempotency_key=body.idempotency_key,
        status=execution_status,
        frontend_steps=frontend_steps,
        step_results=step_results,
        request_context=body.context or {},
        client_state=body.client_state or {},
        output={},
        error=execution_error,
        completed_at=datetime.now(timezone.utc),
        request_id=getattr(g, "request_id", None),
    )
    execution.save()

    return to_json_ready(ActionTriggerResponse(
        execution=_to_action_execution_output(execution),
        frontend_steps=frontend_steps,
        idempotent=False,
    ))


@resources_api.get(
    "/projects/<project_uuid>/forms/<form_uuid>/responses/<response_uuid>/action-executions",
    tags=[resources_tag],
    responses={200: ActionExecutionListResponse, 404: ErrorResponse},
)
def list_action_executions(path: ResponseActionExecutionPath, query: ListQuery):
    project, project_err = _get_project_or_error(path.project_uuid)
    if project_err:
        return project_err
    form, form_err = _get_form_for_project(project, path.form_uuid)
    if form_err:
        return form_err
    response = FormResponse.objects(uuid=path.response_uuid, form_uuid=form.uuid).first()
    if not response:
        return _error("Form response not found", 404)
    executions = ActionExecution.objects(
        project_uuid=project.uuid, form_uuid=form.uuid, response_uuid=response.uuid,
    )
    items, page, page_size, total_items, total_pages, next_cursor = _paginate_queryset(executions, query)
    return to_json_ready(ActionExecutionListResponse(
        items=[_to_action_execution_output(item) for item in items],
        page=page, page_size=page_size, total_items=total_items,
        total_pages=total_pages, next_cursor=next_cursor,
    ))
