import unittest
import json
import time
from unittest.mock import patch, MagicMock
from bson import ObjectId
from app import app, db

class TestAdvancedFeatures(unittest.TestCase):
    def test_dry_run_debugger(self):
        client = app.test_client()
        
        # Create a form
        form_payload = {
            "title": "Debug Form",
            "sections": [
                {
                    "id": "s1",
                    "questions": [
                        {"id": "q_name", "type": "text", "required": True}
                    ]
                }
            ]
        }
        res_form = client.post("/api/forms", json=form_payload)
        form = json.loads(res_form.data)
        form_id = form["_id"]

        # Run Debug POST - Should report failure without saving response
        res_debug = client.post(f"/api/forms/{form_id}/debug", json={"answers": {}})
        data = json.loads(res_debug.data)
        self.assertFalse(data["is_valid"])
        self.assertIn("q_name", data["validation_errors"])

        # Validate that no response was written to database
        db_count = db["responses"].count_documents({"form_id": ObjectId(form_id)})
        self.assertEqual(db_count, 0)

    def test_batch_submission(self):
        client = app.test_client()
        
        form_payload = {
            "title": "Batch Form",
            "sections": [
                {
                    "id": "s1",
                    "questions": [
                        {"id": "q_name", "type": "text", "required": True}
                    ]
                }
            ]
        }
        res_form = client.post("/api/forms", json=form_payload)
        form = json.loads(res_form.data)
        form_id = form["_id"]

        # Post list of submissions - One valid, one invalid
        batch_payload_invalid = {
            "submissions": [
                {"q_name": "Dave"},
                {} # invalid
            ]
        }
        res_batch = client.post(f"/api/forms/{form_id}/submit-batch", json=batch_payload_invalid)
        self.assertEqual(res_batch.status_code, 207)

        # Post list of valid submissions
        batch_payload_valid = {
            "submissions": [
                {"q_name": "Dave"},
                {"q_name": "Eva"}
            ]
        }
        res_batch_ok = client.post(f"/api/forms/{form_id}/submit-batch", json=batch_payload_valid)
        self.assertEqual(res_batch_ok.status_code, 201)
        
        # Verify db contains 3 records (1 from partial success, 2 from full success)
        db_count = db["responses"].count_documents({"form_id": ObjectId(form_id)})
        self.assertEqual(db_count, 3)

    def test_idempotency_key(self):
        client = app.test_client()
        
        form_payload = {
            "title": "Idempotency Form",
            "sections": [
                {
                    "id": "s1",
                    "questions": [{"id": "q_name", "type": "text", "required": True}]
                }
            ]
        }
        res_form = client.post("/api/forms", json=form_payload)
        form = json.loads(res_form.data)
        form_id = form["_id"]

        idem_key = f"key_{ObjectId()}"

        # Submit first time
        res_sub1 = client.post(
            f"/api/forms/{form_id}/submit", 
            json={"q_name": "Alice"},
            headers={"X-Idempotency-Key": idem_key}
        )
        self.assertEqual(res_sub1.status_code, 201)
        data1 = json.loads(res_sub1.data)

        # Submit second time with same key
        res_sub2 = client.post(
            f"/api/forms/{form_id}/submit", 
            json={"q_name": "Bob"}, # different name, should be ignored
            headers={"X-Idempotency-Key": idem_key}
        )
        self.assertEqual(res_sub2.status_code, 200)
        data2 = json.loads(res_sub2.data)
        
        # Verify duplicate payload returns the cached response
        self.assertEqual(data1["response"]["_id"], data2["response"]["_id"])
        self.assertEqual(data2["response"]["answers"]["q_name"], "Alice")

    def test_schema_drift_warning(self):
        client = app.test_client()
        
        # Create version 1
        form_payload = {
            "title": "Drift Form",
            "sections": [
                {
                    "id": "s1",
                    "questions": [{"id": "q_age", "type": "number"}]
                }
            ]
        }
        res_form = client.post("/api/forms", json=form_payload)
        form = json.loads(res_form.data)
        form_id = form["_id"]

        # Post version 2 with question deleted and type changed (shift from number to text)
        version_payload = {
            "sections": [
                {
                    "id": "s1",
                    "questions": [{"id": "q_age", "type": "text"}] # type shift
                }
            ]
        }
        res_v = client.post(f"/api/forms/{form_id}/versions", json=version_payload)
        self.assertEqual(res_v.status_code, 201)
        v_data = json.loads(res_v.data)
        
        # Verify drift warnings are returned
        warnings = v_data["drift_warnings"]
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["type"], "type_changed")

    def test_async_data_export(self):
        client = app.test_client()
        
        form_payload = {
            "title": "Export Form",
            "sections": [
                {
                    "id": "s1",
                    "questions": [{"id": "q_name", "type": "text"}]
                }
            ]
        }
        res_form = client.post("/api/forms", json=form_payload)
        form = json.loads(res_form.data)
        form_id = form["_id"]

        # Trigger async export
        res_exp = client.post(f"/api/forms/{form_id}/export/async", json={})
        self.assertEqual(res_exp.status_code, 202)
        task_data = json.loads(res_exp.data)
        task_id = task_data["task_id"]

        # Poll status
        for _ in range(5):
            res_status = client.get(f"/api/tasks/{task_id}")
            status_data = json.loads(res_status.data)
            if status_data["status"] in ["SUCCESS", "FAILED"]:
                break
            time.sleep(0.5)

        self.assertEqual(status_data["status"], "SUCCESS")
        self.assertIsNotNone(status_data["download_url"])

if __name__ == "__main__":
    unittest.main()
