"""
tests/test_api.py
-----------------
Integration tests for the Flask Form Analyser authentication, RBAC,
and multi-tenant isolation API endpoints.
"""

from __future__ import annotations
import mongomock
import pytest
from app import create_app
from config import DevelopmentConfig

@pytest.fixture
def client():
    # Load app with a mocked MongoClient
    class TestConfig(DevelopmentConfig):
        AUTH_ENABLED = True
        # Use development configs
        
    app = create_app(TestConfig)
    mock_client = mongomock.MongoClient()
    db = mock_client.test_db
    
    # Override app extensions with mocked mongo collections
    app.extensions["db"]              = db
    app.extensions["responses_col"]   = db["form_responses"]
    app.extensions["definitions_col"] = db["analysis_definitions"]
    app.extensions["results_col"]     = db["analysis_results"]
    app.extensions["keys_col"]        = db["api_keys"]
    app.extensions["webhooks_col"]    = db["webhooks"]
    app.extensions["forms_col"]       = db["forms"]
    app.extensions["users_col"]       = db["users"]
    
    with app.test_client() as test_client:
        yield test_client


def test_registration_and_login(client):
    # 1. Register a user
    resp = client.post("/api/v1/auth/register", json={
        "username": "alice",
        "password": "secretpassword",
        "organization_id": "org_a",
        "role": "admin"
    })
    assert resp.status_code == 201
    assert resp.json["data"]["username"] == "alice"
    assert resp.json["data"]["role"] == "admin"
    
    # 2. Login to receive JWT Token
    resp = client.post("/api/v1/auth/login", json={
        "username": "alice",
        "password": "secretpassword"
    })
    assert resp.status_code == 200
    token = resp.json["data"]["token"]
    assert token is not None


def test_rbac_and_multi_tenant_isolation(client):
    # Register and login Admin on Org A
    resp = client.post("/api/v1/auth/register", json={
        "username": "admin_a",
        "password": "password",
        "organization_id": "org_a",
        "role": "admin"
    })
    resp = client.post("/api/v1/auth/login", json={
        "username": "admin_a",
        "password": "password"
    })
    token_a = resp.json["data"]["token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Register and login Viewer on Org B
    resp = client.post("/api/v1/auth/register", json={
        "username": "viewer_b",
        "password": "password",
        "organization_id": "org_b",
        "role": "viewer"
    })
    resp = client.post("/api/v1/auth/login", json={
        "username": "viewer_b",
        "password": "password"
    })
    token_b = resp.json["data"]["token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # 1. Admin A can create a definition
    resp = client.post("/api/v1/analysis", headers=headers_a, json={
        "name": "Org A Survey",
        "source_collection": "form_responses",
        "steps": [{"id": "step1", "type": "frequency", "field": "status"}]
    })
    assert resp.status_code == 201
    def_id = resp.json["data"]["_id"]
    assert resp.json["data"]["organization_id"] == "org_a"

    # 2. Viewer B tries to access Org A's definition -> Should fail (404/not found to isolate tenant info)
    resp = client.get(f"/api/v1/analysis/{def_id}", headers=headers_b)
    assert resp.status_code == 404

    # 3. Viewer B tries to create a definition -> Should fail (403 forbidden due to RBAC viewer role limits)
    resp = client.post("/api/v1/analysis", headers=headers_b, json={
        "name": "Org B Survey",
        "source_collection": "form_responses",
        "steps": [{"id": "step1", "type": "frequency", "field": "status"}]
    })
    assert resp.status_code == 403
