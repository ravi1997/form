"""
Middleware for automatic request/response logging with rotating files.
"""

import time
from typing import Tuple, Any

from flask import Flask, request, g, Response
from app.services import get_rotating_logger


def _extract_user_id() -> Any:
    if getattr(g, "user_id", None):
        return g.user_id
    payload = getattr(g, "resources_user_payload", None)
    if isinstance(payload, dict):
        return payload.get("sub")
    return None


def _extract_error_code(response: Response) -> str | None:
    try:
        if not response.is_json:
            return None
        payload = response.get_json(silent=True)
        if isinstance(payload, dict):
            return payload.get("error_code") or payload.get("error")
    except TypeError:
        return None
    return None


def setup_rotating_logger_middleware(
    app: Flask,
    log_dir: str = "logs",
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 10,
) -> None:
    """
    Setup request/response logging middleware for Flask app.

    Args:
        app: Flask application instance
        log_dir: Directory to store log files
        max_bytes: Max file size before rotation
        backup_count: Number of backup files to keep

    Example:
        from flask import Flask
        from app.middleware.rotating_logger_middleware import setup_rotating_logger_middleware

        app = Flask(__name__)
        setup_rotating_logger_middleware(app, log_dir="logs", max_bytes=10*1024*1024)
    """
    logger_service = get_rotating_logger(
        log_dir=log_dir,
        max_bytes=max_bytes,
        backup_count=backup_count,
    )

    @app.before_request
    def before_request_logging():
        """Log request details before processing."""
        g.start_time = time.time()
        g.user_id = _extract_user_id()
        has_auth_header = bool(request.headers.get("Authorization"))
        is_mutation = request.method in {"POST", "PUT", "PATCH", "DELETE"}

        # Capture request body for logging
        if request.method in ["POST", "PUT", "PATCH"]:
            g.request_body = request.get_data(as_text=True)
        else:
            g.request_body = None

        # Log request details
        logger_service.log_request(
            method=request.method,
            path=request.path,
            url=request.url,
            route=request.url_rule.rule if request.url_rule else request.path,
            headers=dict(request.headers),
            query_params=dict(request.args),
            path_params=dict(request.view_args or {}),
            body=g.request_body,
            client_ip=request.remote_addr,
            user_id=g.user_id,
            request_id=getattr(g, "request_id", "N/A"),
            correlation_id=getattr(
                g, "correlation_id", getattr(g, "request_id", "N/A")
            ),
        )
        logger_service.log_app_event(
            "API Started",
            context={
                "route": f"{request.method} {request.path}",
                "endpoint": request.endpoint,
                "request_id": getattr(g, "request_id", "N/A"),
                "user_id": g.user_id,
            },
        )
        stage_names = [
            "Service entry",
            "Authentication started",
            "Authentication header parsed",
            "Authorization check started",
            "Validation stage started",
            "Database stage started",
            "External API stage started",
            "Business decision stage started",
        ]
        if is_mutation:
            stage_names.append("Audit stage started")
        logger_service.log_app_event(
            "Request stage summary: Service entry | Authentication started | Authentication header parsed | Authorization check started | Validation stage started | Database stage started | External API stage started | Business decision stage started",
            context={
                "route": f"{request.method} {request.path}",
                "endpoint": request.endpoint,
                "has_authorization_header": has_auth_header,
                "stages": stage_names,
            },
        )

    @app.after_request
    def after_request_logging(response: Response) -> Response:
        """Log response details after processing."""
        if hasattr(g, "start_time"):
            duration_ms = (time.time() - g.start_time) * 1000
        else:
            duration_ms = 0

        # Get response body
        response_body = None
        if response.is_json and response.data:
            try:
                response_body = response.get_data(as_text=True)
            except UnicodeDecodeError:
                response_body = "[Unable to extract response body]"

        # Log response details
        logger_service.log_response(
            status_code=response.status_code,
            path=request.path,
            method=request.method,
            headers=dict(response.headers),
            body=response_body,
            duration_ms=duration_ms,
            user_id=_extract_user_id(),
            response_size=len(response.get_data()) if response.data else 0,
            error_code=_extract_error_code(response),
            request_id=getattr(g, "request_id", "N/A"),
            correlation_id=getattr(
                g, "correlation_id", getattr(g, "request_id", "N/A")
            ),
        )
        logger_service.log_app_event(
            "API Completed",
            context={
                "route": f"{request.method} {request.path}",
                "endpoint": request.endpoint,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
                "response_size": len(response.get_data()) if response.data else 0,
                "request_id": getattr(g, "request_id", "N/A"),
                "user_id": _extract_user_id(),
            },
        )
        logger_service.log_app_event(
            "Request stage summary: Service exit | Authentication stage completed | Authorization stage completed | Validation stage completed | Database stage completed | External API stage completed | Business decision recorded",
            context={
                "route": f"{request.method} {request.path}",
                "endpoint": request.endpoint,
                "status_code": response.status_code,
                "stages": [
                    "Service exit",
                    "Authentication stage completed",
                    "Authorization stage completed",
                    "Validation stage completed",
                    "Database stage completed",
                    "External API stage completed",
                    "Business decision recorded",
                ],
                "decision": "error" if response.status_code >= 400 else "success",
            },
        )
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            logger_service.log_app_event(
                "Audit event recorded"
                if response.status_code < 400
                else "Audit event skipped",
                level="INFO" if response.status_code < 400 else "WARNING",
                context={
                    "route": request.path,
                    "method": request.method,
                    "status_code": response.status_code,
                },
            )

        return response

    @app.errorhandler(Exception)
    def handle_error(error: Exception) -> Tuple[dict, int]:
        """Log unhandled exceptions."""
        logger_service.log_error(
            message=f"Unhandled exception in {request.method} {request.path}",
            exception=error,
            user_id=_extract_user_id(),
            endpoint=request.endpoint,
            function="middleware.handle_error",
            input_params={
                "query_params": dict(request.args),
                "path_params": dict(request.view_args or {}),
                "body": request.get_data(as_text=True)
                if request.method in ["POST", "PUT", "PATCH"]
                else None,
            },
            context={
                "request_id": g.get("request_id")
                if hasattr(g, "request_id")
                else "N/A",
                "correlation_id": g.get("correlation_id")
                if hasattr(g, "correlation_id")
                else "N/A",
                "remote_addr": request.remote_addr,
                "route": request.path,
                "method": request.method,
            },
        )

        # Log app event
        logger_service.log_app_event(
            message=f"Error occurred: {str(error)}",
            level="ERROR",
            context={
                "path": request.path,
                "method": request.method,
                "error_type": type(error).__name__,
                "request_id": g.get("request_id")
                if hasattr(g, "request_id")
                else "N/A",
            },
        )

        return {"error": "Internal server error"}, 500


def get_logger_stats() -> dict:
    """
    Get logging statistics (can be used as an API endpoint).

    Returns:
        Dictionary with log file statistics
    """
    logger_service = get_rotating_logger()
    return logger_service.get_log_stats()
