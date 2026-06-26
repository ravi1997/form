import unittest
from validator import FormSubmissionValidator

class TestMoreQuestionTypes(unittest.TestCase):
    def test_contacts_and_coordinate_types(self):
        form_definition = {
            "title": "Registration Forms",
            "sections": [
                {
                    "id": "sec_main",
                    "questions": [
                        {"id": "q_email", "type": "email", "required": True},
                        {"id": "q_url", "type": "url", "required": True},
                        {"id": "q_tel", "type": "tel", "required": True},
                        {
                            "id": "q_gps", 
                            "type": "location", 
                            "required": True
                        },
                        {
                            "id": "q_address",
                            "type": "multiple_text",
                            "properties": {
                                "items": [
                                    {"id": "street", "title": "Street"},
                                    {"id": "city", "title": "City"}
                                ]
                            }
                        }
                    ]
                }
            ]
        }

        # Case A: Valid inputs
        validator = FormSubmissionValidator(form_definition)
        is_valid, answers, errors = validator.validate_and_compute({
            "q_email": "test.user@company.com",
            "q_url": "https://company.com",
            "q_tel": "+1 (555) 019-2834",
            "q_gps": {"latitude": 37.7749, "longitude": -122.4194},
            "q_address": {"street": "123 Main St", "city": "San Francisco"}
        })
        self.assertTrue(is_valid)
        self.assertEqual(answers["q_email"], "test.user@company.com")
        self.assertEqual(answers["q_gps"]["latitude"], 37.7749)
        self.assertEqual(answers["q_address"]["city"], "San Francisco")

        # Case B: Validation failures
        is_valid, answers, errors = validator.validate_and_compute({
            "q_email": "bademail.com",
            "q_url": "not-a-url",
            "q_tel": "123",
            "q_gps": {"lat": 10}, # missing longitude
            "q_address": {"zip": "94103"} # invalid subkey
        })
        self.assertFalse(is_valid)
        self.assertIn("q_email", errors)
        self.assertIn("q_url", errors)
        self.assertIn("q_tel", errors)
        self.assertIn("q_gps", errors)
        self.assertIn("q_address", errors)

if __name__ == "__main__":
    unittest.main()
