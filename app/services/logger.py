"""Backward-compatible facade for structured logging primitives."""

from app.services.logging import (
    LoggerService,
    get_logger,
    log_audit,
    log_performance,
    log_request_middleware,
)
from app.services.logging.formatter import StructuredFormatter

__all__ = [
    "StructuredFormatter",
    "LoggerService",
    "get_logger",
    "log_request_middleware",
    "log_performance",
    "log_audit",
]
