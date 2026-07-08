# Rate Limiting Quick Reference

## Quick Start

### 1. Initialize Default Rate Limits

```bash
python scripts/init_rate_limits.py
```

This creates default rate limit configurations for common endpoints.

### 2. Add Rate Limiting to a Route

```python
from flask import Blueprint, jsonify
from app.middleware.rate_limit import rate_limit

bp = Blueprint('users', __name__, url_prefix='/api/v1/users')

@bp.route('/', methods=['GET'])
@rate_limit('users.list', default_max_requests=100, default_window_minutes=1)
def list_users():
    return jsonify({"users": []})
```

### 3. View All Rate Limits

```bash
curl -X GET http://localhost:5000/api/v1/admin/rate-limits/configs \
  -H "Authorization: Bearer <token>"
```

### 4. Create a New Rate Limit

```bash
curl -X POST http://localhost:5000/api/v1/admin/rate-limits/configs \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "rule_id": "my.endpoint",
    "scope": "route",
    "max_requests": 50,
    "window_size": 5,
    "unit": "minute",
    "http_method": "POST",
    "route_pattern": "/api/v1/my/endpoint",
    "description": "Custom rate limit",
    "is_active": true,
    "priority": 50
  }'
```

### 5. Update a Rate Limit

```bash
curl -X PATCH http://localhost:5000/api/v1/admin/rate-limits/configs/my.endpoint \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "max_requests": 100,
    "description": "Updated limit"
  }'
```

### 6. Disable a Rate Limit

```bash
curl -X POST http://localhost:5000/api/v1/admin/rate-limits/configs/my.endpoint/toggle \
  -H "Authorization: Bearer <token>"
```

### 7. View Rate Limit Violations

```bash
curl -X GET "http://localhost:5000/api/v1/admin/rate-limits/logs?blocked=true" \
  -H "Authorization: Bearer <token>"
```

### 8. Reset a User's Counter

```bash
curl -X POST http://localhost:5000/api/v1/admin/rate-limits/counters/reset \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "scope": "user",
    "target": "user-uuid-123",
    "route": "/api/v1/auth/login",
    "method": "POST"
  }'
```

## Common Scenarios

### Emergency: Disable All Login Rate Limits

```bash
curl -X POST http://localhost:5000/api/v1/admin/rate-limits/configs/bulk/update \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "rule_ids": ["auth.login"],
    "updates": { "is_active": false }
  }'
```

### Give Premium User Higher Limits

```bash
curl -X POST http://localhost:5000/api/v1/admin/rate-limits/configs \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "rule_id": "premium_user_search",
    "scope": "user",
    "target_id": "user-uuid-abc123",
    "max_requests": 1000,
    "window_size": 1,
    "unit": "hour",
    "route_pattern": "/api/v1/search",
    "description": "Premium user unlimited search",
    "is_active": true,
    "priority": 200
  }'
```

### Limit Organization API Calls

```bash
curl -X POST http://localhost:5000/api/v1/admin/rate-limits/configs \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "rule_id": "org_api_limit",
    "scope": "organization",
    "target_id": "org-uuid-xyz",
    "max_requests": 50000,
    "window_size": 24,
    "unit": "hour",
    "description": "Organization daily API limit",
    "is_active": true,
    "priority": 75
  }'
```

## Priority Order

When multiple rules apply to a request, the one with highest priority wins:

```
User-specific (priority + 4)
    ↓
Organization-specific (priority + 3)
    ↓
Route-specific (priority + 2)
    ↓
Global (priority + 1)
```

Example: If user has priority 100 and route has priority 50, user wins because (100+4) > (50+2).

## Response Headers

All rate-limited responses include:

```
X-RateLimit-Limit: 100          # Max requests allowed
X-RateLimit-Remaining: 42       # Requests remaining in window
X-RateLimit-Reset: 1625745600   # Unix timestamp when counter resets
```

## Rate Limited Response (429)

```json
{
  "error": "Rate limit exceeded",
  "message": "Too many requests. Max 50 requests per 5 minute.",
  "rate_limit": {
    "limit": 50,
    "window": "5 minute",
    "current": 51,
    "reset_at": 1625745600
  }
}
```

## Environment Variables

```bash
# Redis for distributed rate limiting (optional)
REDIS_URL=redis://localhost:6379/0

# Or with auth:
REDIS_URL=redis://:password@localhost:6379/0
```

Without Redis, the system uses in-memory tracking (works for single-instance deployments).

## Debugging

### Check if Redis is Connected

```bash
# Look for this message in logs:
# "Redis connection established for rate limiting"
# or
# "Redis not available for rate limiting: [error]"
```

### View Current Rate Limit Status for Route

```bash
curl -X GET "http://localhost:5000/api/v1/admin/rate-limits/status?route_pattern=/api/v1/search" \
  -H "Authorization: Bearer <token>"
```

### View Current Rate Limit Status for User

```bash
curl -X GET "http://localhost:5000/api/v1/admin/rate-limits/status?user_id=user-uuid-123" \
  -H "Authorization: Bearer <token>"
```

## Testing

### Test Route Protection

```bash
# First request - should succeed
curl http://localhost:5000/api/v1/auth/login -X POST

# Make 4 more requests (if limit is 5/min)
for i in {1..4}; do curl http://localhost:5000/api/v1/auth/login -X POST; done

# 6th request - should get 429
curl http://localhost:5000/api/v1/auth/login -X POST
# Response: 429 Too Many Requests
```

### Monitor Active Rate Limits

```bash
# Every 5 seconds, check who's hitting limits
watch -n 5 'curl -s "http://localhost:5000/api/v1/admin/rate-limits/logs?blocked=true&per_page=5" \
  -H "Authorization: Bearer <token>" | jq ".logs"'
```
