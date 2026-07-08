"""
Example usage and integration patterns for the logger service.
"""

from app.services.logger import (
    get_logger,
)


# Basic usage examples
def basic_logging_example():
    """Basic logging examples."""
    logger = get_logger(__name__)

    # Simple logging with context
    logger.info("Application started", version="1.0.0", environment="production")

    # Error logging with exception
    try:
        1 / 0
    except Exception as e:
        logger.log_error_event(
            error_type="arithmetic_error",
            message="An arithmetic error occurred",
            exception=e,
        )


# Request logging example
def request_logging_example():
    """
    Example of using the logger in Flask routes.

    Usage in Flask app:
        from flask import Flask
        from app.services.logger import log_request_middleware

        app = Flask(__name__)

        @app.route('/api/users')
        @log_request_middleware
        def get_users():
            return {'users': []}
    """
    pass


# Audit logging example
def audit_logging_example():
    """
    Example of audit logging for security events.

    Usage:
        from app.services.logger import get_logger

        logger = get_logger(__name__)
        logger.log_audit_event(
            action="login",
            resource_type="user",
            user_id="user123",
            status="success"
        )
    """
    pass


# Performance tracking example
def performance_tracking_example():
    """
    Example of using the logger to track operation performance.

    Usage:
        from app.services.logger import log_performance

        @log_performance("expensive_database_query")
        def fetch_all_users():
            # expensive operation
            pass
    """
    pass


# Decorator usage example
def decorator_usage_example():
    """
    Example of using logger decorators.

    Usage in services:
        from app.services.logger import log_audit, log_performance

        @log_audit("create", "form")
        @log_performance("create_form_operation")
        def create_form(form_data):
            # Create form logic
            return {"id": "form123", "name": form_data.get("name")}
    """
    pass


# Integration with Flask app
def integrate_with_flask_app(app):
    """
    Integrate the logger service with Flask app.

    Example in app/__init__.py or app/openapi.py:

        from app.services.logger import get_logger, log_request_middleware
        from flask import g, request

        logger = get_logger(__name__)

        @app.before_request
        def before_request():
            # Store request ID in g for context propagation
            g.request_id = request.headers.get('X-Request-Id', 'N/A')
            g.user_id = None  # Set from authenticated user

        @app.after_request
        def after_request(response):
            # Log response details
            logger.log_request(
                method=request.method,
                path=request.path,
                status_code=response.status_code,
                duration_ms=0,  # Calculate from before_request
            )
            return response
    """
    pass
