import unittest
import json
from app import app
from validator import FormSubmissionValidator

class TestProgrammableEngine(unittest.TestCase):
    def test_draft_partial_saves_and_patch(self):
        client = app.test_client()

        # 1. Create a form with a custom block script validation and a required field
        form_payload = {
            "title": "Loan Application",
            "block_script": {
                "blocks": [
                    {
                        "type": "conditional",
                        "condition": {
                            "field": "q_income",
                            "operator": "<",
                            "value": 20000
                        },
                        "then_actions": [
                            {
                                "type": "show_error",
                                "field_id": "custom_script",
                                "message": "Salary too low"
                            }
                        ],
                        "else_actions": []
                    }
                ]
            },
            "sections": [
                {
                    "id": "sec_main",
                    "questions": [
                        {"id": "q_name", "type": "text", "required": True},
                        {"id": "q_income", "type": "number", "required": True}
                    ]
                }
            ]
        }
        res_form = client.post("/api/forms", json=form_payload)
        form = json.loads(res_form.data)
        form_id = form["_id"]

        # Scenario A: Post a Draft missing the required 'q_income' field.
        # Should succeed because it is flagged as a "Draft".
        draft_payload = {
            "status": "Draft",
            "q_name": "Alice"
        }
        res_submit = client.post(f"/api/forms/{form_id}/submit", json=draft_payload)
        self.assertEqual(res_submit.status_code, 201)
        resp_data = json.loads(res_submit.data)
        response_id = resp_data["response"]["_id"]
        self.assertEqual(resp_data["response"]["status"], "Draft")

        # Scenario B: Try to promote Draft to Submitted without providing 'q_income'.
        # Should fail validation because 'q_income' is required for full submission.
        promote_payload = {
            "status": "Submitted",
            "answers": {}
        }
        res_patch = client.patch(f"/api/responses/{response_id}", json=promote_payload)
        self.assertEqual(res_patch.status_code, 400)
        err_data = json.loads(res_patch.data)
        self.assertIn("q_income", err_data["details"])

        # Scenario C: Supply invalid salary (< 20000) trigger python sandbox script validation.
        # Should fail with custom script warning.
        promote_payload_invalid = {
            "status": "Submitted",
            "answers": {"q_income": 15000}
        }
        res_patch_script_fail = client.patch(f"/api/responses/{response_id}", json=promote_payload_invalid)
        self.assertEqual(res_patch_script_fail.status_code, 400)
        err_data_script = json.loads(res_patch_script_fail.data)
        self.assertIn("custom_script", err_data_script["details"])
        self.assertEqual(err_data_script["details"]["custom_script"], "Salary too low")

        # Scenario D: Submit valid values. Should succeed.
        promote_payload_valid = {
            "status": "Submitted",
            "answers": {"q_income": 35000}
        }
        res_patch_success = client.patch(f"/api/responses/{response_id}", json=promote_payload_valid)
        self.assertEqual(res_patch_success.status_code, 200)
        success_data = json.loads(res_patch_success.data)
        self.assertEqual(success_data["response"]["status"], "Submitted")

if __name__ == "__main__":
    unittest.main()
