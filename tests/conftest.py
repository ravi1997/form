"""
Pytest configuration and shared fixtures for all tests.
"""
import os
import sys
import pytest
from datetime import datetime, timedelta, timezone
from flask import Flask

# Handle mongomock and MongoEngine setup
try:
    from mongomock import MongoClient
except ImportError:
    pass

# Try to import MongoEngine
try:
    from flask_mongoengine import MongoEngine
    from app.extensions import db
    from app.config import DevelopmentConfig
    HAS_MONGOENGINE = True
except ImportError as e:
    HAS_MONGOENGINE = False
    print(f"Warning: MongoEngine import failed: {e}")


@pytest.fixture(scope="session")
def app():
    """Create application for testing."""
    if not HAS_MONGOENGINE:
        pytest.skip("MongoEngine not available")
    
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["MONGODB_SETTINGS"] = {
        "db": "test_form_db",
        "host": "mongomock://localhost",
        "connect": False,
    }
    app.config["JWT_SECRET_KEY"] = "test-secret-key-do-not-use-in-production"
    app.config["JWT_ALGORITHM"] = "HS256"
    app.config["JWT_ACCESS_TOKEN_EXPIRES_MINUTES"] = 30
    app.config["JWT_REFRESH_TOKEN_EXPIRES_DAYS"] = 7
    app.config["AUTH_RATE_LIMIT_LOGIN_MAX"] = 10
    app.config["AUTH_RATE_LIMIT_LOGIN_WINDOW_SECONDS"] = 60
    app.config["AUTH_RATE_LIMIT_REFRESH_MAX"] = 20
    app.config["AUTH_RATE_LIMIT_REFRESH_WINDOW_SECONDS"] = 60
    app.config["AUTH_RATE_LIMIT_LOGOUT_MAX"] = 20
    app.config["AUTH_RATE_LIMIT_LOGOUT_WINDOW_SECONDS"] = 60
    
    db.init_app(app)
    
    with app.app_context():
        yield app


@pytest.fixture(autouse=True)
def cleanup_db(app):
    """Clean up database before each test."""
    with app.app_context():
        db.connection.drop_database("test_form_db")
        yield
        db.connection.drop_database("test_form_db")


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
