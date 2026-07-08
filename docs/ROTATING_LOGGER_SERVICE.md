# Rotating Logger Service - Complete Documentation

## Overview

The Rotating Logger Service provides separate, automatically rotating log files for different types of logging activities in your Flask application. Each log type is stored in its own file and automatically rotates based on file size.

## Features

### ✅ Separate Log Files
- **requests.log** - Complete request logs with headers, query params, and bodies
- **responses.log** - Complete response logs with status codes, headers, and bodies
- **app.log** - General application event logging
- **debug.log** - Debug-level logging for troubleshooting
- **errors.log** - Error and exception logging with full context

### ✅ Automatic Rotation
- Log files rotate automatically when they reach max size (default: 10 MB)
- Configurable backup count (keeps last N rotated files)
- Maintains automatic log cleanup and management

### ✅ Security Features
- Sensitive headers are automatically masked (Authorization, Cookie, etc.)
- Sensitive response headers are masked (Set-Cookie, etc.)
- Large request/response bodies are truncated with size indicators
- User ID tracking across all logs

### ✅ Context Preservation
- Request ID propagation through request/response lifecycle
- User ID tracking
- Flask g object integration
- Complete audit trail capability

## Installation & Setup

### Step 1: Import the Service

```python
from app.services import get_rotating_logger
```

### Step 2: Initialize in Flask App

```python
from flask import Flask
from app.middleware.rotating_logger_middleware import setup_rotating_logger_middleware

app = Flask(__name__)

# Setup rotating logger middleware
setup_rotating_logger_middleware(
    app,
    log_dir="logs",  # Directory for log files
    max_bytes=10 * 1024 * 1024,  # 10 MB per file
    backup_count=10,  # Keep 10 backup files
)
```

## Usage Patterns

### Basic Usage - Manual Logging

```python
from app.services import get_rotating_logger

logger = get_rotating_logger()

# Log a request manually
logger.log_request(
    method="POST",
    path="/api/users",
    headers={"Content-Type": "application/json"},
    query_params={"filter": "active"},
    body='{"name": "John"}',
    client_ip="192.168.1.1",
    user_id="user_123",
)

# Log a response manually
logger.log_response(
    status_code=201,
    path="/api/users",
    method="POST",
    headers={"Content-Type": "application/json"},
    body='{"id": "user_456", "name": "John"}',
    duration_ms=45.23,
    user_id="user_123",
)

# Log an app event
logger.log_app_event(
    message="User registration completed",
    level="INFO",
    context={"user_id": "user_123", "email": "user@example.com"},
)

# Log debug information
logger.log_debug(
    message="Debugging user authentication",
    context={"auth_method": "oauth", "provider": "google"},
)

# Log an error
try:
    # Some operation
    pass
except Exception as e:
    logger.log_error(
        message="Operation failed",
        exception=e,
        context={"operation": "database_query"},
        user_id="user_123",
    )
```

### Automatic Logging with Middleware

When middleware is set up, requests and responses are automatically logged:

```python
# In app/openapi.py or your Flask factory
from app.middleware.rotating_logger_middleware import setup_rotating_logger_middleware

app = Flask(__name__)
setup_rotating_logger_middleware(app, log_dir="logs")

# All requests/responses are now automatically logged!

@app.route('/api/users', methods=['POST'])
def create_user():
    # Automatically logs:
    # 1. Complete request (headers, body, params)
    # 2. Complete response (status, headers, body)
    # 3. Any errors that occur
    user_data = request.get_json()
    return {'id': 'user_123'}, 201
```

### Using Helper Functions

```python
from flask import Flask, g
from app.services import log_request_details, log_response_details

app = Flask(__name__)

@app.route('/api/endpoint', methods=['POST'])
def endpoint():
    # Manually log request
    log_request_details()
    
    # Process request
    result = {'data': 'processed'}
    
    # Manually log response
    log_response_details(
        status_code=200,
        body=json.dumps(result),
        duration_ms=50.5,
    )
    
    return result, 200
```

## Log File Formats

### Request Log Format

```
================================================================================
REQUEST LOG - 2024-07-08T08:11:57.123Z
================================================================================
Method: POST
Path: /api/users?filter=active
Client IP: 192.168.1.1
User ID: user_123
Request ID: req-12345

HEADERS:
  Content-Type: application/json
  User-Agent: Mozilla/5.0
  Authorization: [MASKED]

QUERY PARAMETERS:
  filter: active

BODY:
{"name": "John", "email": "john@example.com"}
================================================================================
```

### Response Log Format

```
================================================================================
RESPONSE LOG - 2024-07-08T08:11:57.175Z
================================================================================
Status Code: 201
Method: POST
Path: /api/users
Duration: 45.23ms
User ID: user_123
Request ID: req-12345

HEADERS:
  Content-Type: application/json
  Content-Length: 45
  Set-Cookie: [MASKED]

BODY:
{"id": "user_456", "name": "John"}
================================================================================
```

### App Log Format

```
2024-07-08 08:11:57 - app_logger - INFO - User registration completed | Context: user_id=user_123, email=user@example.com
```

### Debug Log Format

```
2024-07-08 08:11:57 - debug_logger - DEBUG - Debugging user authentication | user_id=user_123, auth_method=oauth
```

### Error Log Format

```
2024-07-08 08:11:57 - error_logger - ERROR - Operation failed
Exception: ValueError: Database connection timeout
User ID: user_123
Request ID: req-12345
Method: POST
Path: /api/users
Remote Address: 192.168.1.1
Context:
  operation: database_query
  retry_count: 3
```

## API Reference

### RotatingLoggerService

```python
class RotatingLoggerService:
    def __init__(
        self,
        log_dir: str = "logs",
        max_bytes: int = 10 * 1024 * 1024,
        backup_count: int = 10,
        log_level: int = logging.DEBUG,
    ):
        """Initialize rotating logger service."""
        pass

    def log_request(
        self,
        method: str,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        query_params: Optional[Dict[str, Any]] = None,
        body: Optional[str] = None,
        client_ip: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> None:
        """Log complete request details."""
        pass

    def log_response(
        self,
        status_code: int,
        path: str,
        method: str,
        headers: Optional[Dict[str, str]] = None,
        body: Optional[str] = None,
        duration_ms: Optional[float] = None,
        user_id: Optional[str] = None,
    ) -> None:
        """Log complete response details."""
        pass

    def log_app_event(
        self,
        message: str,
        level: str = "INFO",
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log general application event."""
        pass

    def log_debug(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log debug message."""
        pass

    def log_error(
        self,
        message: str,
        exception: Optional[Exception] = None,
        context: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
    ) -> None:
        """Log error with full context."""
        pass

    def get_log_files(self) -> Dict[str, str]:
        """Get paths of all log files."""
        pass

    def get_log_size(self, log_type: str) -> int:
        """Get size of a log file in bytes."""
        pass

    def get_log_stats(self) -> Dict[str, Any]:
        """Get statistics for all log files."""
        pass
```

### Module Functions

```python
def get_rotating_logger(
    log_dir: str = "logs",
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 10,
) -> RotatingLoggerService:
    """Get or create the global rotating logger instance."""
    pass

def log_request_details(
    method: str = None,
    path: str = None,
    headers: Dict[str, str] = None,
    query_params: Dict[str, Any] = None,
    body: str = None,
) -> None:
    """Log complete request details using Flask context."""
    pass

def log_response_details(
    status_code: int,
    headers: Dict[str, str] = None,
    body: str = None,
    duration_ms: float = None,
) -> None:
    """Log complete response details using Flask context."""
    pass

def setup_rotating_logger_middleware(
    app: Flask,
    log_dir: str = "logs",
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 10,
) -> None:
    """Setup request/response logging middleware for Flask app."""
    pass
```

## Configuration Options

### Log Directory
- Default: `logs/`
- Configurable at initialization
- Created automatically if doesn't exist

### Maximum File Size
- Default: 10 MB
- Configure with `max_bytes` parameter
- File rotates when this size is exceeded

### Backup Count
- Default: 10 files
- Keeps this many rotated log files
- Old files are automatically deleted

### Log Level
- Request/Response: INFO
- App: INFO
- Debug: DEBUG
- Error: ERROR

## Best Practices

### 1. Include Context
```python
# Good - includes relevant context
logger.log_app_event(
    message="Form submission processed",
    level="INFO",
    context={
        "form_id": "form_123",
        "user_id": "user_456",
        "submission_count": 5
    }
)

# Avoid - no context
logger.log_app_event("Form processed", level="INFO")
```

### 2. Log Errors with Full Context
```python
# Good - includes exception and context
try:
    process_data(data)
except Exception as e:
    logger.log_error(
        message="Data processing failed",
        exception=e,
        context={
            "data_source": "api",
            "retry_count": attempt,
        },
        user_id=user_id,
    )
```

### 3. Use Appropriate Log Types
```python
# Use appropriate loggers for different purposes
logger.log_request(...)       # For incoming requests
logger.log_response(...)      # For outgoing responses
logger.log_app_event(...)     # For business logic events
logger.log_debug(...)         # For development/debugging
logger.log_error(...)         # For errors and exceptions
```

### 4. Monitor Log Sizes
```python
# Periodically check log statistics
from app.services import get_rotating_logger

logger = get_rotating_logger()
stats = logger.get_log_stats()

for log_type, info in stats.items():
    print(f"{log_type}: {info['size_mb']} MB")
```

## Monitoring & Maintenance

### Get Log Statistics

```python
from app.services import get_rotating_logger

logger = get_rotating_logger()
stats = logger.get_log_stats()

# Output format:
# {
#   "request": {
#     "file": "/path/to/logs/requests.log",
#     "size_bytes": 1024000,
#     "size_mb": 0.98,
#     "last_modified": "2024-07-08T08:11:57.000000"
#   },
#   ...
# }
```

### Create Monitoring Endpoint

```python
from flask import jsonify
from app.services import get_rotating_logger

@app.route('/api/admin/logs/stats', methods=['GET'])
@require_admin  # Add authentication decorator
def get_log_stats():
    logger = get_rotating_logger()
    return jsonify(logger.get_log_stats())
```

## Security Considerations

### Masked Headers
The following headers are automatically masked in logs:
- **Request:** Authorization, Cookie, X-API-Key, Password
- **Response:** Set-Cookie, Authorization, X-Auth-Token

### Sensitive Data
- Large request/response bodies are truncated
- Size indicators show actual data size
- User IDs are tracked but personal data is minimized

### Log File Permissions
- Ensure log directory has proper permissions
- Only authorized users should access log files
- Consider encrypting log files in production

## Troubleshooting

### Logs Not Being Created
1. Check log directory exists and is writable
2. Verify middleware is set up correctly
3. Check logger service initialization

### Log Files Growing Too Large
1. Increase rotation frequency: lower `max_bytes`
2. Increase cleanup: lower `backup_count`
3. Archive old logs regularly

### Performance Impact
- Logging has minimal overhead
- Consider rotating logs to separate disk in high-traffic scenarios
- Use appropriate log levels (INFO for production)

## Example Integration

```python
# app/openapi.py
from flask import Flask
from app.middleware.rotating_logger_middleware import setup_rotating_logger_middleware
from app.config import DevelopmentConfig

def create_openapi_app():
    app = Flask(__name__)
    app.config.from_object(DevelopmentConfig)
    
    # Setup rotating logger
    setup_rotating_logger_middleware(
        app,
        log_dir="logs",
        max_bytes=10 * 1024 * 1024,
        backup_count=10,
    )
    
    # Register routes
    # ...
    
    return app
```

---

**Status**: ✅ Complete and Ready for Use
**Test Coverage**: ✅ All manual tests passing
**Documentation**: Complete
**Integration**: Ready to deploy
