from __future__ import annotations

import logging
import os
import warnings
from typing import Any, Dict, Mapping, Optional, Type


logger = logging.getLogger(__name__)


ENV_APP_ENV = "APP_ENV"
ENV_FLASK_ENV = "FLASK_ENV"

ENV_JWT_SECRET_KEY = "JWT_SECRET_KEY"
ENV_JWT_ALGORITHM = "JWT_ALGORITHM"
ENV_JWT_ACCESS_TOKEN_EXPIRES_MINUTES = "JWT_ACCESS_TOKEN_EXPIRES_MINUTES"
ENV_JWT_REFRESH_TOKEN_EXPIRES_DAYS = "JWT_REFRESH_TOKEN_EXPIRES_DAYS"

ENV_AUTH_RATE_LIMIT_LOGIN_MAX = "AUTH_RATE_LIMIT_LOGIN_MAX"
ENV_AUTH_RATE_LIMIT_LOGIN_WINDOW_SECONDS = "AUTH_RATE_LIMIT_LOGIN_WINDOW_SECONDS"
ENV_AUTH_RATE_LIMIT_REFRESH_MAX = "AUTH_RATE_LIMIT_REFRESH_MAX"
ENV_AUTH_RATE_LIMIT_REFRESH_WINDOW_SECONDS = "AUTH_RATE_LIMIT_REFRESH_WINDOW_SECONDS"
ENV_AUTH_RATE_LIMIT_LOGOUT_MAX = "AUTH_RATE_LIMIT_LOGOUT_MAX"
ENV_AUTH_RATE_LIMIT_LOGOUT_WINDOW_SECONDS = "AUTH_RATE_LIMIT_LOGOUT_WINDOW_SECONDS"
ENV_ENABLE_AUDIT_LOGS = "ENABLE_AUDIT_LOGS"


KNOWN_ENV_KEYS = {
    ENV_APP_ENV,
    ENV_FLASK_ENV,
    ENV_JWT_SECRET_KEY,
    ENV_JWT_ALGORITHM,
    ENV_JWT_ACCESS_TOKEN_EXPIRES_MINUTES,
    ENV_JWT_REFRESH_TOKEN_EXPIRES_DAYS,
    ENV_AUTH_RATE_LIMIT_LOGIN_MAX,
    ENV_AUTH_RATE_LIMIT_LOGIN_WINDOW_SECONDS,
    ENV_AUTH_RATE_LIMIT_REFRESH_MAX,
    ENV_AUTH_RATE_LIMIT_REFRESH_WINDOW_SECONDS,
    ENV_AUTH_RATE_LIMIT_LOGOUT_MAX,
    ENV_AUTH_RATE_LIMIT_LOGOUT_WINDOW_SECONDS,
    ENV_ENABLE_AUDIT_LOGS,
}


class BaseConfig:
    """Base app configuration shared by all environments."""

    DEBUG = False
    TESTING = False
    ENV_NAME = "base"

    JWT_ALGORITHM = "HS256"
    JWT_ACCESS_TOKEN_EXPIRES_MINUTES = 30
    JWT_REFRESH_TOKEN_EXPIRES_DAYS = 7

    AUTH_RATE_LIMIT_LOGIN_MAX = 10
    AUTH_RATE_LIMIT_LOGIN_WINDOW_SECONDS = 60
    AUTH_RATE_LIMIT_REFRESH_MAX = 20
    AUTH_RATE_LIMIT_REFRESH_WINDOW_SECONDS = 60
    AUTH_RATE_LIMIT_LOGOUT_MAX = 20
    AUTH_RATE_LIMIT_LOGOUT_WINDOW_SECONDS = 60
    ENABLE_AUDIT_LOGS = True

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
            "ENABLE_AUDIT_LOGS": cls._env_bool(
                ENV_ENABLE_AUDIT_LOGS,
                cls.ENABLE_AUDIT_LOGS,
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

        if cls.ENV_NAME == "production" and not app.config.get("JWT_SECRET_KEY"):
            raise RuntimeError("JWT_SECRET_KEY is required in production")

        if cls.ENV_NAME != "production" and not app.config.get("JWT_SECRET_KEY"):
            app.config["JWT_SECRET_KEY"] = "dev-insecure-secret-change-me"
            cls._warn_or_raise(
                "JWT_SECRET_KEY not set; using development fallback secret. "
                "Set JWT_SECRET_KEY for secure environments."
            )

    @classmethod
    def load_app_config(cls, app, overrides: Optional[Mapping[str, Any]] = None) -> None:
        app.config.from_object(cls)
        app.config.update(cls.build_config_from_env())

        if overrides:
            app.config.from_mapping(overrides)

        cls.validate_all(app)


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
