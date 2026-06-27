import unittest
import os
import tempfile

from app import create_app
from bootstrap import bootstrap_repository, resolve_sqlite_path
from routes.forms import store
from repositories.sqlite import SQLiteRepository


class FormResponseServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATABASE_URL"] = f"sqlite:///{self.tmpdir.name}/form-response.db"
        self.app = create_app()
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmpdir.cleanup()

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
        db_url = f"sqlite:///{self.tmpdir.name}/boot.db"
        repo = bootstrap_repository(db_url)
        self.assertTrue(repo.health_check())
        self.assertTrue(resolve_sqlite_path(db_url).exists())
        repo_again = bootstrap_repository(db_url)
        self.assertTrue(repo_again.health_check())

    def test_repository_contract_round_trip(self):
        repo = SQLiteRepository(f"sqlite:///{self.tmpdir.name}/contract.db")
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



if __name__ == "__main__":
    unittest.main()
