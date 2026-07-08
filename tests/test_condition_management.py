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


def test_async_timeout_retry_requeues_job(app_context, monkeypatch):
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
        retries=1,
        fallback_result=False,
        status="queued",
    ).save()

    class FakeQueue:
        def __init__(self):
            self.calls = []

        def enqueue(self, func, *args, **kwargs):
            self.calls.append((func, args, kwargs))

    fake_queue = FakeQueue()

    def raise_timeout(*args, **kwargs):
        raise ConditionEvaluationError("timeout while evaluating")

    monkeypatch.setattr(async_service.ConditionEvaluator, "evaluate", raise_timeout)

    async_service._run_async_job(job.job_id, queue=fake_queue)

    assert fake_queue.calls
    assert fake_queue.calls[0][1][0] == job.job_id
    assert fake_queue.calls[0][1][1] == 1
    assert fake_queue.calls[0][1][2] is fake_queue


def test_recover_pending_async_jobs_requeues_queued_and_running_jobs(app_context):
    queued = ConditionAsyncJob(
        job_id="job-queued",
        condition_uuid="cond-q",
        context={"status": "ok"},
        status="queued",
    ).save()
    running = ConditionAsyncJob(
        job_id="job-running",
        condition_uuid="cond-r",
        context={"status": "ok"},
        status="running",
    ).save()

    class FakeQueue:
        def __init__(self):
            self.calls = []

        def enqueue(self, func, *args, **kwargs):
            self.calls.append((func, args, kwargs))

    fake_queue = FakeQueue()
    stats = async_service.recover_pending_async_jobs(queue=fake_queue)

    assert stats["requeued"] == 2
    assert stats["running_reset"] == 1
    assert len(fake_queue.calls) == 2
    assert ConditionAsyncJob.objects(job_id=queued.job_id).first().status == "queued"
    assert ConditionAsyncJob.objects(job_id=running.job_id).first().status == "queued"


def test_async_queue_status_reports_counts(app_context):
    ConditionAsyncJob(
        job_id="job-count-queued", condition_uuid="cond-a", status="queued"
    ).save()
    ConditionAsyncJob(
        job_id="job-count-running", condition_uuid="cond-b", status="running"
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
    assert status["failed"] == 1
    assert status["timeout"] == 1
    assert status["oldest_queued_at"] is not None
    assert status["oldest_running_at"] is not None
