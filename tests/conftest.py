"""
Pytest configuration and shared fixtures for all tests.
"""

import pytest
from datetime import datetime, timedelta, timezone
from mongoengine.connection import get_connection
from app.models.auth import (
    RateLimitCounter,
    SessionAuditLog,
    TokenBlocklist,
    UserSession,
)
from app.models.form import Condition, Form, FormResponse, Project, Question, Section
from app.models.condition_management import (
    ConditionApprovalAudit,
    ConditionAsyncJob,
    ConditionEvaluationStat,
    ConditionPreset,
    ConditionVersion,
)
from app.models.user import Organization, User

# Handle mongomock and MongoEngine setup
try:
    from mongomock import MongoClient

    HAS_MONGOMOCK = True
except ImportError:
    HAS_MONGOMOCK = False

# Try to import MongoEngine
try:
    from app import create_openapi_app

    HAS_MONGOENGINE = True
except ImportError as e:
    HAS_MONGOENGINE = False
    print(f"Warning: MongoEngine import failed: {e}")


def _drop_test_database() -> None:
    connection = get_connection()
    active_db_name = connection.get_default_database().name
    connection.drop_database(active_db_name)


def _ensure_test_indexes() -> None:
    for document in (
        User,
        Organization,
        Condition,
        Form,
        Project,
        Section,
        Question,
        FormResponse,
        UserSession,
        RateLimitCounter,
        SessionAuditLog,
        TokenBlocklist,
        ConditionPreset,
        ConditionVersion,
        ConditionApprovalAudit,
        ConditionAsyncJob,
        ConditionEvaluationStat,
    ):
        document.ensure_indexes()


@pytest.fixture(scope="session")
def app():
    """Create application for testing."""
    if not HAS_MONGOENGINE:
        pytest.skip("MongoEngine not available")
    if not HAS_MONGOMOCK:
        pytest.skip("mongomock not available")

    db_name = "test_form_db"
    app = create_openapi_app(
        {
            "TESTING": True,
            "MONGODB_SETTINGS": {
                "db": db_name,
                "host": f"mongodb://localhost/{db_name}",
                "mongo_client_class": MongoClient,
                "connect": False,
                "uuidRepresentation": "standard",
            },
            "JWT_SECRET_KEY": "test-secret-key-do-not-use-in-production",
            "JWT_ALGORITHM": "HS256",
            "JWT_ACCESS_TOKEN_EXPIRES_MINUTES": 30,
            "JWT_REFRESH_TOKEN_EXPIRES_DAYS": 7,
            "AUTH_RATE_LIMIT_LOGIN_MAX": 10,
            "AUTH_RATE_LIMIT_LOGIN_WINDOW_SECONDS": 60,
            "AUTH_RATE_LIMIT_REFRESH_MAX": 20,
            "AUTH_RATE_LIMIT_REFRESH_WINDOW_SECONDS": 60,
            "AUTH_RATE_LIMIT_LOGOUT_MAX": 20,
            "AUTH_RATE_LIMIT_LOGOUT_WINDOW_SECONDS": 60,
            "ENABLE_AUDIT_LOGS": False,
            "CELERY_TASK_ALWAYS_EAGER": True,
            "CELERY_TASK_EAGER_PROPAGATES": True,
            "CELERY_BROKER_URL": "memory://",
            "CELERY_RESULT_BACKEND": "cache+memory://",
        }
    )

    _drop_test_database()
    with app.app_context():
        yield app
    _drop_test_database()


@pytest.fixture(autouse=True)
def cleanup_db(app):
    """Clean up database before each test."""
    with app.app_context():
        _drop_test_database()
        _ensure_test_indexes()
        yield
        _drop_test_database()


@pytest.fixture
def client(app):
    """Test client for making requests."""
    return app.test_client()


@pytest.fixture
def app_context(app):
    """Application context for use in tests."""
    with app.app_context():
        yield app


def utcnow():
    """Get current UTC time."""
    return datetime.now(timezone.utc)


def yesterday():
    """Get yesterday's date."""
    return utcnow() - timedelta(days=1)


def tomorrow():
    """Get tomorrow's date."""
    return utcnow() + timedelta(days=1)


def next_week():
    """Get next week's date."""
    return utcnow() + timedelta(days=7)


def next_month():
    """Get next month's date."""
    return utcnow() + timedelta(days=30)


@pytest.fixture
def jwt_secret(app):
    """Get JWT secret key from app config."""
    with app.app_context():
        return app.config.get("JWT_SECRET_KEY")


@pytest.fixture
def jwt_algorithm(app):
    """Get JWT algorithm from app config."""
    with app.app_context():
        return app.config.get("JWT_ALGORITHM")
