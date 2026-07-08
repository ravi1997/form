"""
Rotating file logger service for managing separate log files.

Features:
- Separate rotating log files for different log types
- Automatic log rotation based on file size and time
- Preserves complete request/response headers and bodies
- Thread-safe file handling
- Configurable retention and rotation policies
"""

import logging
import os
import json
import traceback
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any

from flask import request, g, has_request_context


class RotatingLoggerService:
    """Manages rotating log files for different log types."""

    # Default configurations
    DEFAULT_LOG_DIR = "logs"
    DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
    DEFAULT_BACKUP_COUNT = 10
    DEFAULT_LOG_LEVEL = logging.DEBUG

    # Log file names
    REQUEST_LOG_FILE = "requests.log"
    RESPONSE_LOG_FILE = "responses.log"
    APP_LOG_FILE = "app.log"
    DEBUG_LOG_FILE = "debug.log"
    ERROR_LOG_FILE = "errors.log"
    SENSITIVE_KEYS = {
        "authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "password",
        "token",
        "refresh_token",
        "access_token",
        "secret",
        "client_secret",
    }

    def __init__(
        self,
        log_dir: str = DEFAULT_LOG_DIR,
        max_bytes: int = DEFAULT_MAX_BYTES,
        backup_count: int = DEFAULT_BACKUP_COUNT,
        log_level: int = DEFAULT_LOG_LEVEL,
    ):
        """
        Initialize rotating logger service.

        Args:
            log_dir: Directory to store log files
            max_bytes: Max file size before rotation (bytes)
            backup_count: Number of backup files to keep
            log_level: Default logging level
        """
        self.log_dir = Path(log_dir)
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.log_level = log_level

        # Create log directory
        self.log_dir.mkdir(exist_ok=True, parents=True)

        # Initialize loggers
        self.request_logger = self._create_logger(
            "request_logger",
            self.REQUEST_LOG_FILE,
            logging.INFO,
        )
        self.response_logger = self._create_logger(
            "response_logger",
            self.RESPONSE_LOG_FILE,
            logging.INFO,
        )
        self.app_logger = self._create_logger(
            "app_logger",
            self.APP_LOG_FILE,
            logging.INFO,
        )
        self.debug_logger = self._create_logger(
            "debug_logger",
            self.DEBUG_LOG_FILE,
            logging.DEBUG,
        )
        self.error_logger = self._create_logger(
            "error_logger",
            self.ERROR_LOG_FILE,
            logging.ERROR,
        )

    def _create_logger(
        self,
        logger_name: str,
        log_file: str,
        log_level: int,
    ) -> logging.Logger:
        """
        Create a logger with rotating file handler.

        Args:
            logger_name: Name for the logger
            log_file: Log file name
            log_level: Logging level

        Returns:
            Configured logger instance
        """
        logger = logging.getLogger(logger_name)
        logger.setLevel(log_level)
        logger.propagate = False

        # Remove existing handlers
        for existing in logger.handlers[:]:
            logger.removeHandler(existing)
            existing.close()

        # Create rotating file handler
        log_path = self.log_dir / log_file
        handler = RotatingFileHandler(
            filename=str(log_path),
            maxBytes=self.max_bytes,
            backupCount=self.backup_count,
            encoding="utf-8",
        )
        handler.setLevel(log_level)

        # Create formatter
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)

        # Add handler to logger
        logger.addHandler(handler)

        return logger

    def _is_sensitive_key(self, key: str) -> bool:
        lowered = str(key).lower()
        return lowered in self.SENSITIVE_KEYS or any(
            token in lowered for token in ("password", "secret", "token", "key")
        )

    def _mask_mapping(self, data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not data:
            return {}
        masked: Dict[str, Any] = {}
        for key, value in data.items():
            if self._is_sensitive_key(str(key)):
                masked[key] = "[MASKED]"
            else:
                masked[key] = value
        return masked

    def _safe_body(self, body: Optional[str]) -> Optional[str]:
        if not body:
            return None
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict):
                return json.dumps(self._mask_mapping(parsed), ensure_ascii=True)
        except json.JSONDecodeError:
            # Keep raw body when it's not JSON.
            pass
        if len(body) > 5000:
            return f"{body[:5000]}... [Truncated, total size: {len(body)} bytes]"
        return body

    def _request_context(self) -> Dict[str, Any]:
        if not has_request_context():
            return {}
        return {
            "request_id": getattr(g, "request_id", "N/A"),
            "correlation_id": getattr(
                g, "correlation_id", getattr(g, "request_id", "N/A")
            ),
            "method": request.method,
            "path": request.path,
            "url": request.url,
            "endpoint": request.endpoint,
            "remote_addr": request.remote_addr,
            "user_id": getattr(g, "user_id", None),
        }

    def log_request(
        self,
        method: str,
        path: str,
        url: Optional[str] = None,
        route: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        query_params: Optional[Dict[str, Any]] = None,
        path_params: Optional[Dict[str, Any]] = None,
        body: Optional[str] = None,
        client_ip: Optional[str] = None,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> None:
        """
        Log complete request details.

        Args:
            method: HTTP method
            path: Request path
            headers: Request headers
            query_params: Query parameters
            body: Request body
            client_ip: Client IP address
            user_id: User ID (if authenticated)
        """
        entry = {
            "event": "request_received",
            "timestamp": timestamp
            or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "request_id": request_id
            or (getattr(g, "request_id", "N/A") if has_request_context() else "N/A"),
            "correlation_id": correlation_id
            or (
                getattr(g, "correlation_id", getattr(g, "request_id", "N/A"))
                if has_request_context()
                else "N/A"
            ),
            "method": method,
            "url": url or path,
            "path": path,
            "route": route or path,
            "client_ip": client_ip or "Unknown",
            "user_id": user_id or "Anonymous",
            "headers": self._mask_mapping(headers),
            "query_params": self._mask_mapping(query_params),
            "path_params": self._mask_mapping(path_params),
            "body": self._safe_body(body),
        }
        self.request_logger.info(json.dumps(entry, default=str, ensure_ascii=True))

    def log_response(
        self,
        status_code: int,
        path: str,
        method: str,
        headers: Optional[Dict[str, str]] = None,
        body: Optional[str] = None,
        duration_ms: Optional[float] = None,
        user_id: Optional[str] = None,
        response_size: Optional[int] = None,
        error_code: Optional[str] = None,
        request_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> None:
        """
        Log complete response details.

        Args:
            status_code: HTTP status code
            path: Request path
            method: HTTP method
            headers: Response headers
            body: Response body
            duration_ms: Request duration in milliseconds
            user_id: User ID (if authenticated)
        """
        entry = {
            "event": "response_sent",
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "request_id": request_id
            or (getattr(g, "request_id", "N/A") if has_request_context() else "N/A"),
            "correlation_id": correlation_id
            or (
                getattr(g, "correlation_id", getattr(g, "request_id", "N/A"))
                if has_request_context()
                else "N/A"
            ),
            "status_code": status_code,
            "method": method,
            "path": path,
            "duration_ms": round(duration_ms, 2) if duration_ms is not None else None,
            "response_size": response_size
            if response_size is not None
            else (len(body) if body else 0),
            "error_code": error_code,
            "user_id": user_id or "Anonymous",
            "headers": self._mask_mapping(headers),
            "body": self._safe_body(body),
        }
        self.response_logger.info(json.dumps(entry, default=str, ensure_ascii=True))

    def log_app_event(
        self,
        message: str,
        level: str = "INFO",
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log general application event.

        Args:
            message: Event message
            level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            context: Additional context data
        """
        if isinstance(level, dict) and context is None:
            context = level
            level = "INFO"
        safe_context = self._mask_mapping(context)
        event_payload = {
            "event": "app_event",
            "message": message,
            "context": safe_context,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        event_payload.update(self._request_context())

        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
        }

        log_level = level_map.get(str(level).upper(), logging.INFO)
        self.app_logger.log(
            log_level, json.dumps(event_payload, default=str, ensure_ascii=True)
        )

    def log_debug(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log debug message.

        Args:
            message: Debug message
            context: Additional context data
        """
        payload = {
            "event": "debug",
            "message": message,
            "context": self._mask_mapping(context),
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        payload.update(self._request_context())
        self.debug_logger.debug(json.dumps(payload, default=str, ensure_ascii=True))

    def log_error(
        self,
        message: str,
        exception: Optional[Exception] = None,
        context: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        endpoint: Optional[str] = None,
        function: Optional[str] = None,
        input_params: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log error with full context.

        Args:
            message: Error message
            exception: Exception object
            context: Additional context data
            user_id: User ID (if applicable)
        """
        payload: Dict[str, Any] = {
            "event": "error",
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "context": self._mask_mapping(context),
            "input_params": self._mask_mapping(input_params),
            "endpoint": endpoint
            or (request.endpoint if has_request_context() else None),
            "function": function,
            "user_id": user_id
            or (getattr(g, "user_id", None) if has_request_context() else None),
        }
        payload.update(self._request_context())
        if exception:
            payload["exception_type"] = type(exception).__name__
            payload["exception_message"] = str(exception)
            payload["traceback"] = traceback.format_exc()
        self.error_logger.error(
            json.dumps(payload, default=str, ensure_ascii=True),
            exc_info=exception is not None,
        )

    def get_log_files(self) -> Dict[str, str]:
        """
        Get paths of all log files.

        Returns:
            Dictionary with log type and file path
        """
        return {
            "request": str(self.log_dir / self.REQUEST_LOG_FILE),
            "response": str(self.log_dir / self.RESPONSE_LOG_FILE),
            "app": str(self.log_dir / self.APP_LOG_FILE),
            "debug": str(self.log_dir / self.DEBUG_LOG_FILE),
            "error": str(self.log_dir / self.ERROR_LOG_FILE),
        }

    def get_log_size(self, log_type: str) -> int:
        """
        Get size of a log file.

        Args:
            log_type: Type of log (request, response, app, debug, error)

        Returns:
            File size in bytes
        """
        log_files = self.get_log_files()
        file_path = log_files.get(log_type)

        if not file_path or not os.path.exists(file_path):
            return 0

        return os.path.getsize(file_path)

    def get_log_stats(self) -> Dict[str, Any]:
        """
        Get statistics for all log files.

        Returns:
            Dictionary with statistics for each log type
        """
        stats = {}
        log_files = self.get_log_files()

        for log_type, file_path in log_files.items():
            if os.path.exists(file_path):
                size = os.path.getsize(file_path)
                mtime = os.path.getmtime(file_path)
                mtime_str = datetime.fromtimestamp(mtime).isoformat()
                stats[log_type] = {
                    "file": file_path,
                    "size_bytes": size,
                    "size_mb": round(size / (1024 * 1024), 2),
                    "last_modified": mtime_str,
                }
            else:
                stats[log_type] = {
                    "file": file_path,
                    "size_bytes": 0,
                    "size_mb": 0,
                    "last_modified": None,
                }

        return stats


# Global instance
_rotating_logger_instance: Optional[RotatingLoggerService] = None


def get_rotating_logger(
    log_dir: str = RotatingLoggerService.DEFAULT_LOG_DIR,
    max_bytes: int = RotatingLoggerService.DEFAULT_MAX_BYTES,
    backup_count: int = RotatingLoggerService.DEFAULT_BACKUP_COUNT,
) -> RotatingLoggerService:
    """
    Get or create the global rotating logger instance.

    Args:
        log_dir: Directory to store log files
        max_bytes: Max file size before rotation
        backup_count: Number of backup files to keep

    Returns:
        RotatingLoggerService instance (singleton)
    """
    global _rotating_logger_instance
    if (
        _rotating_logger_instance is None
        or str(_rotating_logger_instance.log_dir) != str(log_dir)
        or int(_rotating_logger_instance.max_bytes) != int(max_bytes)
        or int(_rotating_logger_instance.backup_count) != int(backup_count)
    ):
        _rotating_logger_instance = RotatingLoggerService(
            log_dir=log_dir,
            max_bytes=max_bytes,
            backup_count=backup_count,
        )
    return _rotating_logger_instance


def log_request_details(
    method: str = None,
    path: str = None,
    headers: Dict[str, str] = None,
    query_params: Dict[str, Any] = None,
    body: str = None,
) -> None:
    """
    Log complete request details using Flask context.

    Args:
        method: HTTP method (auto-detected if in request context)
        path: Request path (auto-detected if in request context)
        headers: Request headers (auto-detected if in request context)
        query_params: Query parameters
        body: Request body
    """
    if has_request_context():
        method = method or request.method
        path = path or request.path
        headers = headers or dict(request.headers)
        query_params = query_params or dict(request.args)
        body = body or request.get_data(as_text=True)
        client_ip = request.remote_addr
        user_id = g.get("user_id")
    else:
        client_ip = None
        user_id = None

    logger = _rotating_logger_instance or get_rotating_logger()
    logger.log_request(
        method=method,
        path=path,
        headers=headers,
        query_params=query_params,
        body=body,
        client_ip=client_ip,
        user_id=user_id,
    )


def log_response_details(
    status_code: int,
    headers: Dict[str, str] = None,
    body: str = None,
    duration_ms: float = None,
) -> None:
    """
    Log complete response details using Flask context.

    Args:
        status_code: HTTP status code
        headers: Response headers
        body: Response body
        duration_ms: Request duration in milliseconds
    """
    if has_request_context():
        method = request.method
        path = request.path
        user_id = g.get("user_id")
    else:
        method = None
        path = None
        user_id = None

    logger = _rotating_logger_instance or get_rotating_logger()
    logger.log_response(
        status_code=status_code,
        path=path,
        method=method,
        headers=headers,
        body=body,
        duration_ms=duration_ms,
        user_id=user_id,
    )
