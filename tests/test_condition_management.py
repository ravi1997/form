import pytest

from app.models.form import Condition
from app.models.condition_management import ConditionAsyncJob
from app.services.condition_management import (
    build_dependency_graph,
    create_condition_version_snapshot,
    create_or_update_preset,
    detect_circular_references,
    diff_condition_versions,
    discover_usage,
    evaluate_condition_async,
    get_condition_versions,
    list_condition_versions,
    record_condition_version,
    rollback_condition_to_version,
    restore_condition_version,
    transition_approval_state,
    validate_safe_delete,
)
from app.services import condition_management_async as async_service
from app.services.condition_evaluator import ConditionEvaluationError


def test_versioning_record_and_restore(app_context):
    c = Condition(
        uuid="ver-1",
        conditionType="comparison",
        targetField="status",
        operator="equals",
        operands=["draft"],
        isActive=True,
    ).save()

    v1 = record_condition_version(c, action="create")
    c.operands = ["approved"]
    c.save()
    record_condition_version(c, action="update")

    restored = restore_condition_version(c.uuid, v1.version)
    assert restored.operands == ["draft"]
    assert len(list_condition_versions(c.uuid)) >= 3


def test_approval_workflow_and_validation(app_context):
    c = Condition(
        uuid="app-1",
        conditionType="comparison",
        targetField="status",
        operator="equals",
        operands=["submitted"],
        isActive=True,
    ).save()
    transition_approval_state(c, "review")
    result = transition_approval_state(c, "published")
    assert result["to_state"] == "published"


def test_preset_upsert_and_usage_discovery(app_context):
    c = Condition(
        uuid="pre-1",
        conditionType="comparison",
        targetField="status",
        operator="equals",
        operands=["submitted"],
        isActive=True,
    ).save()

    preset = create_or_update_preset(
        preset_uuid="preset-1",
        name="Submitted status",
        condition_uuid=c.uuid,
        auto_update=True,
    )
    assert preset.current_version >= 1
    usage = discover_usage(c.uuid)
    assert usage["condition_uuid"] == c.uuid


def test_dependency_graph_and_circular_detection(app_context):
    first = Condition(
        uuid="dep-a",
        conditionType="comparison",
        targetField="status",
        operator="equals",
        operands=["open"],
        isActive=True,
    ).save()
    second = Condition(
        uuid="dep-b",
        conditionType="logical",
        logicalJoinType="AND",
        subConditions=[first],
        isActive=True,
    ).save()

    first.conditionType = "logical"
    first.logicalJoinType = "AND"
    first.targetField = None
    first.operator = None
    first.operands = []
    first.subConditions = [second]
    first.save()

    graph = build_dependency_graph()
    assert "dep-a" in graph and "dep-b" in graph
    cycles = detect_circular_references(graph)
    assert cycles


def test_version_diff_and_rollback_helpers(app_context):
    condition = Condition(
        uuid="ver-helpers",
        conditionType="comparison",
        targetField="score",
        operator="greater_than",
        operands=["60"],
        isActive=True,
    ).save()

    create_condition_version_snapshot(
        condition, actor_user_uuid="tester", reason="initial"
    )
    condition.operands = ["80"]
    condition.save()
    create_condition_version_snapshot(
        condition, actor_user_uuid="tester", reason="tightened"
    )

    versions = get_condition_versions(condition)
    assert len(versions) == 2

    diff = diff_condition_versions(condition, "1", "2")
    assert diff["diff"]

    restored = rollback_condition_to_version(condition, "1", actor_user_uuid="tester")
    assert restored.operands == ["60"]


def test_async_evaluation_and_safe_delete(app_context):
    condition = Condition(
        uuid="async-helper",
        conditionType="comparison",
        targetField="status",
        operator="equals",
        operands=["approved"],
        isActive=True,
    ).save()

    result = evaluate_condition_async(
        condition, {"status": "approved"}, timeout_seconds=1.0
    )
    assert result["status"] in {"success", "timeout", "failed"}

    safe = validate_safe_delete(condition.uuid)
    assert "safe_to_delete" in safe


def test_async_job_processing_updates_mongo_job_state(app_context, monkeypatch):
    condition = Condition(
        uuid="async-success",
        conditionType="comparison",
        targetField="status",
        operator="equals",
        operands=["approved"],
        isActive=True,
    ).save()

    def evaluate(self, condition_obj, *_args, **_kwargs):
        assert condition_obj.uuid == condition.uuid
        return True

    monkeypatch.setattr(async_service.ConditionEvaluator, "evaluate", evaluate)

    job = async_service.enqueue_async_evaluation(
        condition.uuid,
        {"status": "approved"},
        timeout_ms=1000,
        retries=0,
        fallback_result=False,
    )

    payload = async_service.get_async_job_status(job.job_id)
    assert payload["status"] == "success"
    assert payload["result"] is True
    assert payload["task_name"] == "app.celery.tasks.process_condition_async_job"
    assert payload["celery_task_id"]


def test_async_retry_updates_retrying_state(app_context, monkeypatch):
    condition = Condition(
        uuid="async-retry",
        conditionType="comparison",
        targetField="status",
        operator="equals",
        operands=["approved"],
        isActive=True,
    ).save()

    job = ConditionAsyncJob(
        job_id="job-retry",
        condition_uuid=condition.uuid,
        context={"status": "pending"},
        timeout_ms=10,
        retries=2,
        fallback_result=False,
        status="created",
    ).save()

    def raise_timeout(*args, **kwargs):
        raise ConditionEvaluationError("timeout while evaluating")

    monkeypatch.setattr(async_service.ConditionEvaluator, "evaluate", raise_timeout)

    with pytest.raises(ConditionEvaluationError):
        async_service.process_async_job(job.job_id)

    updated = ConditionAsyncJob.objects(job_id=job.job_id).first()
    assert updated.status == "retrying"
    assert updated.retry_count == 1


def test_async_queue_status_reports_counts(app_context):
    ConditionAsyncJob(
        job_id="job-count-created", condition_uuid="cond-a", status="created"
    ).save()
    ConditionAsyncJob(
        job_id="job-count-queued", condition_uuid="cond-a", status="queued"
    ).save()
    ConditionAsyncJob(
        job_id="job-count-running", condition_uuid="cond-b", status="running"
    ).save()
    ConditionAsyncJob(
        job_id="job-count-retrying", condition_uuid="cond-e", status="retrying"
    ).save()
    ConditionAsyncJob(
        job_id="job-count-failed", condition_uuid="cond-c", status="failed"
    ).save()
    ConditionAsyncJob(
        job_id="job-count-timeout", condition_uuid="cond-d", status="timeout"
    ).save()

    status = async_service.get_async_queue_status()

    assert status["queued"] == 1
    assert status["running"] == 1
    assert status["created"] == 1
    assert status["retrying"] == 1
    assert status["failed"] == 1
    assert status["timeout"] == 1
    assert status["worker_available"] in {True, False}
