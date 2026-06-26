import unittest
import json
from app import app
from validator import FormSubmissionValidator

class TestRepeatableAndNewTypes(unittest.TestCase):
    def test_repeatable_sections(self):
        # A form containing a repeatable section: "sec_passengers"
        form_definition = {
            "title": "Booking Form",
            "sections": [
                {
                    "id": "sec_passengers",
                    "title": "Passengers",
                    "repeatable": True,
                    "questions": [
                        {"id": "q_name", "type": "text", "required": True},
                        {"id": "q_age", "type": "number", "required": True}
                    ]
                }
            ]
        }

        # Case A: Valid inputs
        validator = FormSubmissionValidator(form_definition)
        is_valid, answers, errors = validator.validate_and_compute({
            "sec_passengers": [
                {"q_name": "Bob", "q_age": 45},
                {"q_name": "Alice", "q_age": 42}
            ]
        })
        self.assertTrue(is_valid)
        self.assertEqual(len(answers["sec_passengers"]), 2)
        self.assertEqual(answers["sec_passengers"][0]["q_name"], "Bob")

        # Case B: Validation failure inside repeated panel (missing required fields in second panel)
        is_valid, answers, errors = validator.validate_and_compute({
            "sec_passengers": [
                {"q_name": "Bob", "q_age": 45},
                {"q_name": "Alice"} # missing q_age
            ]
        })
        self.assertFalse(is_valid)
        self.assertIn("sec_passengers[1].q_age", errors)

    def test_new_question_types_validation(self):
        form_definition = {
            "title": "Additional Details",
            "sections": [
                {
                    "id": "sec_main",
                    "questions": [
                        {
                            "id": "q_agree",
                            "type": "boolean",
                            "required": True
                        },
                        {
                            "id": "q_preferences",
                            "type": "ranking",
                            "properties": {
                                "choices": ["A", "B", "C"]
                            }
                        },
                        {
                            "id": "q_matrix",
                            "type": "matrix",
                            "properties": {
                                "rows": ["row1", "row2"],
                                "columns": ["col1", "col2"]
                            }
                        },
                        {
                            "id": "q_custom",
                            "type": "custom",
                            "properties": {
                                "custom_widget_name": "tag-box"
                            }
                        }
                    ]
                }
            ]
        }

        validator = FormSubmissionValidator(form_definition)
        is_valid, answers, errors = validator.validate_and_compute({
            "q_agree": True,
            "q_preferences": ["C", "A", "B"],
            "q_matrix": {"row1": "col2", "row2": "col1"},
            "q_custom": "custom-val"
        })
        self.assertTrue(is_valid)
        self.assertEqual(answers["q_agree"], True)
        self.assertEqual(answers["q_preferences"], ["C", "A", "B"])
        self.assertEqual(answers["q_matrix"]["row1"], "col2")
        self.assertEqual(answers["q_custom"], "custom-val")

if __name__ == "__main__":
    unittest.main()
