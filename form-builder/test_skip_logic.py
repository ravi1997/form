import unittest
import json
from app import app
from condition_evaluator import ConditionEvaluator
from validator import FormSubmissionValidator

class TestAdvancedFormFeatures(unittest.TestCase):
    def test_condition_evaluation(self):
        # Age condition: >= 18
        cond = {"field": "q_age", "operator": ">=", "value": 18}
        
        self.assertTrue(ConditionEvaluator.evaluate_condition(cond, {"q_age": 20}))
        self.assertFalse(ConditionEvaluator.evaluate_condition(cond, {"q_age": 16}))
        
        # Choice condition
        cond_choice = {"field": "q_satisfaction", "operator": "==", "value": "Very Satisfied"}
        self.assertTrue(ConditionEvaluator.evaluate_condition(cond_choice, {"q_satisfaction": "Very Satisfied"}))
        self.assertFalse(ConditionEvaluator.evaluate_condition(cond_choice, {"q_satisfaction": "Neutral"}))

    def test_section_and_question_skip_logic(self):
        # We define a versioned form structure with two sections.
        # The second section is only visible if q_member is "Yes".
        form_definition = {
            "title": "Membership Survey",
            "current_version": 1,
            "versions": [
                {
                    "version_number": 1,
                    "sections": [
                        {
                            "id": "sec_general",
                            "title": "General Info",
                            "questions": [
                                {
                                    "id": "q_member",
                                    "type": "multiple_choice",
                                    "required": True,
                                    "properties": {
                                        "choices": ["Yes", "No"]
                                    }
                                }
                            ]
                        },
                        {
                            "id": "sec_member_details",
                            "title": "Member Feedback",
                            "conditions": [
                                {"field": "q_member", "operator": "==", "value": "Yes"}
                            ],
                            "questions": [
                                {
                                    "id": "q_member_id",
                                    "type": "text",
                                    "required": True,
                                    "validations": [
                                        {
                                            "type": "regex",
                                            "pattern": "^MEM-\\d{4}$",
                                            "error_message": "Member ID must be in format MEM-XXXX"
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }

        # Case A: User is not a member. Section 2 is skipped. 
        # Even though "q_member_id" is required, it shouldn't produce a validation error because its section is skipped!
        validator = FormSubmissionValidator(form_definition)
        is_valid, answers, errors = validator.validate_and_compute({
            "q_member": "No"
        })
        self.assertTrue(is_valid)
        self.assertEqual(answers.get("q_member"), "No")
        self.assertNotIn("q_member_id", answers) # Skipped

        # Case B: User is a member. Section 2 is active.
        # "q_member_id" is required and must match regex. Let's supply an invalid ID first.
        is_valid, answers, errors = validator.validate_and_compute({
            "q_member": "Yes",
            "q_member_id": "1234"
        })
        self.assertFalse(is_valid)
        self.assertIn("q_member_id", errors)
        self.assertEqual(errors["q_member_id"], "Member ID must be in format MEM-XXXX")

        # Case C: User is a member and supplies valid ID matching regex.
        is_valid, answers, errors = validator.validate_and_compute({
            "q_member": "Yes",
            "q_member_id": "MEM-5678"
        })
        self.assertTrue(is_valid)
        self.assertEqual(answers.get("q_member_id"), "MEM-5678")

    def test_api_version_management_flow(self):
        client = app.test_client()
        
        # 1. Create form (initially version 1)
        form_payload = {
            "title": "Feedback Project Forms",
            "sections": [
                {
                    "id": "s1",
                    "title": "Welcome",
                    "questions": [{"id": "q_name", "type": "text", "required": True}]
                }
            ]
        }
        res = client.post("/api/forms", json=form_payload)
        form = json.loads(res.data)
        form_id = form["_id"]
        self.assertEqual(form["current_version"], 1)

        # 2. Add a new version (version 2) with extra questions
        new_version_payload = {
            "sections": [
                {
                    "id": "s1",
                    "title": "Welcome",
                    "questions": [{"id": "q_name", "type": "text", "required": True}]
                },
                {
                    "id": "s2",
                    "title": "Details",
                    "questions": [{"id": "q_email", "type": "text", "required": True}]
                }
            ]
        }
        res_v = client.post(f"/api/forms/{form_id}/versions", json=new_version_payload)
        new_ver = json.loads(res_v.data)
        self.assertEqual(new_ver["version_number"], 2)

        # 3. Publish version 2
        res_pub = client.post(f"/api/forms/{form_id}/publish", json={"version_number": 2})
        self.assertEqual(res_pub.status_code, 200)

        # 4. Check form surveyjs output matches published version 2 (should have 2 pages)
        res_sjs = client.get(f"/api/forms/{form_id}/surveyjs")
        sjs = json.loads(res_sjs.data)
        self.assertEqual(len(sjs["pages"]), 2)

if __name__ == "__main__":
    unittest.main()
