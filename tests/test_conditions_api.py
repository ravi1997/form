import time

from app.models.form import Condition


def test_condition_metadata_and_operator_metadata(client):
    res = client.get("/api/v1/conditions/metadata")
    assert res.status_code == 200
    payload = res.get_json()
    assert "comparison" in payload["condition_types"]

    res2 = client.get("/api/v1/conditions/operators/metadata")
    assert res2.status_code == 200
    assert "between" in res2.get_json()


def test_condition_test_and_batch_and_cache_metrics(client, app_context):
    c = Condition(
        uuid="api-c1",
        conditionType="comparison",
        targetField="score",
        operator="greater_than",
        operands=["50"],
        isActive=True,
    ).save()

    r1 = client.post(
        "/api/v1/conditions/test",
        json={
            "condition_uuid": c.uuid,
            "context": {"score": 70},
            "enable_tracing": True,
        },
    )
    assert r1.status_code == 200
    assert r1.get_json()["matched"] is True

    r2 = client.post(
        "/api/v1/conditions/test/batch",
        json={
            "tests": [
                {"condition_uuid": c.uuid, "context": {"score": 20}},
                {"condition_uuid": c.uuid, "context": {"score": 90}},
            ]
        },
    )
    assert r2.status_code == 200
    assert r2.get_json()["total"] == 2

    metrics = client.get("/api/v1/conditions/cache/metrics")
    assert metrics.status_code == 200
    assert "regex_cache" in metrics.get_json()


def test_presets_approval_versioning_bulk_and_monitoring(client, app_context):
    c = Condition(
        uuid="api-c2",
        conditionType="comparison",
        targetField="status",
        operator="equals",
        operands=["draft"],
        isActive=True,
    ).save()

    preset = client.post(
        "/api/v1/conditions/presets",
        json={"uuid": "preset-api", "name": "Draft", "condition_uuid": c.uuid},
    )
    assert preset.status_code == 200

    approve1 = client.post(
        f"/api/v1/conditions/{c.uuid}/approval/transition",
        json={"target_state": "review"},
    )
    assert approve1.status_code == 200
    approve2 = client.post(
        f"/api/v1/conditions/{c.uuid}/approval/transition",
        json={"target_state": "published"},
    )
    assert approve2.status_code == 200

    record = client.post(
        f"/api/v1/conditions/{c.uuid}/versions/record", json={"action": "update"}
    )
    assert record.status_code == 200

    bulk = client.post(
        "/api/v1/conditions/bulk/create",
        json={
            "items": [
                {
                    "uuid": "bulk-c1",
                    "conditionType": "comparison",
                    "targetField": "score",
                    "operator": "greater_than",
                    "operands": ["10"],
                    "isActive": True,
                }
            ]
        },
    )
    assert bulk.status_code == 200
    assert "bulk-c1" in bulk.get_json()["created"]

    graph = client.get("/api/v1/conditions/monitoring/graph")
    assert graph.status_code == 200


def test_async_evaluation_endpoint(client, app_context):
    c = Condition(
        uuid="api-async-1",
        conditionType="comparison",
        targetField="score",
        operator="greater_than",
        operands=["10"],
        isActive=True,
    ).save()

    start = client.post(
        "/api/v1/conditions/async/evaluate",
        json={"condition_uuid": c.uuid, "context": {"score": 99}, "timeout_ms": 5000},
    )
    assert start.status_code == 200
    job_id = start.get_json()["job_id"]

    status_payload = None
    for _ in range(30):
        time.sleep(0.05)
        status = client.get(f"/api/v1/conditions/async/{job_id}")
        assert status.status_code == 200
        status_payload = status.get_json()
        if status_payload["status"] in {"success", "failed", "timeout"}:
            break

    assert status_payload is not None
    assert status_payload["status"] in {"success", "failed", "timeout"}
