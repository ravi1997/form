from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime

from flask import g, has_request_context, request


class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured JSON logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if has_request_context():
            log_data["request_id"] = g.get("request_id", "N/A")
            log_data["method"] = request.method
            log_data["path"] = request.path
            log_data["remote_addr"] = request.remote_addr

        if hasattr(record, "extra"):
            log_data.update(record.extra)

        if record.exc_info and record.exc_info[0] is not None:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info),
            }

        return json.dumps(log_data)
