import unittest
from flask import Blueprint, jsonify
from pymongo.errors import ConnectionFailure

# Import the app and the custom exception
from app import app, ValidationFailure

# Define a test blueprint for throwing various exceptions
test_errors_bp = Blueprint("test_errors", __name__)

@test_errors_bp.route("/test-error/value")
def throw_value_error():
    raise ValueError("Invalid value provided")

@test_errors_bp.route("/test-error/key")
def throw_key_error():
    raise KeyError("missing_field")

@test_errors_bp.route("/test-error/type")
def throw_type_error():
    raise TypeError("Invalid type matching")

@test_errors_bp.route("/test-error/pymongo")
def throw_pymongo_error():
    raise ConnectionFailure("Could not connect to MongoDB")

@test_errors_bp.route("/test-error/validation")
def throw_validation_failure():
    raise ValidationFailure("Validation error occurred", details={"field": "email", "issue": "format"})

@test_errors_bp.route("/test-error/generic")
def throw_generic_exception():
    raise Exception("Something went wrong internally")

# Register blueprint on the app
app.register_blueprint(test_errors_bp)

class CentralizedExceptionHandlerTest(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_value_error_handling(self):
        resp = self.client.get("/test-error/value")
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error"], "ValueError")
        self.assertEqual(data["message"], "Invalid value provided")

    def test_key_error_handling(self):
        resp = self.client.get("/test-error/key")
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error"], "KeyError")
        self.assertEqual(data["message"], "Missing required key/field: missing_field")

    def test_type_error_handling(self):
        resp = self.client.get("/test-error/type")
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error"], "TypeError")
        self.assertEqual(data["message"], "Invalid type matching")

    def test_pymongo_error_handling(self):
        resp = self.client.get("/test-error/pymongo")
        self.assertEqual(resp.status_code, 500)
        data = resp.get_json()
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error"], "DatabaseError")
        self.assertEqual(data["message"], "A database error occurred.")
        self.assertIn("Could not connect to MongoDB", data["details"])

    def test_validation_failure_handling(self):
        resp = self.client.get("/test-error/validation")
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error"], "ValidationFailure")
        self.assertEqual(data["message"], "Validation error occurred")
        self.assertEqual(data["details"], {"field": "email", "issue": "format"})

    def test_generic_exception_handling(self):
        resp = self.client.get("/test-error/generic")
        self.assertEqual(resp.status_code, 500)
        data = resp.get_json()
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error"], "InternalServerError")
        self.assertEqual(data["message"], "An unexpected error occurred.")

    def test_not_found_handling(self):
        resp = self.client.get("/test-error/non-existent-route-path")
        self.assertEqual(resp.status_code, 404)
        data = resp.get_json()
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error"], "Not Found")
        self.assertIn("not found", data["message"].lower())

if __name__ == "__main__":
    unittest.main()
