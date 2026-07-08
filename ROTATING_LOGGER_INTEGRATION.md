# Rotating Logger Integration Guide

## Quick Start

### 1. Update Flask App Factory (app/openapi.py)

Add this to your Flask app creation function:

```python
from flask import Flask
from app.middleware.rotating_logger_middleware import setup_rotating_logger_middleware
from app.config import apply_app_config

def create_openapi_app():
    app = Flask(__name__)
    
    # Apply configuration
    apply_app_config(app)
    
    # Setup rotating logger middleware
    setup_rotating_logger_middleware(
        app,
        log_dir="logs",              # Log files directory
        max_bytes=10 * 1024 * 1024,  # 10 MB per file
        backup_count=10,             # Keep 10 backup files
    )
    
    # Rest of app setup...
    return app
```

### 2. Manual Logging in Services

```python
from app.services import get_rotating_logger

class UserService:
    def create_user(self, user_data):
        logger = get_rotating_logger()
        
        try:
            logger.log_app_event(
                message="Creating new user",
                level="INFO",
                context={
                    "email": user_data.get("email"),
                    "source": "api",
                }
            )
            
            # Create user logic
            user = User.create(**user_data)
            
            logger.log_app_event(
                message="User created successfully",
                level="INFO",
                context={
                    "user_id": str(user.id),
                    "email": user.email,
                }
            )
            return user
            
        except Exception as e:
            logger.log_error(
                message="Failed to create user",
                exception=e,
                context={"email": user_data.get("email")},
                user_id=getattr(user, 'id', None),
            )
            raise
```

### 3. Manual Logging in Routes

```python
from flask import Blueprint, request, g, jsonify
from app.services import (
    get_rotating_logger,
    log_request_details,
    log_response_details,
)
import json
import time

bp = Blueprint('users', __name__, url_prefix='/api/users')
logger = get_rotating_logger()

@bp.route('', methods=['POST'])
def create_user():
    """Create a new user."""
    start_time = time.time()
    
    try:
        # Log request manually
        log_request_details()
        
        user_data = request.get_json()
        
        logger.log_app_event(
            message="Processing user creation",
            level="INFO",
            context={
                "email": user_data.get("email"),
                "source": request.remote_addr,
            }
        )
        
        # Create user
        user = UserService.create_user(user_data)
        
        # Prepare response
        response_body = json.dumps({"user": user.to_dict()})
        duration_ms = (time.time() - start_time) * 1000
        
        # Log response manually
        log_response_details(
            status_code=201,
            body=response_body,
            duration_ms=duration_ms,
        )
        
        return jsonify({"user": user.to_dict()}), 201
        
    except ValueError as e:
        logger.log_error(
            message="Validation error",
            exception=e,
            context={"endpoint": "/api/users"},
            user_id=g.get("user_id"),
        )
        return jsonify({"error": str(e)}), 400
        
    except Exception as e:
        logger.log_error(
            message="Unexpected error",
            exception=e,
            context={
                "endpoint": "/api/users",
                "method": request.method,
            },
            user_id=g.get("user_id"),
        )
        return jsonify({"error": "Internal server error"}), 500
```

## File Organization

Your project will have logs organized as follows:

```
project_root/
├── logs/
│   ├── requests.log          # Complete request logs (rotated)
│   ├── requests.log.1        # Backup file 1
│   ├── requests.log.2        # Backup file 2
│   ├── responses.log         # Complete response logs (rotated)
│   ├── responses.log.1       # Backup file 1
│   ├── app.log              # Application event logs (rotated)
│   ├── app.log.1
│   ├── debug.log            # Debug logs (rotated)
│   ├── debug.log.1
│   ├── errors.log           # Error logs (rotated)
│   ├── errors.log.1
│   └── ...
├── app/
│   ├── services/
│   │   ├── logger.py
│   │   └── rotating_logger.py
│   ├── middleware/
│   │   └── rotating_logger_middleware.py
│   └── ...
└── ...
```

## Configuration by Environment

### Development Environment

```python
# app/config.py
class DevelopmentConfig(BaseConfig):
    DEBUG = True
    ENV_NAME = "development"
    
    # Logging configuration
    LOG_DIR = "logs"
    LOG_MAX_BYTES = 5 * 1024 * 1024  # 5 MB for dev
    LOG_BACKUP_COUNT = 5              # Keep 5 backups
```

### Production Environment

```python
# app/config.py
class ProductionConfig(BaseConfig):
    DEBUG = False
    ENV_NAME = "production"
    
    # Logging configuration
    LOG_DIR = "/var/log/myapp"       # System log directory
    LOG_MAX_BYTES = 50 * 1024 * 1024  # 50 MB for prod
    LOG_BACKUP_COUNT = 20             # Keep 20 backups
```

### Initialize with Config

```python
from app.config import DevelopmentConfig, ProductionConfig

def create_openapi_app(env=None):
    app = Flask(__name__)
    config = DevelopmentConfig if env == 'dev' else ProductionConfig
    app.config.from_object(config)
    
    # Use config values
    setup_rotating_logger_middleware(
        app,
        log_dir=app.config.get('LOG_DIR', 'logs'),
        max_bytes=app.config.get('LOG_MAX_BYTES', 10*1024*1024),
        backup_count=app.config.get('LOG_BACKUP_COUNT', 10),
    )
    
    return app
```

## Accessing Logs

### View Request Logs

```bash
# View real-time requests
tail -f logs/requests.log

# Search for specific user
grep "user_123" logs/requests.log

# Count requests by method
grep "Method:" logs/requests.log | cut -d' ' -f2 | sort | uniq -c
```

### View Response Logs

```bash
# View response logs
tail -f logs/responses.log

# Find errors
grep "500\|404" logs/responses.log
```

### View Error Logs

```bash
# View all errors
cat logs/errors.log

# View recent errors
tail -20 logs/errors.log

# Search for specific error type
grep "ValueError" logs/errors.log
```

### View App Logs

```bash
# View app events
tail -f logs/app.log

# Find specific event
grep "User registration" logs/app.log
```

### View Debug Logs

```bash
# View debug info
tail -f logs/debug.log

# Search for debug context
grep "auth_method" logs/debug.log
```

## Monitoring Log Files

### Create Monitoring Endpoint

```python
from flask import Blueprint, jsonify, request
from app.services import get_rotating_logger
from functools import wraps

def require_admin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Add your auth check here
        return f(*args, **kwargs)
    return decorated_function

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')
logger = get_rotating_logger()

@admin_bp.route('/logs/stats', methods=['GET'])
@require_admin
def get_log_stats():
    """Get logging statistics."""
    stats = logger.get_log_stats()
    return jsonify(stats)

@admin_bp.route('/logs/<log_type>', methods=['GET'])
@require_admin
def get_log_file(log_type):
    """Get log file content."""
    log_files = logger.get_log_files()
    
    if log_type not in log_files:
        return jsonify({"error": "Invalid log type"}), 400
    
    file_path = log_files[log_type]
    lines = request.args.get('lines', 100, type=int)
    
    try:
        with open(file_path, 'r') as f:
            all_lines = f.readlines()
            tail_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
        
        return jsonify({
            "log_type": log_type,
            "file": file_path,
            "total_lines": len(all_lines),
            "lines_returned": len(tail_lines),
            "content": ''.join(tail_lines)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
```

### Python Script to Monitor Logs

```python
# scripts/monitor_logs.py
import os
from pathlib import Path
from app.services import get_rotating_logger

def monitor_logs():
    """Monitor log file sizes and provide statistics."""
    logger = get_rotating_logger(log_dir="logs")
    stats = logger.get_log_stats()
    
    print("\n" + "="*80)
    print("LOG FILE STATISTICS")
    print("="*80)
    
    total_size_mb = 0
    for log_type, info in stats.items():
        size_mb = info['size_mb']
        total_size_mb += size_mb
        
        status = "✅" if size_mb < 100 else "⚠️ " if size_mb < 500 else "❌"
        print(f"{status} {log_type:12} | {size_mb:7.2f} MB | Modified: {info['last_modified']}")
    
    print("-"*80)
    print(f"{'TOTAL':12} | {total_size_mb:7.2f} MB")
    print("="*80)

if __name__ == "__main__":
    monitor_logs()
```

Run with:
```bash
python scripts/monitor_logs.py
```

## Log Rotation Strategies

### By Size (Default)

```python
# Rotate when file reaches 10 MB
setup_rotating_logger_middleware(
    app,
    max_bytes=10 * 1024 * 1024,
    backup_count=10,
)
```

### Custom Sizes per Environment

```python
# Development
setup_rotating_logger_middleware(
    app,
    max_bytes=5 * 1024 * 1024,    # 5 MB
    backup_count=5,
)

# Production
setup_rotating_logger_middleware(
    app,
    max_bytes=100 * 1024 * 1024,  # 100 MB
    backup_count=20,
)
```

## Troubleshooting

### Issue: Logs not being created

**Solution:**
```python
# Check if logs directory exists
import os
log_dir = "logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# Verify directory permissions
os.chmod(log_dir, 0o755)
```

### Issue: Logs directory not writable

**Solution:**
```bash
# Linux/Mac
sudo chmod -R 755 logs/
sudo chown -R $USER:$USER logs/

# Docker
# Add to Dockerfile
RUN mkdir -p /app/logs && chmod 755 /app/logs
```

### Issue: Log files growing too quickly

**Solution:**
```python
# Reduce max_bytes or increase backup_count
setup_rotating_logger_middleware(
    app,
    max_bytes=5 * 1024 * 1024,    # Smaller files
    backup_count=5,               # Fewer backups
)
```

### Issue: Old logs not being deleted

**Solution:**
```python
# Archive old logs periodically
from pathlib import Path

def cleanup_old_logs(log_dir="logs", max_backups=10):
    log_dir = Path(log_dir)
    
    for log_type in ["requests", "responses", "app", "debug", "errors"]:
        # Find backup files
        backup_files = sorted(
            log_dir.glob(f"{log_type}.log.*"),
            key=lambda x: x.stat().st_mtime,
        )
        
        # Remove oldest backups beyond max_backups
        for backup in backup_files[max_backups:]:
            backup.unlink()
            print(f"Deleted: {backup}")
```

## Best Practices

1. **Monitor Log Sizes**: Regularly check log file sizes to avoid disk space issues

2. **Archive Old Logs**: Move old logs to separate storage for long-term retention

3. **Set Appropriate Levels**: 
   - Development: DEBUG
   - Production: INFO for app, ERROR for errors

4. **Include Context**: Always include user_id, request_id, and relevant data

5. **Security**: 
   - Restrict access to log files
   - Never log passwords or sensitive data
   - Mask sensitive headers (automatic)

6. **Centralize Logs**: Consider log aggregation for multi-server deployments

---

**Next Steps:**
1. Update your Flask app factory with middleware setup
2. Configure log directories in app/config.py
3. Test logging with sample requests
4. Monitor log files and adjust sizes as needed
5. Set up log monitoring endpoints for production
