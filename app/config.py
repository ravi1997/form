"""Application configuration.

Provides environment-specific config classes (BaseConfig, DevelopmentConfig,
ProductionConfig), env-var parsing helpers, startup validation, and the
RuntimeSettings Pydantic model used by the app factory.

Environment selection is driven by the APP_ENV (or FLASK_ENV) variable.
All supported keys are listed in KNOWN_ENV_KEYS; unknown JWT_*/AUTH_RATE_LIMIT_*
variables produce a warning (or raise in production) to catch typos early.
"""

from __future__ import annotations

import logging
import json
import os
import warnings
from typing import Any, Dict, Mapping, Optional, Type

from pydantic import BaseModel, Field, ValidationError as PydanticValidationError
from pymongo.uri_parser import parse_uri

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
ENV_RESOURCE_RBAC_REQUIRE_ORG_ROLE_ALIGNMENT = (
    "RESOURCE_RBAC_REQUIRE_ORG_ROLE_ALIGNMENT"
)
ENV_WORKFLOW_STRICT_REVIEW_BEFORE_APPROVE = "WORKFLOW_STRICT_REVIEW_BEFORE_APPROVE"
ENV_ENABLE_AUDIT_LOGS = "ENABLE_AUDIT_LOGS"
ENV_REQUEST_ID_HEADER = "REQUEST_ID_HEADER"
ENV_API_VERSION = "API_VERSION"
ENV_AUDIT_LOG_RETENTION_DAYS = "AUDIT_LOG_RETENTION_DAYS"
ENV_MONITORING_STATS_RETENTION_DAYS = "MONITORING_STATS_RETENTION_DAYS"
ENV_MAX_PASSWORD_EXPIRE_DAYS = "MAX_PASSWORD_EXPIRE_DAYS"
ENV_MONGODB_URI = "MONGODB_URI"
ENV_MONGODB_DB = "MONGODB_DB"
ENV_MONGODB_CONNECT_TIMEOUT_MS = "MONGODB_CONNECT_TIMEOUT_MS"
ENV_CELERY_BROKER_URL = "CELERY_BROKER_URL"
ENV_CELERY_RESULT_BACKEND = "CELERY_RESULT_BACKEND"
ENV_REDIS_URL = "REDIS_URL"
ENV_CELERY_TASK_DEFAULT_QUEUE = "CELERY_TASK_DEFAULT_QUEUE"
ENV_CELERY_TASK_TIME_LIMIT = "CELERY_TASK_TIME_LIMIT"
ENV_CELERY_TASK_SOFT_TIME_LIMIT = "CELERY_TASK_SOFT_TIME_LIMIT"
ENV_CELERY_TASK_ALWAYS_EAGER = "CELERY_TASK_ALWAYS_EAGER"
ENV_CELERY_TASK_EAGER_PROPAGATES = "CELERY_TASK_EAGER_PROPAGATES"
ENV_LOG_LEVEL = "LOG_LEVEL"
ENV_LOG_DIR = "LOG_DIR"
ENV_LOG_MAX_BYTES = "LOG_MAX_BYTES"
ENV_LOG_BACKUP_COUNT = "LOG_BACKUP_COUNT"
ENV_CORS_ALLOW_ORIGINS = "CORS_ALLOW_ORIGINS"
ENV_ENABLE_COMPRESSION = "ENABLE_COMPRESSION"
ENV_PUBLIC_BASE_URL = "PUBLIC_BASE_URL"
ENV_FRONTEND_URL = "FRONTEND_URL"


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
    ENV_MONITORING_STATS_RETENTION_DAYS,
    ENV_MAX_PASSWORD_EXPIRE_DAYS,
    ENV_MONGODB_URI,
    ENV_MONGODB_DB,
    ENV_MONGODB_CONNECT_TIMEOUT_MS,
    ENV_CELERY_BROKER_URL,
    ENV_CELERY_RESULT_BACKEND,
    ENV_REDIS_URL,
    ENV_CELERY_TASK_DEFAULT_QUEUE,
    ENV_CELERY_TASK_TIME_LIMIT,
    ENV_CELERY_TASK_SOFT_TIME_LIMIT,
    ENV_CELERY_TASK_ALWAYS_EAGER,
    ENV_CELERY_TASK_EAGER_PROPAGATES,
    ENV_LOG_LEVEL,
    ENV_LOG_DIR,
    ENV_LOG_MAX_BYTES,
    ENV_LOG_BACKUP_COUNT,
    ENV_CORS_ALLOW_ORIGINS,
    ENV_ENABLE_COMPRESSION,
    ENV_PUBLIC_BASE_URL,
    ENV_FRONTEND_URL,
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
    MONITORING_STATS_RETENTION_DAYS = 30
    MAX_PASSWORD_EXPIRE_DAYS = 90
    MONGODB_URI = "mongodb://localhost:27017/form_dev"
    MONGODB_DB = "form_dev"
    MONGODB_CONNECT_TIMEOUT_MS = 2000
    CELERY_BROKER_URL = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND = "redis://localhost:6379/1"
    REDIS_URL = "redis://localhost:6379/0"
    CELERY_TASK_DEFAULT_QUEUE = "form_tasks"
    CELERY_TASK_TIME_LIMIT = 300
    CELERY_TASK_SOFT_TIME_LIMIT = 240
    CELERY_TASK_ALWAYS_EAGER = False
    CELERY_TASK_EAGER_PROPAGATES = False
    LOG_LEVEL = "INFO"
    LOG_DIR = "logs"
    LOG_MAX_BYTES = 10 * 1024 * 1024
    LOG_BACKUP_COUNT = 10
    CORS_ALLOW_ORIGINS: list[str] = []
    ENABLE_COMPRESSION = True
    PUBLIC_BASE_URL = ""
    FRONTEND_URL = ""

    ALLOWED_JWT_ALGORITHMS = {"HS256"}
    ALLOWED_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
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
        "MONITORING_STATS_RETENTION_DAYS",
        "MAX_PASSWORD_EXPIRE_DAYS",
        "MONGODB_CONNECT_TIMEOUT_MS",
        "CELERY_TASK_TIME_LIMIT",
        "CELERY_TASK_SOFT_TIME_LIMIT",
        "LOG_MAX_BYTES",
        "LOG_BACKUP_COUNT",
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
        "MONITORING_STATS_RETENTION_DAYS": (1, 3650),
        "MAX_PASSWORD_EXPIRE_DAYS": (1, 3650),
        "MONGODB_CONNECT_TIMEOUT_MS": (100, 120000),
        "CELERY_TASK_TIME_LIMIT": (1, 3600),
        "CELERY_TASK_SOFT_TIME_LIMIT": (1, 3600),
        "LOG_MAX_BYTES": (1024, 1024 * 1024 * 1024),
        "LOG_BACKUP_COUNT": (1, 1000),
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
    def _env_key_map(
        name: str, default: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        raw = os.getenv(name)
        if raw is None or raw.strip() == "":
            return dict(default or {})

        raw = raw.strip()
        if raw.startswith("{"):
            try:
                parsed_mapping = json.loads(raw)
            except ValueError as exc:
                raise RuntimeError(
                    f"{name} must be valid JSON or 'kid:secret' pairs"
                ) from exc
            if not isinstance(parsed_mapping, dict):
                raise RuntimeError(
                    f"{name} must be a mapping of kid to secret metadata"
                )
            return parsed_mapping

        items = [item.strip() for item in raw.split(",") if item.strip()]
        parsed: Dict[str, Any] = {}
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
    def _env_csv(name: str, default: Optional[list[str]] = None) -> list[str]:
        raw = os.getenv(name)
        if raw is None or raw.strip() == "":
            return list(default or [])
        return [item.strip() for item in raw.split(",") if item.strip()]

    @staticmethod
    def _mongodb_settings_from_uri(uri: str) -> Dict[str, Any]:
        settings: Dict[str, Any] = {"host": uri}
        try:
            parsed = parse_uri(uri)
        except Exception:
            return settings

        options = parsed.get("options") or {}
        nodelist = parsed.get("nodelist") or []
        if nodelist:
            hosts = ",".join(f"{host}:{port}" for host, port in nodelist)
            database = parsed.get("database")
            query_parts = []
            auth_source = options.get("authsource") or options.get("authSource")
            if auth_source:
                query_parts.append(f"authSource={auth_source}")
            auth_mechanism = options.get("authmechanism") or options.get(
                "authMechanism"
            )
            if auth_mechanism:
                query_parts.append(f"authMechanism={auth_mechanism}")
            query = f"?{'&'.join(query_parts)}" if query_parts else ""
            settings["host"] = f"mongodb://{hosts}"
            if database:
                settings["host"] = f"{settings['host']}/{database}"
            settings["host"] = f"{settings['host']}{query}"
        if parsed.get("username"):
            settings["username"] = parsed["username"]
        if parsed.get("password"):
            settings["password"] = parsed["password"]
        auth_source = options.get("authsource") or options.get("authSource")
        if auth_source:
            settings["authentication_source"] = auth_source
        auth_mechanism = options.get("authmechanism") or options.get("authMechanism")
        if auth_mechanism:
            settings["authentication_mechanism"] = auth_mechanism
        settings.setdefault("uuidRepresentation", "standard")

        return settings

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
        raise RuntimeError(
            f"{name} must be a boolean (true/false, 1/0, yes/no, on/off)"
        )

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
            "MONITORING_STATS_RETENTION_DAYS": cls._env_int(
                ENV_MONITORING_STATS_RETENTION_DAYS,
                cls.MONITORING_STATS_RETENTION_DAYS,
            ),
            "MONGODB_URI": cls._env_str(ENV_MONGODB_URI, cls.MONGODB_URI),
            "MONGODB_DB": cls._env_str(ENV_MONGODB_DB, cls.MONGODB_DB),
            "MONGODB_CONNECT_TIMEOUT_MS": cls._env_int(
                ENV_MONGODB_CONNECT_TIMEOUT_MS,
                cls.MONGODB_CONNECT_TIMEOUT_MS,
            ),
            "CELERY_BROKER_URL": cls._env_str(
                ENV_CELERY_BROKER_URL,
                cls.CELERY_BROKER_URL,
            ),
            "CELERY_RESULT_BACKEND": cls._env_str(
                ENV_CELERY_RESULT_BACKEND,
                cls.CELERY_RESULT_BACKEND,
            ),
            "REDIS_URL": cls._env_str(
                ENV_REDIS_URL,
                cls._env_str(ENV_CELERY_BROKER_URL, cls.CELERY_BROKER_URL),
            ),
            "CELERY_TASK_DEFAULT_QUEUE": cls._env_str(
                ENV_CELERY_TASK_DEFAULT_QUEUE,
                cls.CELERY_TASK_DEFAULT_QUEUE,
            ),
            "CELERY_TASK_TIME_LIMIT": cls._env_int(
                ENV_CELERY_TASK_TIME_LIMIT,
                cls.CELERY_TASK_TIME_LIMIT,
            ),
            "CELERY_TASK_SOFT_TIME_LIMIT": cls._env_int(
                ENV_CELERY_TASK_SOFT_TIME_LIMIT,
                cls.CELERY_TASK_SOFT_TIME_LIMIT,
            ),
            "CELERY_TASK_ALWAYS_EAGER": cls._env_bool(
                ENV_CELERY_TASK_ALWAYS_EAGER,
                cls.CELERY_TASK_ALWAYS_EAGER,
            ),
            "CELERY_TASK_EAGER_PROPAGATES": cls._env_bool(
                ENV_CELERY_TASK_EAGER_PROPAGATES,
                cls.CELERY_TASK_EAGER_PROPAGATES,
            ),
            "LOG_LEVEL": cls._env_str(ENV_LOG_LEVEL, cls.LOG_LEVEL),
            "LOG_DIR": cls._env_str(ENV_LOG_DIR, cls.LOG_DIR),
            "LOG_MAX_BYTES": cls._env_int(ENV_LOG_MAX_BYTES, cls.LOG_MAX_BYTES),
            "LOG_BACKUP_COUNT": cls._env_int(
                ENV_LOG_BACKUP_COUNT,
                cls.LOG_BACKUP_COUNT,
            ),
            "CORS_ALLOW_ORIGINS": cls._env_csv(
                ENV_CORS_ALLOW_ORIGINS,
                cls.CORS_ALLOW_ORIGINS,
            ),
            "ENABLE_COMPRESSION": cls._env_bool(
                ENV_ENABLE_COMPRESSION,
                cls.ENABLE_COMPRESSION,
            ),
            "PUBLIC_BASE_URL": cls._env_str(
                ENV_PUBLIC_BASE_URL,
                cls.PUBLIC_BASE_URL,
            ),
            "FRONTEND_URL": cls._env_str(
                ENV_FRONTEND_URL,
                cls.FRONTEND_URL,
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
        log_level = cls.get_str(app.config, "LOG_LEVEL", cls.LOG_LEVEL).upper()
        if log_level not in cls.ALLOWED_LOG_LEVELS:
            raise RuntimeError(
                f"LOG_LEVEL must be one of {sorted(cls.ALLOWED_LOG_LEVELS)}"
            )

        for key in cls.REQUIRED_POSITIVE_INT_KEYS:
            value = cls.get_int(app.config, key, 0)
            if value <= 0:
                raise RuntimeError(f"{key} must be a positive integer")

            lower, upper = cls.INT_BOUNDS[key]
            if value < lower or value > upper:
                raise RuntimeError(f"{key} must be between {lower} and {upper}")

        soft_time_limit = cls.get_int(
            app.config,
            "CELERY_TASK_SOFT_TIME_LIMIT",
            cls.CELERY_TASK_SOFT_TIME_LIMIT,
        )
        task_time_limit = cls.get_int(
            app.config,
            "CELERY_TASK_TIME_LIMIT",
            cls.CELERY_TASK_TIME_LIMIT,
        )
        if soft_time_limit >= task_time_limit:
            raise RuntimeError(
                "CELERY_TASK_SOFT_TIME_LIMIT must be less than CELERY_TASK_TIME_LIMIT"
            )

        cls.get_bool(app.config, "ENABLE_AUDIT_LOGS", cls.ENABLE_AUDIT_LOGS)
        api_version = cls.get_str(app.config, "API_VERSION", cls.API_VERSION)
        if not api_version.startswith("v") or not api_version[1:].isdigit():
            raise RuntimeError("API_VERSION must use format v<integer>, for example v1")

        redis_url = cls.get_str(app.config, "REDIS_URL", cls.REDIS_URL)
        app.config["REDIS_URL"] = redis_url
        if cls.ENV_NAME == "production" and not redis_url:
            raise RuntimeError("REDIS_URL is required in production for rate limiting")

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
        has_mongodb_uri = bool(app.config.get("MONGODB_URI"))
        has_mongodb_settings = isinstance(app.config.get("MONGODB_SETTINGS"), dict)
        if cls.ENV_NAME == "production" and not (
            has_mongodb_uri or has_mongodb_settings
        ):
            raise RuntimeError(
                "MONGODB_URI or MONGODB_SETTINGS is required in production"
            )

        if cls.ENV_NAME != "production" and not app.config.get("JWT_SECRET_KEY"):
            app.config["JWT_SECRET_KEY"] = "dev-insecure-secret-change-me"
            cls._warn_or_raise(
                "JWT_SECRET_KEY not set; using development fallback secret. "
                "Set JWT_SECRET_KEY for secure environments."
            )

        if active_kid in additional_keys and app.config.get(
            "JWT_SECRET_KEY"
        ) == additional_keys.get(active_kid):
            cls._warn_or_raise(
                "JWT_ACTIVE_KID should point to the primary JWT_SECRET_KEY, "
                "not a duplicated key in JWT_ADDITIONAL_KEYS."
            )
        app.config["LOG_LEVEL"] = log_level
        existing_settings = app.config.get("MONGODB_SETTINGS")
        if isinstance(existing_settings, dict):
            merged_settings = dict(existing_settings)
            mongodb_uri = cls.get_str(app.config, "MONGODB_URI", cls.MONGODB_URI)
            merged_settings.setdefault("host", mongodb_uri)
            merged_settings.setdefault(
                "db", cls.get_str(app.config, "MONGODB_DB", cls.MONGODB_DB)
            )
            merged_settings.setdefault(
                "connectTimeoutMS",
                cls.get_int(
                    app.config,
                    "MONGODB_CONNECT_TIMEOUT_MS",
                    cls.MONGODB_CONNECT_TIMEOUT_MS,
                ),
            )
            merged_settings.setdefault(
                "serverSelectionTimeoutMS",
                cls.get_int(
                    app.config,
                    "MONGODB_CONNECT_TIMEOUT_MS",
                    cls.MONGODB_CONNECT_TIMEOUT_MS,
                ),
            )
            merged_settings.setdefault("alias", "default")
            merged_settings.update(cls._mongodb_settings_from_uri(mongodb_uri))
            app.config["MONGODB_SETTINGS"] = merged_settings
        else:
            mongodb_uri = cls.get_str(app.config, "MONGODB_URI", cls.MONGODB_URI)
            app.config["MONGODB_SETTINGS"] = {
                "host": mongodb_uri,
                "db": cls.get_str(app.config, "MONGODB_DB", cls.MONGODB_DB),
                "connectTimeoutMS": cls.get_int(
                    app.config,
                    "MONGODB_CONNECT_TIMEOUT_MS",
                    cls.MONGODB_CONNECT_TIMEOUT_MS,
                ),
                "serverSelectionTimeoutMS": cls.get_int(
                    app.config,
                    "MONGODB_CONNECT_TIMEOUT_MS",
                    cls.MONGODB_CONNECT_TIMEOUT_MS,
                ),
                "alias": "default",
                "uuidRepresentation": "standard",
            }
            app.config["MONGODB_SETTINGS"].update(
                cls._mongodb_settings_from_uri(mongodb_uri)
            )

    @classmethod
    def load_app_config(
        cls, app, overrides: Optional[Mapping[str, Any]] = None
    ) -> None:
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
            "monitoring_stats_retention_days": cls.get_int(
                config,
                "MONITORING_STATS_RETENTION_DAYS",
                cls.MONITORING_STATS_RETENTION_DAYS,
            ),
            "mongodb_db": cls.get_str(config, "MONGODB_DB", cls.MONGODB_DB),
            "mongodb_uri_configured": bool(config.get("MONGODB_URI")),
            "celery_broker_url_configured": bool(config.get("CELERY_BROKER_URL")),
            "celery_result_backend_configured": bool(
                config.get("CELERY_RESULT_BACKEND")
            ),
            "celery_task_default_queue": cls.get_str(
                config,
                "CELERY_TASK_DEFAULT_QUEUE",
                cls.CELERY_TASK_DEFAULT_QUEUE,
            ),
            "celery_task_time_limit": cls.get_int(
                config,
                "CELERY_TASK_TIME_LIMIT",
                cls.CELERY_TASK_TIME_LIMIT,
            ),
            "celery_task_soft_time_limit": cls.get_int(
                config,
                "CELERY_TASK_SOFT_TIME_LIMIT",
                cls.CELERY_TASK_SOFT_TIME_LIMIT,
            ),
            "log_level": cls.get_str(config, "LOG_LEVEL", cls.LOG_LEVEL),
            "log_dir": cls.get_str(config, "LOG_DIR", cls.LOG_DIR),
            "log_max_bytes": cls.get_int(
                config,
                "LOG_MAX_BYTES",
                cls.LOG_MAX_BYTES,
            ),
            "log_backup_count": cls.get_int(
                config,
                "LOG_BACKUP_COUNT",
                cls.LOG_BACKUP_COUNT,
            ),
            "cors_allow_origins": list(config.get("CORS_ALLOW_ORIGINS") or []),
            "enable_compression": cls.get_bool(
                config,
                "ENABLE_COMPRESSION",
                cls.ENABLE_COMPRESSION,
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
    MONGODB_DB = "form_dev"


class ProductionConfig(BaseConfig):
    """Configuration for production deployments."""

    DEBUG = False
    ENV_NAME = "production"
    JWT_ACCESS_TOKEN_EXPIRES_MINUTES = 15
    AUTH_RATE_LIMIT_LOGIN_MAX = 8
    AUTH_RATE_LIMIT_REFRESH_MAX = 15
    AUTH_RATE_LIMIT_LOGOUT_MAX = 15
    MONGODB_DB = "form_prod"
    LOG_LEVEL = "INFO"
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
    resolved_name = (
        env_name or os.getenv(ENV_APP_ENV) or os.getenv(ENV_FLASK_ENV) or "development"
    )
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


class RuntimeSettings(BaseModel):
    env_name: str = Field(default=BaseConfig.ENV_NAME)
    debug: bool = Field(default=BaseConfig.DEBUG)
    api_version: str = Field(default=BaseConfig.API_VERSION)
    log_level: str = Field(default=BaseConfig.LOG_LEVEL)
    log_dir: str = Field(default=BaseConfig.LOG_DIR)
    log_max_bytes: int = Field(default=BaseConfig.LOG_MAX_BYTES, ge=1024)
    log_backup_count: int = Field(default=BaseConfig.LOG_BACKUP_COUNT, ge=1)
    mongodb_uri: str = Field(default=BaseConfig.MONGODB_URI)
    mongodb_db: str = Field(default=BaseConfig.MONGODB_DB)
    redis_url: str = Field(default=BaseConfig.REDIS_URL)
    mongodb_connect_timeout_ms: int = Field(
        default=BaseConfig.MONGODB_CONNECT_TIMEOUT_MS,
        ge=100,
    )
    monitoring_stats_retention_days: int = Field(
        default=BaseConfig.MONITORING_STATS_RETENTION_DAYS,
        ge=1,
    )
    request_id_header: str = Field(default=BaseConfig.REQUEST_ID_HEADER)
    cors_allow_origins: list[str] = Field(default_factory=list)
    enable_compression: bool = Field(default=BaseConfig.ENABLE_COMPRESSION)


def build_runtime_settings(config: Mapping[str, Any]) -> RuntimeSettings:
    data = {
        "env_name": BaseConfig.get_str(config, "ENV_NAME", BaseConfig.ENV_NAME),
        "debug": BaseConfig.get_bool(config, "DEBUG", BaseConfig.DEBUG),
        "api_version": BaseConfig.get_str(
            config, "API_VERSION", BaseConfig.API_VERSION
        ),
        "log_level": BaseConfig.get_str(config, "LOG_LEVEL", BaseConfig.LOG_LEVEL),
        "log_dir": BaseConfig.get_str(config, "LOG_DIR", BaseConfig.LOG_DIR),
        "log_max_bytes": BaseConfig.get_int(
            config, "LOG_MAX_BYTES", BaseConfig.LOG_MAX_BYTES
        ),
        "log_backup_count": BaseConfig.get_int(
            config, "LOG_BACKUP_COUNT", BaseConfig.LOG_BACKUP_COUNT
        ),
        "mongodb_uri": BaseConfig.get_str(
            config, "MONGODB_URI", BaseConfig.MONGODB_URI
        ),
        "mongodb_db": BaseConfig.get_str(config, "MONGODB_DB", BaseConfig.MONGODB_DB),
        "redis_url": BaseConfig.get_str(config, "REDIS_URL", BaseConfig.REDIS_URL),
        "mongodb_connect_timeout_ms": BaseConfig.get_int(
            config,
            "MONGODB_CONNECT_TIMEOUT_MS",
            BaseConfig.MONGODB_CONNECT_TIMEOUT_MS,
        ),
        "monitoring_stats_retention_days": BaseConfig.get_int(
            config,
            "MONITORING_STATS_RETENTION_DAYS",
            BaseConfig.MONITORING_STATS_RETENTION_DAYS,
        ),
        "request_id_header": BaseConfig.get_str(
            config, "REQUEST_ID_HEADER", BaseConfig.REQUEST_ID_HEADER
        ),
        "cors_allow_origins": list(config.get("CORS_ALLOW_ORIGINS") or []),
        "enable_compression": BaseConfig.get_bool(
            config, "ENABLE_COMPRESSION", BaseConfig.ENABLE_COMPRESSION
        ),
    }
    try:
        return RuntimeSettings.model_validate(data)
    except PydanticValidationError as exc:
        raise RuntimeError(f"Invalid runtime settings: {exc}") from exc
