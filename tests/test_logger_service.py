"""Unit tests for the logger service."""

import logging
import json
import pytest
from flask import Flask, g

import app.services.logging.decorators as logging_decorators
from app.services.logger import (
    LoggerService,
    StructuredFormatter,
    get_logger,
    log_request_middleware,
    log_performance,
    log_audit,
)


class TestStructuredFormatter:
    """Tests for StructuredFormatter."""

    def test_format_basic_log_record(self):
        """Test formatting of basic log record."""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test.logger"
        assert parsed["message"] == "Test message"
        assert "timestamp" in parsed

    def test_format_with_extra_context(self):
        """Test formatting with extra context."""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.extra = {"user_id": "user_123", "action": "login"}

        output = formatter.format(record)
        parsed = json.loads(output)

        # Extra fields are merged at root level
        assert parsed.get("user_id") == "user_123"
        assert parsed.get("action") == "login"


class TestLoggerService:
    """Tests for LoggerService class."""

    def test_logger_initialization(self):
        """Test logger initialization."""
        logger_service = LoggerService("test.logger")
        assert logger_service.logger is not None
        assert len(logger_service.logger.handlers) > 0

    def test_debug_logging(self, caplog):
        """Test debug level logging."""
        logger_service = LoggerService("test.logger")
        with caplog.at_level(logging.DEBUG):
            logger_service.debug("Debug message", key="value")

        assert "Debug message" in caplog.text

    def test_info_logging(self, caplog):
        """Test info level logging."""
        logger_service = LoggerService("test.logger")
        with caplog.at_level(logging.INFO):
            logger_service.info("Info message", key="value")

        assert "Info message" in caplog.text

    def test_warning_logging(self, caplog):
        """Test warning level logging."""
        logger_service = LoggerService("test.logger")
        with caplog.at_level(logging.WARNING):
            logger_service.warning("Warning message", key="value")

        assert "Warning message" in caplog.text

    def test_error_logging(self, caplog):
        """Test error level logging."""
        logger_service = LoggerService("test.logger")
        with caplog.at_level(logging.ERROR):
            logger_service.error("Error message", key="value")

        assert "Error message" in caplog.text

    def test_critical_logging(self, caplog):
        """Test critical level logging."""
        logger_service = LoggerService("test.logger")
        with caplog.at_level(logging.CRITICAL):
            logger_service.critical("Critical message", key="value")

        assert "Critical message" in caplog.text

    def test_log_with_context(self, caplog):
        """Test logging with context dictionary."""
        logger_service = LoggerService("test.logger")
        with caplog.at_level(logging.INFO):
            logger_service.log_with_context(
                logging.INFO,
                "Test message",
                extra={"user_id": "user_123", "action": "created"},
            )

        assert "Test message" in caplog.text

    def test_log_request(self, caplog):
        """Test API request logging."""
        logger_service = LoggerService("test.logger")
        with caplog.at_level(logging.INFO):
            logger_service.log_request(
                method="POST",
                path="/api/users",
                status_code=201,
                duration_ms=45.23,
                user_id="user_123",
                metadata={"form_id": "form_456"},
            )

        assert "API Request" in caplog.text or "POST" in caplog.text

    def test_log_request_with_error_status(self, caplog):
        """Test API request logging with error status."""
        logger_service = LoggerService("test.logger")
        with caplog.at_level(logging.WARNING):
            logger_service.log_request(
                method="GET",
                path="/api/users/invalid",
                status_code=404,
                duration_ms=10.0,
            )

        # Should log at WARNING level for 4xx errors
        assert len(caplog.records) > 0

    def test_log_audit_event_success(self, caplog):
        """Test audit event logging - success case."""
        logger_service = LoggerService("test.logger")
        with caplog.at_level(logging.INFO):
            logger_service.log_audit_event(
                action="create",
                resource_type="user",
                resource_id="user_123",
                user_id="admin_001",
                org_id="org_001",
                status="success",
            )

        assert "Audit Event" in caplog.text or "create" in caplog.text

    def test_log_audit_event_failure(self, caplog):
        """Test audit event logging - failure case."""
        logger_service = LoggerService("test.logger")
        with caplog.at_level(logging.WARNING):
            logger_service.log_audit_event(
                action="delete",
                resource_type="form",
                user_id="user_123",
                status="failure",
                details={"error": "Permission denied"},
            )

        assert len(caplog.records) > 0

    def test_log_error_event(self, caplog):
        """Test error event logging."""
        logger_service = LoggerService("test.logger")

        try:
            raise ValueError("Test error")
        except Exception as e:
            with caplog.at_level(logging.ERROR):
                logger_service.log_error_event(
                    error_type="validation_error",
                    message="Validation failed",
                    exception=e,
                    context={"field": "email"},
                    user_id="user_123",
                )

        assert "Validation failed" in caplog.text

    def test_log_performance_metric_success(self, caplog):
        """Test performance metric logging - success."""
        logger_service = LoggerService("test.logger")
        with caplog.at_level(logging.INFO):
            logger_service.log_performance_metric(
                operation="database_query",
                duration_ms=123.45,
                success=True,
                metadata={"rows": 10},
            )

        assert len(caplog.records) > 0

    def test_log_performance_metric_failure(self, caplog):
        """Test performance metric logging - failure."""
        logger_service = LoggerService("test.logger")
        with caplog.at_level(logging.WARNING):
            logger_service.log_performance_metric(
                operation="api_call",
                duration_ms=5000.0,
                success=False,
                metadata={"error": "Timeout"},
            )

        assert len(caplog.records) > 0


class TestLoggerSingletons:
    """Tests for get_logger singleton."""

    def test_get_logger_returns_same_instance(self):
        """Test that get_logger returns the same instance."""
        logger1 = get_logger("test1")
        logger2 = get_logger("test2")

        # Should be the same instance
        assert logger1 is logger2

    def test_get_logger_creates_logger_service(self):
        """Test that get_logger creates a LoggerService instance."""
        logger = get_logger("test")
        assert isinstance(logger, LoggerService)


class TestLogRequestDecorator:
    """Tests for log_request_middleware decorator."""

    def test_log_request_decorator_success(self):
        """Test log_request_middleware decorator with successful response."""
        app = Flask(__name__)

        @log_request_middleware
        def endpoint():
            return {"data": "test"}, 200

        with app.test_request_context():
            g.request_id = "req-123"
            g.user_id = "user_123"
            result = endpoint()

        assert result[1] == 200

    def test_log_request_decorator_exception(self):
        """Test log_request_middleware decorator with exception."""
        app = Flask(__name__)

        @log_request_middleware
        def endpoint():
            raise ValueError("Test error")

        with app.test_request_context():
            g.request_id = "req-123"
            g.user_id = "user_123"

            with pytest.raises(ValueError):
                endpoint()


class TestLogPerformanceDecorator:
    """Tests for log_performance decorator."""

    def test_log_performance_decorator_success(self):
        """Test log_performance decorator with successful operation."""

        @log_performance("test_operation")
        def operation():
            return "result"

        result = operation()
        assert result == "result"

    def test_log_performance_decorator_exception(self):
        """Test log_performance decorator with exception."""

        @log_performance("test_operation")
        def operation():
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            operation()


class TestLogAuditDecorator:
    """Tests for log_audit decorator."""

    def test_log_audit_decorator_success(self):
        """Test log_audit decorator with successful operation."""
        app = Flask(__name__)
        captured = {}

        class DummyLogger:
            def log_audit_event(self, **kwargs):
                captured.update(kwargs)

        @log_audit("create", "user")
        def create_operation():
            return {"uuid": "user_123", "name": "John"}

        with app.test_request_context():
            g.user_id = "admin_001"
            original_get_logger = logging_decorators.get_logger

            def fake_get_logger() -> DummyLogger:
                return DummyLogger()

            logging_decorators.get_logger = fake_get_logger
            try:
                result = create_operation()
            finally:
                logging_decorators.get_logger = original_get_logger

        assert result["uuid"] == "user_123"
        assert captured["resource_id"] == "user_123"
        assert captured["status"] == "success"

    def test_log_audit_decorator_exception(self):
        """Test log_audit decorator with exception."""
        app = Flask(__name__)
        captured = {}

        class DummyLogger:
            def log_audit_event(self, **kwargs):
                captured.update(kwargs)

        @log_audit("delete", "form")
        def delete_operation():
            raise PermissionError("Access denied")

        with app.test_request_context():
            g.user_id = "user_123"
            original_get_logger = logging_decorators.get_logger

            def fake_get_logger() -> DummyLogger:
                return DummyLogger()

            logging_decorators.get_logger = fake_get_logger

            try:
                with pytest.raises(PermissionError):
                    delete_operation()
            finally:
                logging_decorators.get_logger = original_get_logger

        assert captured["status"] == "failure"


class TestIntegrationWithFlask:
    """Integration tests with Flask app."""

    @pytest.fixture
    def app(self):
        """Create Flask app for testing."""
        app = Flask(__name__)
        app.config["TESTING"] = True
        return app

    def test_logger_with_flask_context(self, app):
        """Test logger with Flask request context."""
        logger = get_logger(__name__)

        with app.test_request_context():
            g.request_id = "req-123"
            g.user_id = "user_123"

            logger.info("Test message in context", action="test")

    def test_logger_without_flask_context(self):
        """Test logger without Flask request context."""
        logger = get_logger(__name__)
        logger.info("Test message without context", action="test")
