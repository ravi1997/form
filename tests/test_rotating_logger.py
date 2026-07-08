"""Unit tests for rotating logger service."""

import pytest
import tempfile
from pathlib import Path
from flask import Flask, g

from app.services.rotating_logger import (
    RotatingLoggerService,
    get_rotating_logger,
    log_request_details,
    log_response_details,
)
from app.middleware.rotating_logger_middleware import setup_rotating_logger_middleware


class TestRotatingLoggerService:
    """Tests for RotatingLoggerService."""

    @pytest.fixture
    def temp_log_dir(self):
        """Create temporary log directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def logger_service(self, temp_log_dir):
        """Create logger service with temp directory."""
        return RotatingLoggerService(
            log_dir=temp_log_dir,
            max_bytes=1024 * 1024,
            backup_count=5,
        )

    def test_logger_initialization(self, logger_service):
        """Test logger service initialization."""
        assert logger_service.log_dir.exists()
        assert logger_service.request_logger is not None
        assert logger_service.response_logger is not None
        assert logger_service.app_logger is not None
        assert logger_service.debug_logger is not None
        assert logger_service.error_logger is not None

    def test_log_request(self, logger_service, temp_log_dir):
        """Test request logging."""
        logger_service.log_request(
            method="POST",
            path="/api/users",
            headers={"Content-Type": "application/json"},
            query_params={"filter": "active"},
            body='{"name": "John"}',
            client_ip="192.168.1.1",
            user_id="user_123",
        )

        # Check if log file exists and contains data
        log_file = Path(temp_log_dir) / "requests.log"
        assert log_file.exists()
        content = log_file.read_text()
        assert "POST" in content
        assert "/api/users" in content
        assert "192.168.1.1" in content
        assert "user_123" in content

    def test_log_request_masks_sensitive_headers(self, logger_service, temp_log_dir):
        """Test that sensitive headers are masked in request logs."""
        logger_service.log_request(
            method="POST",
            path="/api/login",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer token123",
            },
            body='{"password": "secret"}',
        )

        log_file = Path(temp_log_dir) / "requests.log"
        content = log_file.read_text()
        assert "[MASKED]" in content

    def test_log_response(self, logger_service, temp_log_dir):
        """Test response logging."""
        logger_service.log_response(
            status_code=200,
            path="/api/users",
            method="GET",
            headers={"Content-Type": "application/json"},
            body='{"users": []}',
            duration_ms=45.23,
            user_id="user_123",
        )

        log_file = Path(temp_log_dir) / "responses.log"
        assert log_file.exists()
        content = log_file.read_text()
        assert "200" in content
        assert "/api/users" in content
        assert "45.23" in content

    def test_log_response_truncates_large_body(self, logger_service, temp_log_dir):
        """Test that large response bodies are truncated."""
        large_body = "x" * 10000
        logger_service.log_response(
            status_code=200,
            path="/api/data",
            method="GET",
            body=large_body,
        )

        log_file = Path(temp_log_dir) / "responses.log"
        content = log_file.read_text()
        assert "Truncated" in content
        assert "10000" in content

    def test_log_app_event(self, logger_service, temp_log_dir):
        """Test app event logging."""
        logger_service.log_app_event(
            message="User registration completed",
            level="INFO",
            context={"user_id": "user_456", "email": "user@example.com"},
        )

        log_file = Path(temp_log_dir) / "app.log"
        assert log_file.exists()
        content = log_file.read_text()
        assert "User registration" in content
        assert "user_456" in content

    def test_log_debug(self, logger_service, temp_log_dir):
        """Test debug logging."""
        logger_service.log_debug(
            message="Debugging user authentication",
            context={"user_id": "user_789", "auth_method": "oauth"},
        )

        log_file = Path(temp_log_dir) / "debug.log"
        assert log_file.exists()
        content = log_file.read_text()
        assert "Debugging" in content or "user_789" in content

    def test_log_error(self, logger_service, temp_log_dir):
        """Test error logging."""
        try:
            raise ValueError("Test error")
        except Exception as e:
            logger_service.log_error(
                message="Operation failed",
                exception=e,
                context={"operation": "database_query"},
                user_id="user_123",
            )

        log_file = Path(temp_log_dir) / "errors.log"
        assert log_file.exists()
        content = log_file.read_text()
        assert "Operation failed" in content
        assert "ValueError" in content or "Test error" in content

    def test_get_log_files(self, logger_service):
        """Test getting log file paths."""
        log_files = logger_service.get_log_files()

        assert "request" in log_files
        assert "response" in log_files
        assert "app" in log_files
        assert "debug" in log_files
        assert "error" in log_files

    def test_get_log_size(self, logger_service, temp_log_dir):
        """Test getting log file size."""
        logger_service.log_request(
            method="GET",
            path="/api/test",
        )

        size = logger_service.get_log_size("request")
        assert size > 0

    def test_get_log_stats(self, logger_service, temp_log_dir):
        """Test getting log statistics."""
        # Log some data
        logger_service.log_app_event("Test event", level="INFO")

        stats = logger_service.get_log_stats()

        assert "request" in stats
        assert "response" in stats
        assert "app" in stats
        assert "debug" in stats
        assert "error" in stats

        # Check app log stats
        app_stats = stats["app"]
        assert "file" in app_stats
        assert "size_bytes" in app_stats
        assert "size_mb" in app_stats
        assert "last_modified" in app_stats


class TestRotatingLoggerMiddleware:
    """Tests for middleware integration."""

    @pytest.fixture
    def app_with_logger(self):
        """Create simple Flask app with logger middleware."""
        app = Flask(__name__)
        app.config["TESTING"] = True

        with tempfile.TemporaryDirectory() as tmpdir:
            setup_rotating_logger_middleware(app, log_dir=tmpdir)

            @app.route("/api/test", methods=["GET", "POST"])
            def test_endpoint():
                return {"success": True}, 200

            @app.route("/api/error", methods=["GET"])
            def error_endpoint():
                raise ValueError("Test error")

            yield app.test_client(), tmpdir

    def test_request_logging_middleware(self, app_with_logger):
        """Test request logging via middleware."""
        client, tmpdir = app_with_logger
        response = client.get("/api/test")

        assert response.status_code == 200
        log_file = Path(tmpdir) / "requests.log"
        assert log_file.exists()

    def test_response_logging_middleware(self, app_with_logger):
        """Test response logging via middleware."""
        client, tmpdir = app_with_logger
        response = client.get("/api/test")

        assert response.status_code == 200
        log_file = Path(tmpdir) / "responses.log"
        assert log_file.exists()

    def test_error_logging_middleware(self, app_with_logger):
        """Test error logging via middleware."""
        client, tmpdir = app_with_logger
        response = client.get("/api/error")

        assert response.status_code == 500

    def test_post_request_logging(self, app_with_logger):
        """Test POST request logging."""
        client, tmpdir = app_with_logger
        response = client.post(
            "/api/test",
            json={"data": "test"},
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 200
        log_file = Path(tmpdir) / "requests.log"
        assert log_file.exists()


class TestLogRequestResponseFunctions:
    """Tests for helper functions."""

    def test_log_request_details(self):
        """Test log_request_details function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            get_rotating_logger(log_dir=tmpdir)

            app = Flask(__name__)
            with app.test_request_context(
                "/api/test?param=value",
                method="POST",
                json={"data": "test"},
                headers={"Content-Type": "application/json"},
            ):
                g.request_id = "req-123"
                g.user_id = "user_123"
                log_request_details()

            log_file = Path(tmpdir) / "requests.log"
            assert log_file.exists()
            content = log_file.read_text()
            assert "POST" in content

    def test_log_response_details(self):
        """Test log_response_details function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            get_rotating_logger(log_dir=tmpdir)

            app = Flask(__name__)
            with app.test_request_context("/api/test", method="GET"):
                g.request_id = "req-123"
                g.user_id = "user_123"
                log_response_details(
                    status_code=200,
                    body='{"success": true}',
                    duration_ms=45.5,
                )

            log_file = Path(tmpdir) / "responses.log"
            assert log_file.exists()
            content = log_file.read_text()
            assert "200" in content
