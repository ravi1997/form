import os
import pathlib
import importlib.util
import unittest
from unittest import mock

CONFIG_FILE = pathlib.Path(__file__).resolve().parents[1] / "app" / "config.py"
SPEC = importlib.util.spec_from_file_location("form_config", CONFIG_FILE)
CONFIG_MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(CONFIG_MODULE)

BaseConfig = CONFIG_MODULE.BaseConfig
DevelopmentConfig = CONFIG_MODULE.DevelopmentConfig
ProductionConfig = CONFIG_MODULE.ProductionConfig
get_config_class = CONFIG_MODULE.get_config_class


class DummyConfig(dict):
    def from_object(self, obj):
        for name in dir(obj):
            if name.isupper():
                self[name] = getattr(obj, name)

    def from_mapping(self, mapping):
        self.update(mapping)


class DummyApp:
    def __init__(self):
        self.config = DummyConfig()


class ConfigTests(unittest.TestCase):
    def test_get_config_class_aliases(self):
        self.assertIs(get_config_class("development"), DevelopmentConfig)
        self.assertIs(get_config_class("local"), DevelopmentConfig)
        self.assertIs(get_config_class("production"), ProductionConfig)
        self.assertIs(get_config_class("staging"), ProductionConfig)

    def test_development_fallback_secret_is_set(self):
        app = DummyApp()
        with mock.patch.dict(os.environ, {"APP_ENV": "development"}, clear=True):
            with self.assertWarns(RuntimeWarning):
                DevelopmentConfig.load_app_config(app)

        self.assertEqual(app.config["JWT_SECRET_KEY"], "dev-insecure-secret-change-me")

    def test_production_requires_secret(self):
        app = DummyApp()
        with mock.patch.dict(os.environ, {"APP_ENV": "production"}, clear=True):
            with self.assertRaises(RuntimeError):
                ProductionConfig.load_app_config(app)

    def test_invalid_integer_env_raises(self):
        app = DummyApp()
        with mock.patch.dict(
            os.environ,
            {
                "APP_ENV": "development",
                "JWT_ACCESS_TOKEN_EXPIRES_MINUTES": "abc",
            },
            clear=True,
        ):
            with self.assertRaises(RuntimeError):
                DevelopmentConfig.load_app_config(app)

    def test_bounds_validation_raises(self):
        app = DummyApp()
        with mock.patch.dict(
            os.environ,
            {
                "APP_ENV": "development",
                "JWT_ACCESS_TOKEN_EXPIRES_MINUTES": "2000",
            },
            clear=True,
        ):
            with self.assertRaises(RuntimeError):
                DevelopmentConfig.load_app_config(app)

    def test_resource_rate_limit_bounds_validation_raises(self):
        app = DummyApp()
        cases = [
            {"RESOURCE_RATE_LIMIT_MAX": "10001"},
            {"RESOURCE_RATE_LIMIT_WINDOW_SECONDS": "0"},
        ]

        for overrides in cases:
            with self.subTest(overrides=overrides):
                env = {"APP_ENV": "development"}
                env.update(overrides)
                with mock.patch.dict(os.environ, env, clear=True):
                    with self.assertRaises(RuntimeError):
                        DevelopmentConfig.load_app_config(app)

    def test_invalid_workflow_rbac_boolean_env_raises(self):
        app = DummyApp()
        with mock.patch.dict(
            os.environ,
            {
                "APP_ENV": "development",
                "RESOURCE_RBAC_REQUIRE_ORG_ROLE_ALIGNMENT": "maybe",
            },
            clear=True,
        ):
            with self.assertRaises(RuntimeError):
                DevelopmentConfig.load_app_config(app)

    def test_public_config_snapshot_includes_workflow_rbac_flags(self):
        snapshot = BaseConfig.public_config_snapshot(
            {
                "RESOURCE_RBAC_REQUIRE_ORG_ROLE_ALIGNMENT": False,
                "WORKFLOW_STRICT_REVIEW_BEFORE_APPROVE": False,
            }
        )

        self.assertIn("resource_rbac_require_org_role_alignment", snapshot)
        self.assertIn("workflow_strict_review_before_approve", snapshot)
        self.assertFalse(snapshot["resource_rbac_require_org_role_alignment"])
        self.assertFalse(snapshot["workflow_strict_review_before_approve"])

    def test_unknown_env_key_warns_in_development(self):
        app = DummyApp()
        with mock.patch.dict(
            os.environ,
            {
                "APP_ENV": "development",
                "JWT_SECRT_KEY": "typo",
            },
            clear=True,
        ):
            with self.assertWarns(RuntimeWarning):
                DevelopmentConfig.load_app_config(app)

    def test_unknown_env_key_fails_in_production(self):
        app = DummyApp()
        with mock.patch.dict(
            os.environ,
            {
                "APP_ENV": "production",
                "JWT_SECRET_KEY": "prod-secret",
                "JWT_SECRT_KEY": "typo",
            },
            clear=True,
        ):
            with self.assertRaises(RuntimeError):
                ProductionConfig.load_app_config(app)

    def test_production_mongodb_uri_exposes_explicit_auth_settings(self):
        app = DummyApp()
        with mock.patch.dict(
            os.environ,
            {
                "APP_ENV": "production",
                "JWT_SECRET_KEY": "prod-secret",
                "MONGODB_URI": (
                    "mongodb://formadmin:ci-mongo-secret@mongo:27017/form_prod"
                    "?authSource=admin"
                ),
            },
            clear=True,
        ):
            ProductionConfig.load_app_config(app)

        settings = app.config["MONGODB_SETTINGS"]
        self.assertEqual(settings["username"], "formadmin")
        self.assertEqual(settings["password"], "ci-mongo-secret")
        self.assertEqual(settings["authentication_source"], "admin")
        self.assertEqual(
            settings["host"], "mongodb://mongo:27017/form_prod?authSource=admin"
        )


if __name__ == "__main__":
    unittest.main()
