from __future__ import annotations

import time
from functools import wraps
from typing import Any, Callable

from flask import g, has_request_context, request

from app.services.logging.service import get_logger


def log_request_middleware(func: Callable) -> Callable:
    """Decorator to log API request details with duration/status context."""

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        start_time = time.time()
        logger = get_logger()
        try:
            result = func(*args, **kwargs)
            duration_ms = (time.time() - start_time) * 1000

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
        # Intentionally broad: decorator wraps arbitrary endpoint/service code and
        # must reliably log unexpected exceptions before re-raising.
        except Exception as exc:
            duration_ms = (time.time() - start_time) * 1000
            logger.log_error_event(
                error_type="unhandled_exception",
                message=f"Error in {request.method} {request.path}",
                exception=exc,
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
    """Decorator to measure and log operation performance metrics."""

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
            # Intentionally broad: wrapped function exceptions are domain-specific.
            except Exception as exc:
                duration_ms = (time.time() - start_time) * 1000
                logger.log_performance_metric(
                    operation=operation_name,
                    duration_ms=duration_ms,
                    success=False,
                    metadata={"error": str(exc)},
                )
                raise

        return wrapper

    return decorator


def log_audit(action: str, resource_type: str) -> Callable:
    """Decorator to emit audit events around function execution."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            logger = get_logger()
            user_id = g.get("user_id") if has_request_context() else None
            try:
                result = func(*args, **kwargs)
                resource_id = None
                if isinstance(result, dict):
                    resource_id = result.get("uuid") or result.get("id")
                elif hasattr(result, "uuid"):
                    resource_id = str(result.uuid)
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
            # Intentionally broad: wrapped function exceptions are domain-specific.
            except Exception as exc:
                logger.log_audit_event(
                    action=action,
                    resource_type=resource_type,
                    user_id=user_id,
                    status="failure",
                    details={"error": str(exc)},
                )
                raise

        return wrapper

    return decorator
