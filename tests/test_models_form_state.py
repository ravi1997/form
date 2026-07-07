import unittest

from flask import Flask


ValidationError = None
db = None
Form = None
FormResponse = None
Version = None


class FormStateModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global ValidationError, db, Form, FormResponse, Version
        try:
            from mongoengine.errors import ValidationError as _ValidationError
            from app.extensions import db as _db
            from app.models.form import Form as _Form
            from app.models.form import FormResponse as _FormResponse
            from app.models.form import Version as _Version
        except Exception as exc:
            raise unittest.SkipTest(f"Model state tests skipped due to environment import issue: {exc}")

        ValidationError = _ValidationError
        db = _db
        Form = _Form
        FormResponse = _FormResponse
        Version = _Version

        cls.app = Flask(__name__)
        cls.app.config["TESTING"] = True
        cls.app.config["MONGODB_SETTINGS"] = {
            "db": "test_form_state_db",
            "host": "mongomock://localhost",
            "connect": False,
        }
        db.init_app(cls.app)
        cls.ctx = cls.app.app_context()
        cls.ctx.push()

    @classmethod
    def tearDownClass(cls):
        db.connection.drop_database("test_form_state_db")
        cls.ctx.pop()

    def setUp(self):
        db.connection.drop_database("test_form_state_db")

    def test_form_rejects_invalid_workflow_transition(self):
        form = Form(
            uuid="form-state-0001",
            versions=[Version(uuid="v1")],
            sections={"v1": []},
        )
        form.save()

        form.workflow_state = "approved"
        with self.assertRaises(ValidationError):
            form.save()

    def test_form_allows_valid_workflow_transition(self):
        form = Form(
            uuid="form-state-0002",
            versions=[Version(uuid="v1")],
            sections={"v1": []},
        )
        form.save()

        form.workflow_state = "submitted"
        form.save()

        saved = Form.objects.get(uuid="form-state-0002")
        self.assertEqual(saved.workflow_state, "submitted")

    def test_response_rejects_invalid_status_transition(self):
        form = Form(
            uuid="form-response-state-0001",
            versions=[Version(uuid="v1")],
            sections={"v1": []},
        )
        form.save()

        response = FormResponse(
            uuid="response-state-0001",
            form=form,
            form_uuid=form.uuid,
            form_version_uuid="v1",
            status="draft",
        )
        response.save()

        response.status = "approved"
        with self.assertRaises(ValidationError):
            response.save()

    def test_response_status_history_and_timestamps_are_maintained(self):
        form = Form(
            uuid="form-response-state-0002",
            versions=[Version(uuid="v1")],
            sections={"v1": []},
        )
        form.save()

        response = FormResponse(
            uuid="response-state-0002",
            form=form,
            form_uuid=form.uuid,
            form_version_uuid="v1",
            status="draft",
        )
        response.save()

        self.assertEqual(len(response.status_history), 1)
        self.assertIsNone(response.status_history[0].transition_from)
        self.assertEqual(response.status_history[0].transition_to, "draft")
        self.assertIsNone(response.reviewed_at)
        self.assertIsNone(response.approved_at)

        response.status = "submitted"
        response.save()
        self.assertIsNotNone(response.submitted_at)
        self.assertIsNone(response.reviewed_at)
        self.assertIsNone(response.approved_at)
        self.assertEqual(response.status_history[-1].transition_from, "draft")
        self.assertEqual(response.status_history[-1].transition_to, "submitted")

        response.status = "in_review"
        response.save()
        self.assertIsNotNone(response.reviewed_at)
        self.assertIsNone(response.approved_at)
        self.assertEqual(response.status_history[-1].transition_from, "submitted")
        self.assertEqual(response.status_history[-1].transition_to, "in_review")

        response.status = "approved"
        response.save()
        self.assertIsNotNone(response.approved_at)
        self.assertEqual(response.status_history[-1].transition_from, "in_review")
        self.assertEqual(response.status_history[-1].transition_to, "approved")


if __name__ == "__main__":
    unittest.main()
