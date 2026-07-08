"""
Comprehensive logging service for structured, audit, and error logging.

Features:
- Structured logging for API requests/responses
- Application error and event logging
- Audit logging for security events
- Context propagation with request IDs
- Performance metrics tracking
"""

import json
import logging
import time
import traceback
from datetime import datetime
from functools import wraps
from typing import Any, Callable, Dict, Optional

from flask import has_request_context, request, g


class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured JSON logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add request context if available
        if has_request_context():
            log_data["request_id"] = g.get("request_id", "N/A")
            log_data["method"] = request.method
            log_data["path"] = request.path
            log_data["remote_addr"] = request.remote_addr

        # Add extra fields
        if hasattr(record, "extra"):
            log_data.update(record.extra)

        # Add exception info if present
        if record.exc_info and record.exc_info[0] is not None:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info),
            }

        return json.dumps(log_data)


class LoggerService:
    """
    Centralized logging service with structured, audit, and event logging capabilities.
    """

    def __init__(self, name: str = __name__):
        """
        Initialize the logger service.

        Args:
            name: Logger name (typically __name__)
        """
        self.logger = logging.getLogger(name)
        self._setup_handlers()

    def _setup_handlers(self) -> None:
        """Setup logging handlers with appropriate formatters."""
        # Remove existing handlers
        self.logger.handlers = []

        # Console handler with structured format
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(StructuredFormatter())
        self.logger.addHandler(console_handler)

        # Set default level
        self.logger.setLevel(logging.DEBUG)

    def log_with_context(
        self,
        level: int,
        message: str,
        extra: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """
        Log a message with extra context.

        Args:
            level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            message: Log message
            extra: Dictionary of extra context to include
            **kwargs: Additional keyword arguments for extra context
        """
        context = extra or {}
        context.update(kwargs)

        if context:
            self.logger.log(level, message, extra={"extra": context})
        else:
            self.logger.log(level, message)

    def debug(self, message: str, **context: Any) -> None:
        """Log debug message with context."""
        self.log_with_context(logging.DEBUG, message, **context)

    def info(self, message: str, **context: Any) -> None:
        """Log info message with context."""
        self.log_with_context(logging.INFO, message, **context)

    def warning(self, message: str, **context: Any) -> None:
        """Log warning message with context."""
        self.log_with_context(logging.WARNING, message, **context)

    def error(self, message: str, **context: Any) -> None:
        """Log error message with context."""
        self.log_with_context(logging.ERROR, message, **context)

    def critical(self, message: str, **context: Any) -> None:
        """Log critical message with context."""
        self.log_with_context(logging.CRITICAL, message, **context)

    def log_request(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log API request details.

        Args:
            method: HTTP method
            path: Request path
            status_code: Response status code
            duration_ms: Request duration in milliseconds
            user_id: Optional user ID
            metadata: Optional additional metadata
        """
        context = {
            "event_type": "api_request",
            "method": method,
            "path": path,
            "status_code": status_code,
            "duration_ms": round(duration_ms, 2),
        }

        if user_id:
            context["user_id"] = user_id

        if metadata:
            context.update(metadata)

        level = logging.INFO if status_code < 400 else logging.WARNING
        if status_code >= 500:
            level = logging.ERROR

        self.log_with_context(level, f"API Request: {method} {path}", **context)

    def log_audit_event(
        self,
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        user_id: Optional[str] = None,
        org_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        status: str = "success",
    ) -> None:
        """
        Log security/audit event.

        Args:
            action: Action performed (e.g., 'create', 'update', 'delete', 'login', 'logout')
            resource_type: Type of resource (e.g., 'user', 'form', 'response')
            resource_id: Optional resource ID
            user_id: User who performed the action
            org_id: Organization ID (if applicable)
            details: Additional audit details
            status: Status of the action ('success' or 'failure')
        """
        context = {
            "event_type": "audit",
            "action": action,
            "resource_type": resource_type,
            "status": status,
            "timestamp": datetime.utcnow().isoformat(),
        }

        if resource_id:
            context["resource_id"] = resource_id
        if user_id:
            context["user_id"] = user_id
        if org_id:
            context["org_id"] = org_id
        if details:
            context["details"] = details

        level = logging.INFO if status == "success" else logging.WARNING
        self.log_with_context(
            level,
            f"Audit Event: {action} on {resource_type}",
            **context,
        )

    def log_error_event(
        self,
        error_type: str,
        message: str,
        exception: Optional[Exception] = None,
        context: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
    ) -> None:
        """
        Log error event with exception details.

        Args:
            error_type: Type of error (e.g., 'validation_error', 'database_error')
            message: Error message
            exception: Optional exception object
            context: Additional context
            user_id: Optional user ID
        """
        log_context = {
            "event_type": "error",
            "error_type": error_type,
        }

        if context:
            log_context.update(context)
        if user_id:
            log_context["user_id"] = user_id

        if exception:
            log_context["exception_type"] = type(exception).__name__
            log_context["exception_message"] = str(exception)

        self.log_with_context(logging.ERROR, message, **log_context)

    def log_performance_metric(
        self,
        operation: str,
        duration_ms: float,
        success: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log performance metrics for operations.

        Args:
            operation: Operation name
            duration_ms: Duration in milliseconds
            success: Whether operation succeeded
            metadata: Additional metadata
        """
        context = {
            "event_type": "performance",
            "operation": operation,
            "duration_ms": round(duration_ms, 2),
            "success": success,
        }

        if metadata:
            context.update(metadata)

        level = logging.INFO if success else logging.WARNING
        self.log_with_context(level, f"Performance: {operation}", **context)


# Global logger instance
_logger_instance: Optional[LoggerService] = None


def get_logger(name: str = __name__) -> LoggerService:
    """
    Get or create the global logger instance.

    Args:
        name: Logger name

    Returns:
        LoggerService instance
    """
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = LoggerService(name)
    return _logger_instance


def log_request_middleware(func: Callable) -> Callable:
    """
    Decorator to log API request details.

    Usage:
        @app.route('/api/endpoint')
        @log_request_middleware
        def endpoint():
            return {'data': 'value'}
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        start_time = time.time()
        logger = get_logger()

        try:
            result = func(*args, **kwargs)
            duration_ms = (time.time() - start_time) * 1000

            # Extract status code from response
            status_code = 200
            if isinstance(result, tuple) and len(result) > 1:
                status_code = result[1] if isinstance(result[1], int) else 200
            elif hasattr(result, "status_code"):
                status_code = result.status_code

            user_id = g.get("user_id")
            logger.log_request(
                method=request.method,
                path=request.path,
                status_code=status_code,
                duration_ms=duration_ms,
                user_id=user_id,
            )

            return result

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.log_error_event(
                error_type="unhandled_exception",
                message=f"Error in {request.method} {request.path}",
                exception=e,
                user_id=g.get("user_id"),
            )
            logger.log_request(
                method=request.method,
                path=request.path,
                status_code=500,
                duration_ms=duration_ms,
                user_id=g.get("user_id"),
            )
            raise

    return wrapper


def log_performance(operation_name: str) -> Callable:
    """
    Decorator to measure and log operation performance.

    Usage:
        @log_performance("database_query")
        def my_query():
            pass
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.time()
            logger = get_logger()

            try:
                result = func(*args, **kwargs)
                duration_ms = (time.time() - start_time) * 1000
                logger.log_performance_metric(
                    operation=operation_name,
                    duration_ms=duration_ms,
                    success=True,
                )
                return result

            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                logger.log_performance_metric(
                    operation=operation_name,
                    duration_ms=duration_ms,
                    success=False,
                    metadata={"error": str(e)},
                )
                raise

        return wrapper

    return decorator


def log_audit(
    action: str,
    resource_type: str,
) -> Callable:
    """
    Decorator to automatically log audit events.

    Usage:
        @log_audit("create", "user")
        def create_user(user_data):
            pass
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            logger = get_logger()
            user_id = g.get("user_id") if has_request_context() else None

            try:
                result = func(*args, **kwargs)
                resource_id = None
                if isinstance(result, dict) and "id" in result:
                    resource_id = result["id"]
                elif hasattr(result, "id"):
                    resource_id = str(result.id)

                logger.log_audit_event(
                    action=action,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    user_id=user_id,
                    status="success",
                )
                return result

            except Exception as e:
                logger.log_audit_event(
                    action=action,
                    resource_type=resource_type,
                    user_id=user_id,
                    status="failure",
                    details={"error": str(e)},
                )
                raise

        return wrapper

    return decorator
