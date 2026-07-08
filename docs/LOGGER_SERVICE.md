# Logger Service Documentation

## Overview

The Logger Service provides comprehensive logging capabilities for the Flask application with support for:
- **Structured Logging**: JSON-formatted logs for easy parsing and analysis
- **API Request/Response Logging**: Automatic tracking of HTTP requests, responses, and performance
- **Audit Logging**: Security and compliance event tracking
- **Error Logging**: Exception tracking with full context
- **Performance Metrics**: Operation performance measurement and tracking

## Features

### 1. Structured Logging
All logs are output as JSON for easy integration with log aggregation systems (ELK, Splunk, etc.).

```json
{
  "timestamp": "2024-07-08T08:11:57.712Z",
  "level": "INFO",
  "logger": "app.api.users",
  "message": "User created successfully",
  "request_id": "req-123456",
  "method": "POST",
  "path": "/api/users",
  "remote_addr": "192.168.1.1",
  "extra": {
    "event_type": "audit",
    "action": "create",
    "resource_type": "user",
    "user_id": "admin_001"
  }
}
```

### 2. API Request Logging
Automatically log all API requests with method, path, status code, and performance metrics.

```python
logger = get_logger(__name__)
logger.log_request(
    method="POST",
    path="/api/users",
    status_code=201,
    duration_ms=45.23,
    user_id="user_123",
    metadata={"form_id": "form_456"}
)
```

### 3. Audit Logging
Track security and compliance events.

```python
logger.log_audit_event(
    action="login",
    resource_type="user",
    resource_id="user_123",
    user_id="user_123",
    org_id="org_001",
    status="success"
)
```

### 4. Error Logging
Log errors with full exception context.

```python
try:
    # Some operation
    1 / 0
except Exception as e:
    logger.log_error_event(
        error_type="validation_error",
        message="Failed to process user input",
        exception=e,
        context={"field": "email", "value": "invalid"},
        user_id="user_123"
    )
```

### 5. Performance Metrics
Track operation performance.

```python
logger.log_performance_metric(
    operation="database_query",
    duration_ms=123.45,
    success=True,
    metadata={"rows_affected": 10}
)
```

## Usage Patterns

### Basic Logging

```python
from app.services import get_logger

logger = get_logger(__name__)

# Simple logging with context
logger.info("User registration completed", user_id="user_123", email="user@example.com")
logger.warning("Rate limit approaching", user_id="user_123", remaining=5)
logger.error("Database connection failed", host="db.example.com", port=5432)
```

### Decorator: Request Logging

```python
from flask import Flask
from app.services import log_request_middleware

app = Flask(__name__)

@app.route('/api/users/<user_id>')
@log_request_middleware
def get_user(user_id):
    # Automatically logs request/response details
    return {"id": user_id, "name": "John Doe"}
```

### Decorator: Performance Tracking

```python
from app.services import log_performance

@log_performance("fetch_users_from_database")
def fetch_all_users():
    # Database query
    return []
```

### Decorator: Audit Logging

```python
from app.services import log_audit

@log_audit("delete", "form")
def delete_form(form_id):
    # Delete form logic
    return {"deleted": True, "id": form_id}
```

### Chaining Decorators

```python
from app.services import log_audit, log_performance

@log_audit("create", "response")
@log_performance("create_form_response")
def create_response(form_id, response_data):
    # Create response logic
    return {"id": "resp_123", "form_id": form_id}
```

## Integration with Flask App

### 1. Initialize Logger in App Factory

```python
# app/openapi.py or app/__init__.py

from flask import Flask, g, request
from app.services import get_logger

logger = get_logger(__name__)

def create_app():
    app = Flask(__name__)
    
    @app.before_request
    def before_request():
        # Initialize request context
        g.request_id = request.headers.get('X-Request-Id', 'N/A')
        g.user_id = None  # Set from authenticated user if available
        g.start_time = time.time()
        
        logger.debug(
            "Request started",
            method=request.method,
            path=request.path,
            request_id=g.request_id
        )
    
    @app.after_request
    def after_request(response):
        # Log request completion
        if hasattr(g, 'start_time'):
            duration_ms = (time.time() - g.start_time) * 1000
            logger.log_request(
                method=request.method,
                path=request.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
                user_id=g.get('user_id')
            )
        return response
    
    return app
```

### 2. Using in Services

```python
# app/services/user_service.py

from app.services import get_logger, log_audit, log_performance

logger = get_logger(__name__)

class UserService:
    @log_audit("create", "user")
    @log_performance("create_user_operation")
    def create_user(self, user_data):
        try:
            # Validation
            if not user_data.get("email"):
                raise ValueError("Email is required")
            
            # Create user
            logger.info("Creating new user", email=user_data.get("email"))
            user = User.create(**user_data)
            
            logger.info("User created successfully", user_id=user.id)
            return user
            
        except Exception as e:
            logger.log_error_event(
                error_type="user_creation_failed",
                message="Failed to create user",
                exception=e,
                context={"email": user_data.get("email")}
            )
            raise
```

### 3. Using in API Routes

```python
# app/api/users.py

from flask import Blueprint, request, jsonify
from app.services import get_logger, log_request_middleware

bp = Blueprint('users', __name__)
logger = get_logger(__name__)

@bp.route('/users', methods=['POST'])
@log_request_middleware
def create_user():
    user_data = request.get_json()
    
    try:
        logger.info("Processing user creation request", email=user_data.get("email"))
        user = UserService.create_user(user_data)
        
        return jsonify({"user": user.to_dict()}), 201
        
    except ValueError as e:
        logger.log_error_event(
            error_type="validation_error",
            message="Invalid user data",
            exception=e
        )
        return jsonify({"error": str(e)}), 400
```

## Log Levels

- **DEBUG**: Detailed information for development and debugging
- **INFO**: General informational messages (user actions, successful operations)
- **WARNING**: Warning messages (approaching limits, deprecated features)
- **ERROR**: Error messages (exceptions, failed operations)
- **CRITICAL**: Critical messages (system failures)

## Structured Log Fields

### Common Fields (All Logs)
- `timestamp`: ISO 8601 timestamp
- `level`: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `logger`: Logger name
- `message`: Log message
- `request_id`: Request identifier (from Flask g)
- `method`: HTTP method (if in request context)
- `path`: Request path (if in request context)
- `remote_addr`: Client IP address (if in request context)

### API Request Fields
- `event_type`: "api_request"
- `method`: HTTP method
- `path`: Request path
- `status_code`: HTTP status code
- `duration_ms`: Request duration in milliseconds
- `user_id`: User ID (if authenticated)

### Audit Event Fields
- `event_type`: "audit"
- `action`: Action performed (create, update, delete, login, etc.)
- `resource_type`: Resource type (user, form, response, etc.)
- `resource_id`: Resource ID
- `user_id`: User who performed the action
- `org_id`: Organization ID (if applicable)
- `status`: "success" or "failure"
- `details`: Additional audit details

### Error Event Fields
- `event_type`: "error"
- `error_type`: Type of error
- `exception_type`: Exception class name
- `exception_message`: Exception message
- `context`: Additional context

### Performance Metric Fields
- `event_type`: "performance"
- `operation`: Operation name
- `duration_ms`: Operation duration in milliseconds
- `success`: Boolean success status
- `error`: Error message (if failed)

## Best Practices

### 1. Always Include Context
```python
# Good: Clear context
logger.info("User login successful", user_id="user_123", provider="oauth")

# Avoid: Vague logging
logger.info("Login successful")
```

### 2. Use Appropriate Levels
```python
# Use INFO for successful operations
logger.info("Form submitted", form_id="form_123", user_id="user_456")

# Use WARNING for unexpected but recoverable situations
logger.warning("Retry attempt", attempt=2, max_attempts=3)

# Use ERROR for exceptions and failures
logger.error("Payment processing failed", order_id="order_789")
```

### 3. Use Audit Events for Security Sensitive Actions
```python
# For any action that affects security or compliance
logger.log_audit_event(
    action="role_assignment",
    resource_type="user",
    resource_id="user_123",
    user_id="admin_456",
    details={"role": "moderator"}
)
```

### 4. Include Performance Metrics for Long Operations
```python
import time

start = time.time()
# Long operation
duration = (time.time() - start) * 1000

logger.log_performance_metric(
    operation="bulk_import",
    duration_ms=duration,
    success=True,
    metadata={"rows_imported": 1000}
)
```

### 5. Don't Log Sensitive Data
```python
# Bad: Logging sensitive information
logger.info("User password", password="secret123")

# Good: Log only necessary identifiers
logger.info("Password reset initiated", user_id="user_123")
```

## Configuration

The logger uses default Flask logging configuration. To customize:

```python
# In app/config.py or app initialization
import logging

# Set log level for specific module
logging.getLogger('app.api').setLevel(logging.DEBUG)

# Add additional handlers (file, remote, etc.)
file_handler = logging.FileHandler('app.log')
logging.getLogger().addHandler(file_handler)
```

## Troubleshooting

### Logs Not Appearing
- Ensure logger is initialized before use
- Check logging level configuration
- Verify handlers are attached

### Performance Impact
- Structured JSON logging has minimal overhead
- Use DEBUG level only in development
- Consider asynchronous logging for high-volume scenarios

### Memory Usage
- Logger service maintains one global instance
- Handlers are cleaned up automatically
- Extra context dictionaries are garbage collected after logging

## Testing

```python
import pytest
from app.services import get_logger

def test_logger_functionality(caplog):
    logger = get_logger(__name__)
    
    with caplog.at_level(logging.INFO):
        logger.info("Test message", key="value")
    
    assert "Test message" in caplog.text
    assert "key" in caplog.text
```

## Future Enhancements

- Remote log aggregation integration
- Log filtering and sampling strategies
- Distributed tracing support
- Custom handlers for specific log types
- Log rotation and retention policies
