import unittest
import os
import shutil
import base64
from datetime import datetime

from surveyjs_translator import SurveyJSTranslator
from validator import FormSubmissionValidator, SafeFormulaEvaluator

class TestSurveyJSTranslator(unittest.TestCase):
    def test_translation_mapping(self):
        form_data = {
            "title": "Customer Survey",
            "description": "Feedback form",
            "questions": [
                {
                    "id": "q_satisfaction",
                    "type": "multiple_choice",
                    "title": "How satisfied are you?",
                    "required": True,
                    "hint": "Scale of 1-10",
                    "properties": {
                        "multiselect": False,
                        "choices": [
                            {"value": "Very Satisfied", "score": 10},
                            {"value": "Neutral", "score": 5}
                        ]
                    }
                },
                {
                    "id": "q_text",
                    "type": "text",
                    "title": "Comments",
                    "properties": {
                        "multiline": True
                    }
                },
                {
                    "id": "q_num",
                    "type": "number",
                    "title": "Age",
                    "properties": {
                        "min": 18,
                        "max": 99
                    }
                },
                {
                    "id": "q_range",
                    "type": "range",
                    "title": "Rating",
                    "properties": {
                        "min": 1,
                        "max": 5,
                        "step": 1
                    }
                }
            ]
        }
        
        translated = SurveyJSTranslator.translate_form(form_data)
        elements = translated["pages"][0]["elements"]
        
        self.assertEqual(translated["title"], "Customer Survey")
        
        # Check multiple choice translation
        self.assertEqual(elements[0]["name"], "q_satisfaction")
        self.assertEqual(elements[0]["type"], "radiogroup")
        self.assertEqual(elements[0]["description"], "Scale of 1-10")
        self.assertEqual(elements[0]["choices"][0]["value"], "Very Satisfied")
        
        # Check text (multiline) translation
        self.assertEqual(elements[1]["name"], "q_text")
        self.assertEqual(elements[1]["type"], "comment")
        
        # Check number translation
        self.assertEqual(elements[2]["name"], "q_num")
        self.assertEqual(elements[2]["type"], "text")
        self.assertEqual(elements[2]["inputType"], "number")
        self.assertEqual(elements[2]["min"], 18)
        self.assertEqual(elements[2]["max"], 99)

        # Check range translation
        self.assertEqual(elements[3]["name"], "q_range")
        self.assertEqual(elements[3]["type"], "rating")
        self.assertEqual(elements[3]["rateMin"], 1)
        self.assertEqual(elements[3]["rateMax"], 5)


class TestFormValidatorAndCalculations(unittest.TestCase):
    def setUp(self):
        self.form_definition = {
            "title": "Feedback Survey",
            "questions": [
                {
                    "id": "q_satisfaction",
                    "type": "multiple_choice",
                    "required": True,
                    "properties": {
                        "choices": [
                            {"value": "Very Satisfied", "score": 10},
                            {"value": "Neutral", "score": 5},
                            {"value": "Dissatisfied", "score": 1}
                        ]
                    }
                },
                {
                    "id": "q_score",
                    "type": "number",
                    "properties": {
                        "min": 0,
                        "max": 10
                    }
                },
                {
                    "id": "q_calc",
                    "type": "calculation",
                    "calculation_formula": "(q_score * 0.5) + q_satisfaction_score"
                }
            ]
        }

    def test_safe_formula_evaluator(self):
        variables = {
            "q_score": 10,
            "q_satisfaction_score": 5
        }
        res = SafeFormulaEvaluator.evaluate("(q_score * 0.5) + q_satisfaction_score", variables)
        self.assertEqual(res, 10.0)

    def test_validation_and_computation_success(self):
        validator = FormSubmissionValidator(self.form_definition)
        submitted_data = {
            "q_satisfaction": "Very Satisfied",
            "q_score": 8
        }
        is_valid, answers, errors = validator.validate_and_compute(submitted_data)
        
        self.assertTrue(is_valid)
        self.assertEqual(answers["q_satisfaction"], "Very Satisfied")
        self.assertEqual(answers["q_score"], 8)
        # Expected calculation: (8 * 0.5) + 10 = 14.0
        self.assertEqual(answers["q_calc"], 14.0)
        self.assertEqual(len(errors), 0)

    def test_validation_failure(self):
        validator = FormSubmissionValidator(self.form_definition)
        
        # Out of bounds number
        submitted_data = {
            "q_satisfaction": "Very Satisfied",
            "q_score": 25
        }
        is_valid, answers, errors = validator.validate_and_compute(submitted_data)
        self.assertFalse(is_valid)
        self.assertIn("q_score", errors)

        # Missing required field
        submitted_data = {
            "q_score": 5
        }
        is_valid, answers, errors = validator.validate_and_compute(submitted_data)
        self.assertFalse(is_valid)
        self.assertIn("q_satisfaction", errors)

        # Invalid choice
        submitted_data = {
            "q_satisfaction": "Extremely Happy",
            "q_score": 5
        }
        is_valid, answers, errors = validator.validate_and_compute(submitted_data)
        self.assertFalse(is_valid)
        self.assertIn("q_satisfaction", errors)


if __name__ == "__main__":
    unittest.main()
