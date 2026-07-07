from __future__ import annotations

import logging
import os
import warnings
from typing import Any, Dict, Mapping, Optional, Type


logger = logging.getLogger(__name__)


ENV_APP_ENV = "APP_ENV"
ENV_FLASK_ENV = "FLASK_ENV"

ENV_JWT_SECRET_KEY = "JWT_SECRET_KEY"
ENV_JWT_ACTIVE_KID = "JWT_ACTIVE_KID"
ENV_JWT_ADDITIONAL_KEYS = "JWT_ADDITIONAL_KEYS"
ENV_JWT_ALGORITHM = "JWT_ALGORITHM"
ENV_JWT_ACCESS_TOKEN_EXPIRES_MINUTES = "JWT_ACCESS_TOKEN_EXPIRES_MINUTES"
ENV_JWT_REFRESH_TOKEN_EXPIRES_DAYS = "JWT_REFRESH_TOKEN_EXPIRES_DAYS"

ENV_AUTH_RATE_LIMIT_LOGIN_MAX = "AUTH_RATE_LIMIT_LOGIN_MAX"
ENV_AUTH_RATE_LIMIT_LOGIN_WINDOW_SECONDS = "AUTH_RATE_LIMIT_LOGIN_WINDOW_SECONDS"
ENV_AUTH_RATE_LIMIT_REFRESH_MAX = "AUTH_RATE_LIMIT_REFRESH_MAX"
ENV_AUTH_RATE_LIMIT_REFRESH_WINDOW_SECONDS = "AUTH_RATE_LIMIT_REFRESH_WINDOW_SECONDS"
ENV_AUTH_RATE_LIMIT_LOGOUT_MAX = "AUTH_RATE_LIMIT_LOGOUT_MAX"
ENV_AUTH_RATE_LIMIT_LOGOUT_WINDOW_SECONDS = "AUTH_RATE_LIMIT_LOGOUT_WINDOW_SECONDS"
ENV_RESOURCE_RATE_LIMIT_MAX = "RESOURCE_RATE_LIMIT_MAX"
ENV_RESOURCE_RATE_LIMIT_WINDOW_SECONDS = "RESOURCE_RATE_LIMIT_WINDOW_SECONDS"
ENV_RESOURCE_RBAC_REQUIRE_ORG_ROLE_ALIGNMENT = "RESOURCE_RBAC_REQUIRE_ORG_ROLE_ALIGNMENT"
ENV_WORKFLOW_STRICT_REVIEW_BEFORE_APPROVE = "WORKFLOW_STRICT_REVIEW_BEFORE_APPROVE"
ENV_ENABLE_AUDIT_LOGS = "ENABLE_AUDIT_LOGS"
ENV_REQUEST_ID_HEADER = "REQUEST_ID_HEADER"
ENV_API_VERSION = "API_VERSION"
ENV_AUDIT_LOG_RETENTION_DAYS = "AUDIT_LOG_RETENTION_DAYS"


KNOWN_ENV_KEYS = {
    ENV_APP_ENV,
    ENV_FLASK_ENV,
    ENV_JWT_SECRET_KEY,
    ENV_JWT_ACTIVE_KID,
    ENV_JWT_ADDITIONAL_KEYS,
    ENV_JWT_ALGORITHM,
    ENV_JWT_ACCESS_TOKEN_EXPIRES_MINUTES,
    ENV_JWT_REFRESH_TOKEN_EXPIRES_DAYS,
    ENV_AUTH_RATE_LIMIT_LOGIN_MAX,
    ENV_AUTH_RATE_LIMIT_LOGIN_WINDOW_SECONDS,
    ENV_AUTH_RATE_LIMIT_REFRESH_MAX,
    ENV_AUTH_RATE_LIMIT_REFRESH_WINDOW_SECONDS,
    ENV_AUTH_RATE_LIMIT_LOGOUT_MAX,
    ENV_AUTH_RATE_LIMIT_LOGOUT_WINDOW_SECONDS,
    ENV_RESOURCE_RATE_LIMIT_MAX,
    ENV_RESOURCE_RATE_LIMIT_WINDOW_SECONDS,
    ENV_RESOURCE_RBAC_REQUIRE_ORG_ROLE_ALIGNMENT,
    ENV_WORKFLOW_STRICT_REVIEW_BEFORE_APPROVE,
    ENV_ENABLE_AUDIT_LOGS,
    ENV_REQUEST_ID_HEADER,
    ENV_API_VERSION,
    ENV_AUDIT_LOG_RETENTION_DAYS,
}


class BaseConfig:
    """Base app configuration shared by all environments."""

    DEBUG = False
    TESTING = False
    ENV_NAME = "base"

    JWT_ALGORITHM = "HS256"
    JWT_ACTIVE_KID = "v1"
    JWT_ACCESS_TOKEN_EXPIRES_MINUTES = 30
    JWT_REFRESH_TOKEN_EXPIRES_DAYS = 7
    JWT_ADDITIONAL_KEYS: Dict[str, str] = {}

    AUTH_RATE_LIMIT_LOGIN_MAX = 10
    AUTH_RATE_LIMIT_LOGIN_WINDOW_SECONDS = 60
    AUTH_RATE_LIMIT_REFRESH_MAX = 20
    AUTH_RATE_LIMIT_REFRESH_WINDOW_SECONDS = 60
    AUTH_RATE_LIMIT_LOGOUT_MAX = 20
    AUTH_RATE_LIMIT_LOGOUT_WINDOW_SECONDS = 60
    RESOURCE_RATE_LIMIT_MAX = 300
    RESOURCE_RATE_LIMIT_WINDOW_SECONDS = 60
    RESOURCE_RBAC_REQUIRE_ORG_ROLE_ALIGNMENT = True
    WORKFLOW_STRICT_REVIEW_BEFORE_APPROVE = True
    ENABLE_AUDIT_LOGS = True
    REQUEST_ID_HEADER = "X-Request-Id"
    API_VERSION = "v1"
    AUDIT_LOG_RETENTION_DAYS = 180

    ALLOWED_JWT_ALGORITHMS = {"HS256"}
    REQUIRED_POSITIVE_INT_KEYS = (
        "JWT_ACCESS_TOKEN_EXPIRES_MINUTES",
        "JWT_REFRESH_TOKEN_EXPIRES_DAYS",
        "AUTH_RATE_LIMIT_LOGIN_MAX",
        "AUTH_RATE_LIMIT_LOGIN_WINDOW_SECONDS",
        "AUTH_RATE_LIMIT_REFRESH_MAX",
        "AUTH_RATE_LIMIT_REFRESH_WINDOW_SECONDS",
        "AUTH_RATE_LIMIT_LOGOUT_MAX",
        "AUTH_RATE_LIMIT_LOGOUT_WINDOW_SECONDS",
        "RESOURCE_RATE_LIMIT_MAX",
        "RESOURCE_RATE_LIMIT_WINDOW_SECONDS",
        "AUDIT_LOG_RETENTION_DAYS",
    )

    INT_BOUNDS = {
        "JWT_ACCESS_TOKEN_EXPIRES_MINUTES": (1, 1440),
        "JWT_REFRESH_TOKEN_EXPIRES_DAYS": (1, 90),
        "AUTH_RATE_LIMIT_LOGIN_MAX": (1, 1000),
        "AUTH_RATE_LIMIT_LOGIN_WINDOW_SECONDS": (1, 3600),
        "AUTH_RATE_LIMIT_REFRESH_MAX": (1, 2000),
        "AUTH_RATE_LIMIT_REFRESH_WINDOW_SECONDS": (1, 3600),
        "AUTH_RATE_LIMIT_LOGOUT_MAX": (1, 2000),
        "AUTH_RATE_LIMIT_LOGOUT_WINDOW_SECONDS": (1, 3600),
        "RESOURCE_RATE_LIMIT_MAX": (1, 10000),
        "RESOURCE_RATE_LIMIT_WINDOW_SECONDS": (1, 3600),
        "AUDIT_LOG_RETENTION_DAYS": (1, 3650),
    }

    @staticmethod
    def _env_str(name: str, default: str) -> str:
        raw = os.getenv(name)
        if raw is None or raw.strip() == "":
            return default
        return raw.strip()

    @classmethod
    def _env_int(cls, name: str, default: int) -> int:
        raw = os.getenv(name)
        if raw is None or raw.strip() == "":
            return default
        try:
            return int(raw)
        except ValueError as exc:
            raise RuntimeError(f"{name} must be an integer") from exc

    @staticmethod
    def _env_key_map(name: str, default: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        raw = os.getenv(name)
        if raw is None or raw.strip() == "":
            return dict(default or {})

        items = [item.strip() for item in raw.split(",") if item.strip()]
        parsed: Dict[str, str] = {}
        for item in items:
            if ":" not in item:
                raise RuntimeError(f"{name} must be 'kid:secret,kid2:secret2'")
            kid, secret = item.split(":", 1)
            kid = kid.strip()
            secret = secret.strip()
            if not kid or not secret:
                raise RuntimeError(f"{name} contains an empty kid or secret")
            parsed[kid] = secret

        return parsed

    @staticmethod
    def _env_bool(name: str, default: bool) -> bool:
        raw = os.getenv(name)
        if raw is None or raw.strip() == "":
            return default

        normalized = raw.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        raise RuntimeError(f"{name} must be a boolean (true/false, 1/0, yes/no, on/off)")

    @staticmethod
    def get_str(config: Mapping[str, Any], key: str, default: str) -> str:
        value = config.get(key, default)
        return str(value).strip()

    @staticmethod
    def get_int(config: Mapping[str, Any], key: str, default: int) -> int:
        value = config.get(key, default)
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"{key} must be an integer") from exc

    @staticmethod
    def get_bool(config: Mapping[str, Any], key: str, default: bool) -> bool:
        value = config.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        raise RuntimeError(f"{key} must be a boolean")

    @classmethod
    def _warn_or_raise(cls, message: str) -> None:
        if cls.ENV_NAME == "production":
            raise RuntimeError(message)
        warnings.warn(message, RuntimeWarning, stacklevel=2)

    @classmethod
    def _validate_env_keys(cls) -> None:
        suspicious = []
        for key in os.environ.keys():
            if key in KNOWN_ENV_KEYS:
                continue
            if key.startswith("JWT_") or key.startswith("AUTH_RATE_LIMIT_"):
                suspicious.append(key)

        if suspicious:
            joined = ", ".join(sorted(suspicious))
            cls._warn_or_raise(f"Unknown auth config env key(s): {joined}")

    @classmethod
    def build_config_from_env(cls) -> Dict[str, Any]:
        cls._validate_env_keys()

        config = {
            "JWT_ALGORITHM": cls._env_str(ENV_JWT_ALGORITHM, cls.JWT_ALGORITHM),
            "JWT_ACTIVE_KID": cls._env_str(ENV_JWT_ACTIVE_KID, cls.JWT_ACTIVE_KID),
            "JWT_ACCESS_TOKEN_EXPIRES_MINUTES": cls._env_int(
                ENV_JWT_ACCESS_TOKEN_EXPIRES_MINUTES,
                cls.JWT_ACCESS_TOKEN_EXPIRES_MINUTES,
            ),
            "JWT_REFRESH_TOKEN_EXPIRES_DAYS": cls._env_int(
                ENV_JWT_REFRESH_TOKEN_EXPIRES_DAYS,
                cls.JWT_REFRESH_TOKEN_EXPIRES_DAYS,
            ),
            "AUTH_RATE_LIMIT_LOGIN_MAX": cls._env_int(
                ENV_AUTH_RATE_LIMIT_LOGIN_MAX,
                cls.AUTH_RATE_LIMIT_LOGIN_MAX,
            ),
            "AUTH_RATE_LIMIT_LOGIN_WINDOW_SECONDS": cls._env_int(
                ENV_AUTH_RATE_LIMIT_LOGIN_WINDOW_SECONDS,
                cls.AUTH_RATE_LIMIT_LOGIN_WINDOW_SECONDS,
            ),
            "AUTH_RATE_LIMIT_REFRESH_MAX": cls._env_int(
                ENV_AUTH_RATE_LIMIT_REFRESH_MAX,
                cls.AUTH_RATE_LIMIT_REFRESH_MAX,
            ),
            "AUTH_RATE_LIMIT_REFRESH_WINDOW_SECONDS": cls._env_int(
                ENV_AUTH_RATE_LIMIT_REFRESH_WINDOW_SECONDS,
                cls.AUTH_RATE_LIMIT_REFRESH_WINDOW_SECONDS,
            ),
            "AUTH_RATE_LIMIT_LOGOUT_MAX": cls._env_int(
                ENV_AUTH_RATE_LIMIT_LOGOUT_MAX,
                cls.AUTH_RATE_LIMIT_LOGOUT_MAX,
            ),
            "AUTH_RATE_LIMIT_LOGOUT_WINDOW_SECONDS": cls._env_int(
                ENV_AUTH_RATE_LIMIT_LOGOUT_WINDOW_SECONDS,
                cls.AUTH_RATE_LIMIT_LOGOUT_WINDOW_SECONDS,
            ),
            "RESOURCE_RATE_LIMIT_MAX": cls._env_int(
                ENV_RESOURCE_RATE_LIMIT_MAX,
                cls.RESOURCE_RATE_LIMIT_MAX,
            ),
            "RESOURCE_RATE_LIMIT_WINDOW_SECONDS": cls._env_int(
                ENV_RESOURCE_RATE_LIMIT_WINDOW_SECONDS,
                cls.RESOURCE_RATE_LIMIT_WINDOW_SECONDS,
            ),
            "RESOURCE_RBAC_REQUIRE_ORG_ROLE_ALIGNMENT": cls._env_bool(
                ENV_RESOURCE_RBAC_REQUIRE_ORG_ROLE_ALIGNMENT,
                cls.RESOURCE_RBAC_REQUIRE_ORG_ROLE_ALIGNMENT,
            ),
            "WORKFLOW_STRICT_REVIEW_BEFORE_APPROVE": cls._env_bool(
                ENV_WORKFLOW_STRICT_REVIEW_BEFORE_APPROVE,
                cls.WORKFLOW_STRICT_REVIEW_BEFORE_APPROVE,
            ),
            "ENABLE_AUDIT_LOGS": cls._env_bool(
                ENV_ENABLE_AUDIT_LOGS,
                cls.ENABLE_AUDIT_LOGS,
            ),
            "REQUEST_ID_HEADER": cls._env_str(
                ENV_REQUEST_ID_HEADER,
                cls.REQUEST_ID_HEADER,
            ),
            "API_VERSION": cls._env_str(
                ENV_API_VERSION,
                cls.API_VERSION,
            ),
            "AUDIT_LOG_RETENTION_DAYS": cls._env_int(
                ENV_AUDIT_LOG_RETENTION_DAYS,
                cls.AUDIT_LOG_RETENTION_DAYS,
            ),
            "JWT_ADDITIONAL_KEYS": cls._env_key_map(
                ENV_JWT_ADDITIONAL_KEYS,
                cls.JWT_ADDITIONAL_KEYS,
            ),
        }

        jwt_secret = os.getenv(ENV_JWT_SECRET_KEY)
        if jwt_secret:
            config["JWT_SECRET_KEY"] = jwt_secret.strip()

        return config

    @classmethod
    def validate_all(cls, app) -> None:
        algorithm = cls.get_str(app.config, "JWT_ALGORITHM", cls.JWT_ALGORITHM)
        if algorithm not in cls.ALLOWED_JWT_ALGORITHMS:
            raise RuntimeError(
                f"JWT_ALGORITHM must be one of {sorted(cls.ALLOWED_JWT_ALGORITHMS)}"
            )

        for key in cls.REQUIRED_POSITIVE_INT_KEYS:
            value = cls.get_int(app.config, key, 0)
            if value <= 0:
                raise RuntimeError(f"{key} must be a positive integer")

            lower, upper = cls.INT_BOUNDS[key]
            if value < lower or value > upper:
                raise RuntimeError(f"{key} must be between {lower} and {upper}")

        cls.get_bool(app.config, "ENABLE_AUDIT_LOGS", cls.ENABLE_AUDIT_LOGS)
        api_version = cls.get_str(app.config, "API_VERSION", cls.API_VERSION)
        if not api_version.startswith("v") or not api_version[1:].isdigit():
            raise RuntimeError("API_VERSION must use format v<integer>, for example v1")

        active_kid = cls.get_str(app.config, "JWT_ACTIVE_KID", cls.JWT_ACTIVE_KID)
        if not active_kid:
            raise RuntimeError("JWT_ACTIVE_KID cannot be empty")

        additional_keys = app.config.get("JWT_ADDITIONAL_KEYS", cls.JWT_ADDITIONAL_KEYS)
        if additional_keys is None:
            additional_keys = {}
        if not isinstance(additional_keys, dict):
            raise RuntimeError("JWT_ADDITIONAL_KEYS must be a mapping of kid -> secret")

        if cls.ENV_NAME == "production" and not app.config.get("JWT_SECRET_KEY"):
            raise RuntimeError("JWT_SECRET_KEY is required in production")

        if cls.ENV_NAME != "production" and not app.config.get("JWT_SECRET_KEY"):
            app.config["JWT_SECRET_KEY"] = "dev-insecure-secret-change-me"
            cls._warn_or_raise(
                "JWT_SECRET_KEY not set; using development fallback secret. "
                "Set JWT_SECRET_KEY for secure environments."
            )

        if active_kid in additional_keys and app.config.get("JWT_SECRET_KEY") == additional_keys.get(active_kid):
            cls._warn_or_raise(
                "JWT_ACTIVE_KID should point to the primary JWT_SECRET_KEY, "
                "not a duplicated key in JWT_ADDITIONAL_KEYS."
            )

    @classmethod
    def load_app_config(cls, app, overrides: Optional[Mapping[str, Any]] = None) -> None:
        app.config.from_object(cls)
        app.config.update(cls.build_config_from_env())

        if overrides:
            app.config.from_mapping(overrides)

        cls.validate_all(app)

    @classmethod
    def public_config_snapshot(cls, config: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            "env_name": cls.get_str(config, "ENV_NAME", cls.ENV_NAME),
            "debug": cls.get_bool(config, "DEBUG", cls.DEBUG),
            "jwt_algorithm": cls.get_str(config, "JWT_ALGORITHM", cls.JWT_ALGORITHM),
            "jwt_active_kid": cls.get_str(config, "JWT_ACTIVE_KID", cls.JWT_ACTIVE_KID),
            "jwt_access_token_expires_minutes": cls.get_int(
                config,
                "JWT_ACCESS_TOKEN_EXPIRES_MINUTES",
                cls.JWT_ACCESS_TOKEN_EXPIRES_MINUTES,
            ),
            "jwt_refresh_token_expires_days": cls.get_int(
                config,
                "JWT_REFRESH_TOKEN_EXPIRES_DAYS",
                cls.JWT_REFRESH_TOKEN_EXPIRES_DAYS,
            ),
            "auth_rate_limit_login_max": cls.get_int(
                config,
                "AUTH_RATE_LIMIT_LOGIN_MAX",
                cls.AUTH_RATE_LIMIT_LOGIN_MAX,
            ),
            "auth_rate_limit_login_window_seconds": cls.get_int(
                config,
                "AUTH_RATE_LIMIT_LOGIN_WINDOW_SECONDS",
                cls.AUTH_RATE_LIMIT_LOGIN_WINDOW_SECONDS,
            ),
            "auth_rate_limit_refresh_max": cls.get_int(
                config,
                "AUTH_RATE_LIMIT_REFRESH_MAX",
                cls.AUTH_RATE_LIMIT_REFRESH_MAX,
            ),
            "auth_rate_limit_refresh_window_seconds": cls.get_int(
                config,
                "AUTH_RATE_LIMIT_REFRESH_WINDOW_SECONDS",
                cls.AUTH_RATE_LIMIT_REFRESH_WINDOW_SECONDS,
            ),
            "auth_rate_limit_logout_max": cls.get_int(
                config,
                "AUTH_RATE_LIMIT_LOGOUT_MAX",
                cls.AUTH_RATE_LIMIT_LOGOUT_MAX,
            ),
            "auth_rate_limit_logout_window_seconds": cls.get_int(
                config,
                "AUTH_RATE_LIMIT_LOGOUT_WINDOW_SECONDS",
                cls.AUTH_RATE_LIMIT_LOGOUT_WINDOW_SECONDS,
            ),
            "resource_rate_limit_max": cls.get_int(
                config,
                "RESOURCE_RATE_LIMIT_MAX",
                cls.RESOURCE_RATE_LIMIT_MAX,
            ),
            "resource_rate_limit_window_seconds": cls.get_int(
                config,
                "RESOURCE_RATE_LIMIT_WINDOW_SECONDS",
                cls.RESOURCE_RATE_LIMIT_WINDOW_SECONDS,
            ),
            "resource_rbac_require_org_role_alignment": cls.get_bool(
                config,
                "RESOURCE_RBAC_REQUIRE_ORG_ROLE_ALIGNMENT",
                cls.RESOURCE_RBAC_REQUIRE_ORG_ROLE_ALIGNMENT,
            ),
            "workflow_strict_review_before_approve": cls.get_bool(
                config,
                "WORKFLOW_STRICT_REVIEW_BEFORE_APPROVE",
                cls.WORKFLOW_STRICT_REVIEW_BEFORE_APPROVE,
            ),
            "enable_audit_logs": cls.get_bool(
                config,
                "ENABLE_AUDIT_LOGS",
                cls.ENABLE_AUDIT_LOGS,
            ),
            "request_id_header": cls.get_str(
                config,
                "REQUEST_ID_HEADER",
                cls.REQUEST_ID_HEADER,
            ),
            "api_version": cls.get_str(
                config,
                "API_VERSION",
                cls.API_VERSION,
            ),
            "audit_log_retention_days": cls.get_int(
                config,
                "AUDIT_LOG_RETENTION_DAYS",
                cls.AUDIT_LOG_RETENTION_DAYS,
            ),
            "jwt_additional_key_ids": sorted(
                list((config.get("JWT_ADDITIONAL_KEYS") or {}).keys())
            ),
            "jwt_secret_configured": bool(config.get("JWT_SECRET_KEY")),
        }


class DevelopmentConfig(BaseConfig):
    """Configuration for local development."""

    DEBUG = True
    ENV_NAME = "development"
    JWT_ACCESS_TOKEN_EXPIRES_MINUTES = 60
    AUTH_RATE_LIMIT_LOGIN_MAX = 20
    AUTH_RATE_LIMIT_REFRESH_MAX = 40
    AUTH_RATE_LIMIT_LOGOUT_MAX = 40


class ProductionConfig(BaseConfig):
    """Configuration for production deployments."""

    DEBUG = False
    ENV_NAME = "production"
    JWT_ACCESS_TOKEN_EXPIRES_MINUTES = 15
    AUTH_RATE_LIMIT_LOGIN_MAX = 8
    AUTH_RATE_LIMIT_REFRESH_MAX = 15
    AUTH_RATE_LIMIT_LOGOUT_MAX = 15
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"


CONFIG_BY_ENV = {
    "dev": DevelopmentConfig,
    "development": DevelopmentConfig,
    "local": DevelopmentConfig,
    "prod": ProductionConfig,
    "production": ProductionConfig,
    "stage": ProductionConfig,
    "staging": ProductionConfig,
    "qa": ProductionConfig,
}


def get_config_class(env_name: Optional[str] = None) -> Type[BaseConfig]:
    resolved_name = env_name or os.getenv(ENV_APP_ENV) or os.getenv(ENV_FLASK_ENV) or "development"
    return CONFIG_BY_ENV.get(resolved_name.strip().lower(), DevelopmentConfig)


def apply_app_config(
    app,
    overrides: Optional[Mapping[str, Any]] = None,
    env_name: Optional[str] = None,
) -> None:
    """Resolve environment class and apply configuration to the app."""
    config_class = get_config_class(env_name=env_name)
    config_class.load_app_config(app, overrides=overrides)
    logger.info("Config loaded: %s", config_class.__name__)
    logger.info("Config snapshot: %s", config_class.public_config_snapshot(app.config))
