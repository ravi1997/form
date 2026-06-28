"""
json_logger.py
--------------
Structured JSON logging for centralized log management.
"""

from __future__ import annotations
import json
import logging
from datetime import datetime, timezone

class JSONFormatter(logging.Formatter):
    """Formats log records as JSON strings."""
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "filename": record.filename,
            "line_number": record.lineno,
        }
        # Include tracebacks if an exception is raised
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_data)


def setup_json_logging():
    """Override root logging handlers to output structured JSON."""
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    
    root_logger = logging.getLogger()
    # Clean up standard handlers
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)
        
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
    
    # Ensure Flask logger propagates to the root logger properly
    flask_logger = logging.getLogger("flask.app")
    for h in list(flask_logger.handlers):
        flask_logger.removeHandler(h)
    flask_logger.propagate = True
    flask_logger.setLevel(logging.INFO)
    
    # Optional: silence noisy third-party libraries slightly
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
