import unittest
from unittest.mock import patch
import mongomock

# Patch pymongo.MongoClient with a shared mongomock.MongoClient globally for tests
shared_client = mongomock.MongoClient()
patcher = patch("repositories.mongodb.MongoClient", return_value=shared_client)
patcher.start()

import os
from app import create_app
from bootstrap import bootstrap_repository
from routes.forms import store
from repositories.mongodb import MongoDBRepository


class FormResponseServiceTest(unittest.TestCase):
    def setUp(self):
        os.environ["DATABASE_URL"] = "mongodb://localhost:27017/form_response_test"
        self.app = create_app()
        self.client = self.app.test_client()

    def tearDown(self):
        # Clear collections after each test to keep tests isolated
        from routes.forms import store as current_store
        if isinstance(current_store, MongoDBRepository):
            current_store.clear_forms()
            current_store.clear_responses()

    def test_ingest_form_and_validate_required_fields(self):
        form = {
            "id": "form-1",
            "title": "Survey",
            "sections": [{"id": "s1", "questions": [{"id": "q1", "type": "text", "required": True}]}],
        }
        resp = self.client.post("/forms/ingest", json=form)
        self.assertEqual(resp.status_code, 201)
        resp = self.client.post("/forms/form-1/responses", json={"answers": {}})
        self.assertEqual(resp.status_code, 400)

    def test_create_patch_and_get_response(self):
        self.client.post(
            "/forms/ingest",
            json={"id": "form-1", "sections": [{"id": "s1", "questions": [{"id": "q1", "type": "text", "required": True}]}]},
        )
        created = self.client.post("/forms/form-1/responses", json={"answers": {"q1": "A"}, "status": "draft"})
        self.assertEqual(created.status_code, 201)
        response_id = created.get_json()["response"]["response_id"]
        patched = self.client.patch(f"/responses/{response_id}", json={"status": "submitted"})
        self.assertEqual(patched.status_code, 200)
        fetched = self.client.get(f"/responses/{response_id}")
        self.assertEqual(fetched.status_code, 200)

    def test_persistence_survives_app_recreation(self):
        self.client.post(
            "/forms/ingest",
            json={"id": "form-2", "sections": [{"id": "s1", "questions": [{"id": "q1", "type": "text", "required": True}]}]},
        )
        created = self.client.post("/forms/form-2/responses", json={"answers": {"q1": "A"}, "status": "submitted"})
        response_id = created.get_json()["response"]["response_id"]

        recreated = create_app().test_client()
        fetched_form = recreated.get("/forms/form-2")
        fetched_response = recreated.get(f"/responses/{response_id}")
        self.assertEqual(fetched_form.status_code, 200)
        self.assertEqual(fetched_response.status_code, 200)

    def test_sync_analyser_generates_adapter_payload(self):
        self.client.post(
            "/forms/ingest",
            json={"id": "form-1", "sections": [{"id": "s1", "questions": [{"id": "q1", "type": "text", "required": True}]}]},
        )
        created = self.client.post("/forms/form-1/responses", json={"answers": {"q1": "A"}, "status": "submitted"})
        response_id = created.get_json()["response"]["response_id"]
        sync = self.client.post("/sync/analyser", json={"response_id": response_id})
        self.assertEqual(sync.status_code, 200)
        payload = sync.get_json()["sync"]["payload"]
        self.assertEqual(payload["form_id"], "form-1")
        self.assertEqual(payload["response_id"], response_id)

    def test_bootstrap_initializes_schema_and_health(self):
        db_url = "mongodb://localhost:27017/boot_test"
        repo = bootstrap_repository(db_url)
        self.assertTrue(repo.health_check())
        repo_again = bootstrap_repository(db_url)
        self.assertTrue(repo_again.health_check())

    def test_repository_contract_round_trip(self):
        repo = MongoDBRepository("mongodb://localhost:27017/contract_test")
        repo.initialize()
        self.assertTrue(repo.health_check())
        self.assertIsNone(repo.get_form("missing"))
        self.assertIsNone(repo.get_response("missing"))

    def test_health_endpoint_reports_ready(self):
        resp = self.client.get("/healthz")
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["database"])

    def test_form_versioning_increments_on_change(self):
        # Version 1
        resp = self.client.post(
            "/forms/ingest",
            json={"id": "versioned-form", "title": "First Version", "sections": []}
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.get_json()["form"]["snapshot_version"], 1)

        # Same structure should not increment
        resp = self.client.post(
            "/forms/ingest",
            json={"id": "versioned-form", "title": "First Version", "sections": []}
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.get_json()["form"]["snapshot_version"], 1)

        # Changed structure should increment to version 2
        resp = self.client.post(
            "/forms/ingest",
            json={"id": "versioned-form", "title": "Second Version", "sections": []}
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.get_json()["form"]["snapshot_version"], 2)

        # Get specific version
        resp_v1 = self.client.get("/forms/versioned-form?version=1")
        self.assertEqual(resp_v1.status_code, 200)
        self.assertEqual(resp_v1.get_json()["form"]["title"], "First Version")

        resp_v2 = self.client.get("/forms/versioned-form?version=2")
        self.assertEqual(resp_v2.status_code, 200)
        self.assertEqual(resp_v2.get_json()["form"]["title"], "Second Version")

    def test_strict_type_and_choice_validation(self):
        self.client.post(
            "/forms/ingest",
            json={
                "id": "strict-form",
                "sections": [
                    {
                        "id": "s1",
                        "questions": [
                            {"id": "q_num", "type": "number", "required": False},
                            {"id": "q_choice", "type": "choice", "choices": ["A", "B"], "required": False},
                            {"id": "q_bool", "type": "boolean", "required": False},
                        ]
                    }
                ]
            }
        )

        # Valid payload
        resp = self.client.post("/forms/strict-form/responses", json={"answers": {"q_num": 42, "q_choice": "A", "q_bool": True}})
        self.assertEqual(resp.status_code, 201)

        # Invalid number type
        resp = self.client.post("/forms/strict-form/responses", json={"answers": {"q_num": "not-a-number"}})
        self.assertEqual(resp.status_code, 400)

        # Invalid choice value
        resp = self.client.post("/forms/strict-form/responses", json={"answers": {"q_choice": "C"}})
        self.assertEqual(resp.status_code, 400)

        # Invalid boolean type
        resp = self.client.post("/forms/strict-form/responses", json={"answers": {"q_bool": "yes"}})
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
