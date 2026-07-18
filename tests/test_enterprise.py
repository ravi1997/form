import uuid
from app.models.enterprise import (
    WebhookDeliveryLog,
    LogicSubGraph,
    TenantResidencyConfig,
    SignedAuditLog,
    ActiveSessionPresence,
)
from app.models.form import ResponseAuditLog, Form


def test_simulate_form(client):
    schema = {
        "sections": [
            {"uuid": "sec-1", "title": "General Info", "conditional_rules": []},
            {
                "uuid": "sec-2",
                "title": "Extended Details",
                "conditional_rules": [
                    {"field": "has_hazards", "operator": "equals", "value": "yes"}
                ],
            },
        ]
    }
    res = client.post(
        "/api/v1/enterprise/forms/simulate",
        json={
            "form_schema": schema,
            "user_state": {"has_hazards": "yes"},
            "role": "submitter",
        },
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["evaluated_sections"][0]["visible"] is True
    assert data["evaluated_sections"][1]["visible"] is True


def test_logic_dry_run(client):
    graph = {
        "nodes": [
            {"id": "n1", "type": "input", "config": {"input_key": "val1"}},
            {"id": "n2", "type": "input", "config": {"input_key": "val2"}},
            {"id": "n3", "type": "math", "config": {"operator": "add"}},
        ],
        "connections": [
            {
                "source_node": "n1",
                "source_port": "value",
                "target_node": "n3",
                "target_port": "a",
            },
            {
                "source_node": "n2",
                "source_port": "value",
                "target_node": "n3",
                "target_port": "b",
            },
        ],
    }

    res = client.post(
        "/api/v1/enterprise/logic/dry-run",
        json={
            "graph": graph,
            "inputs": {"val1": 40, "val2": 2},
            "compare_with_previous": {"n3": {"value": 41}},
        },
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "completed"
    assert data["results"]["n3"]["value"] == 42
    assert data["comparison"] is not None


def test_webhook_logs_and_retry(client, app_context):
    # Clear logs
    WebhookDeliveryLog.objects.delete()

    log_uuid = str(uuid.uuid4())
    log = WebhookDeliveryLog(
        uuid=log_uuid,
        webhook_config_uuid="cfg-1",
        form_uuid="form-1",
        event_type="submit",
        url="http://test.local",
        status="failed",
        error_message="Timeout",
    ).save()

    res = client.get("/api/v1/enterprise/webhooks/logs?form_uuid=form-1")
    assert res.status_code == 200
    logs = res.get_json()["items"]
    assert len(logs) == 1

    res_retry = client.post(f"/api/v1/enterprise/webhooks/logs/{log_uuid}/retry")
    assert res_retry.status_code == 200
    log.reload()
    assert log.status == "retrying"


def test_apply_acl(client):
    schema = {
        "sections": [
            {
                "uuid": "sec-1",
                "title": "Section 1",
                "acl": {"hidden_for": ["guest"], "read_only_for": ["submitter"]},
                "questions": [
                    {
                        "uuid": "q-1",
                        "type": "text",
                        "label": "Name",
                        "acl": {"hidden_for": ["restricted_role"]},
                    }
                ],
            }
        ]
    }
    res_sub = client.post(
        "/api/v1/enterprise/forms/apply-acl",
        json={"form_schema": schema, "role": "submitter"},
    )
    assert res_sub.status_code == 200
    sections = res_sub.get_json()["sections"]
    assert sections[0]["read_only"] is True


def test_audit_logs_searching(client, app_context):
    # Clear logs
    ResponseAuditLog.objects.delete()

    audit_uuid = str(uuid.uuid4())
    ResponseAuditLog(
        uuid=audit_uuid,
        response_uuid="resp-99",
        actor_user_uuid="user-1",
        action="update",
        changes={"score": [10, 20]},
    ).save()

    res = client.get("/api/v1/enterprise/audit-logs?response_uuid=resp-99")
    assert res.status_code == 200
    logs = res.get_json()["items"]
    assert len(logs) == 1


def test_data_masking(client):
    res_data = {"q-ssn": "123-456-7890"}
    config = [{"field_uuid": "q-ssn", "piiClass": "phi"}]

    res_guest = client.post(
        "/api/v1/enterprise/responses/mask",
        json={"response_data": res_data, "fields_config": config, "role": "guest"},
    )
    assert res_guest.status_code == 200
    data = res_guest.get_json()["anonymized_data"]
    assert "*" in data["q-ssn"]


def test_offline_sync(client, app_context):
    Form.objects.delete()
    Form(uuid="f-99").save()

    # Test valid sync token
    res = client.post(
        "/api/v1/enterprise/sync/offline",
        json={
            "submissions": [
                {"uuid": "sub-1", "form_uuid": "f-99", "answers": {"q1": "val"}}
            ],
            "client_timestamp": "2026-07-18T18:00:00Z",
            "encryption_verification_token": "valid_token_sign",
        },
    )
    assert res.status_code == 200

    # Test invalid sync token
    res_invalid = client.post(
        "/api/v1/enterprise/sync/offline",
        json={
            "submissions": [],
            "client_timestamp": "2026-07-18T18:00:00Z",
            "encryption_verification_token": "hacked_token",
        },
    )
    assert res_invalid.status_code == 400


def test_residency_verification(client, app_context):
    TenantResidencyConfig.objects.delete()
    res = client.post(
        "/api/v1/enterprise/residency/verify",
        json={"organization_id": "org-99", "target_region": "eu-central"},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["residency_routing_valid"] is True


def test_sub_graph_management(client, app_context):
    LogicSubGraph.objects.delete()
    payload = {
        "name": "Tax Calculator",
        "organization_id": "org-1",
        "input_ports": [],
        "output_ports": [],
        "nodes": [],
        "connections": [],
    }
    res_create = client.post("/api/v1/enterprise/sub-graphs", json=payload)
    assert res_create.status_code == 201


# --- Hardened Audit and Security Tests ---


def test_signed_audit_chain_tamper_detection(client, app_context):
    # Clear signed logs from previous runs
    SignedAuditLog.objects.delete()

    # Create signed logs
    client.post(
        "/api/v1/enterprise/audit-logs/signed",
        json={
            "response_uuid": "resp-1",
            "actor_user_uuid": "user-1",
            "action": "create",
            "changes": {"data": "initial"},
        },
    )
    client.post(
        "/api/v1/enterprise/audit-logs/signed",
        json={
            "response_uuid": "resp-1",
            "actor_user_uuid": "user-1",
            "action": "update",
            "changes": {"data": "updated"},
        },
    )

    # Verify chain
    res = client.post("/api/v1/enterprise/audit-logs/verify")
    assert res.status_code == 200
    assert res.get_json()["tamper_detected"] is False

    # Simulate database tampering by modifying an entry directly
    last_log = SignedAuditLog.objects.order_by("-timestamp").first()
    last_log.changes = {"data": "hacked"}
    last_log.save()

    res_tampered = client.post("/api/v1/enterprise/audit-logs/verify")
    assert res_tampered.status_code == 200
    assert res_tampered.get_json()["tamper_detected"] is True
    assert last_log.uuid in res_tampered.get_json()["mismatched_uuids"]


def test_offline_key_negotiation(client):
    res = client.post(
        "/api/v1/enterprise/sync/negotiate-key",
        json={"client_device_id": "phone-1", "workspace_uuid": "work-1"},
    )
    assert res.status_code == 200
    assert res.get_json()["sync_key"] == "valid_token_sign"


def test_collaboration_presence_locks(client, app_context):
    # Clear active sessions
    ActiveSessionPresence.objects.delete()

    # Report presence
    res = client.post(
        "/api/v1/enterprise/collaboration/presence",
        json={
            "workspace_uuid": "w-1",
            "resource_uuid": "form-1",
            "user_uuid": "user-A",
            "user_name": "Alice",
            "active_section": "sec-2",
        },
    )
    assert res.status_code == 200
    assert len(res.get_json()["active_users"]) == 1

    # Acquire lock
    res_lock = client.post(
        "/api/v1/enterprise/collaboration/lock",
        json={
            "resource_uuid": "form-1",
            "user_uuid": "user-A",
            "section_uuid": "sec-2",
            "lock": True,
        },
    )
    assert res_lock.status_code == 200

    # Test lock conflict (User-B attempts to lock the same section)
    res_conflict = client.post(
        "/api/v1/enterprise/collaboration/lock",
        json={
            "resource_uuid": "form-1",
            "user_uuid": "user-B",
            "section_uuid": "sec-2",
            "lock": True,
        },
    )
    assert res_conflict.status_code == 409


def test_governance_retention(client, app_context):
    res = client.post(
        "/api/v1/enterprise/governance/retention",
        json={
            "organization_id": "org-1",
            "retention_days": 30,
            "archival_target": "delete",
            "consent_tracking_required": True,
        },
    )
    assert res.status_code == 200

    res_purge = client.post("/api/v1/enterprise/governance/purge")
    assert res_purge.status_code == 200


def test_webhook_policies_and_analytics(client, app_context):
    res = client.post(
        "/api/v1/enterprise/webhooks/policies",
        json={
            "webhook_config_uuid": "cfg-99",
            "retry_policy": "exponential_backoff",
            "timeout_seconds": 15,
            "failure_threshold_pct": 20,
            "alert_emails": ["admin@test.local"],
        },
    )
    assert res.status_code == 200

    res_analytics = client.get("/api/v1/enterprise/webhooks/analytics")
    assert res_analytics.status_code == 200
    assert res_analytics.get_json()["health_score"] == 99


def test_platform_operations_dashboard(client):
    res = client.get("/api/v1/enterprise/operations/dashboard")
    assert res.status_code == 200
    data = res.get_json()
    assert data["system_health"]["api_status"] == "nominal"
    assert data["security_metrics"]["failed_logins_24h"] == 0
