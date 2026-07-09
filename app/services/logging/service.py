from __future__ import annotations

import logging
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, Optional

from app.services.logging.formatter import StructuredFormatter


class LoggerService:
    """Centralized structured logging service."""

    def __init__(self, name: str = __name__):
        self.logger = logging.getLogger(name)
        self._setup_handlers()

    def _setup_handlers(self) -> None:
        self.logger.handlers = []
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(StructuredFormatter())
        self.logger.addHandler(console_handler)
        self.logger.setLevel(logging.DEBUG)

    def log_with_context(
        self,
        level: int,
        message: str,
        extra: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        context = extra or {}
        context.update(kwargs)
        if context:
            self.logger.log(level, message, extra={"extra": context})
        else:
            self.logger.log(level, message)

    def debug(self, message: str, **context: Any) -> None:
        self.log_with_context(logging.DEBUG, message, **context)

    def info(self, message: str, **context: Any) -> None:
        self.log_with_context(logging.INFO, message, **context)

    def warning(self, message: str, **context: Any) -> None:
        self.log_with_context(logging.WARNING, message, **context)

    def error(self, message: str, **context: Any) -> None:
        self.log_with_context(logging.ERROR, message, **context)

    def critical(self, message: str, **context: Any) -> None:
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
        context = {
            "event_type": "audit",
            "action": action,
            "resource_type": resource_type,
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
            level, f"Audit Event: {action} on {resource_type}", **context
        )

    def log_error_event(
        self,
        error_type: str,
        message: str,
        exception: Optional[Exception] = None,
        context: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
    ) -> None:
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


_logger_instance: Optional[LoggerService] = None
_logger_instance_lock = Lock()


def get_logger(name: str = __name__) -> LoggerService:
    global _logger_instance
    if _logger_instance is None:
        with _logger_instance_lock:
            if _logger_instance is None:
                _logger_instance = LoggerService(name)
    return _logger_instance
