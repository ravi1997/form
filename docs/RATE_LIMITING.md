# Rate Limiting Service Documentation

## Overview

The Rate Limiting Service provides a comprehensive system for managing rate limits across your API routes. It features:

- **Multi-level Configuration**: Global, organization-specific, route-specific, and user-specific rate limits
- **Flexible Scoping**: Apply limits at different levels with priority-based resolution
- **Full Admin Control**: Super admins can create, update, view, and manage all rate limits
- **Distributed Support**: Redis-backed for distributed systems, with in-memory fallback
- **Audit Logging**: Track all rate limit events for compliance and debugging
- **Real-time Monitoring**: View current rate limit status and usage

## Architecture

### Rate Limit Hierarchy (Priority Order)

1. **User-Specific Limits** (highest priority) - Override limits for specific users
2. **Organization-Specific Limits** - Limits per organization
3. **Route-Specific Limits** - Defaults for specific API routes
4. **Global Limits** (lowest priority) - System-wide defaults

## Configuration

### Environment Variables

```bash
# Redis URL for distributed rate limiting (optional)
REDIS_URL=redis://localhost:6379/0

# Or with authentication:
REDIS_URL=redis://:password@localhost:6379/0
```

If `REDIS_URL` is not set, the system falls back to in-memory tracking (not suitable for distributed systems).

## Admin API Endpoints

All admin endpoints require super admin authentication (Bearer token with super admin role).

### 1. Create Rate Limit Configuration

**Endpoint**: `POST /api/v1/admin/rate-limits/configs`

**Request Body**:
```json
{
  "rule_id": "auth.login",
  "scope": "route",
  "max_requests": 5,
  "window_size": 1,
  "unit": "minute",
  "http_method": "POST",
  "route_pattern": "/api/v1/auth/login",
  "description": "Limit login attempts to 5 per minute",
  "is_active": true,
  "priority": 10
}
```

**Scopes**:
- `global` - Applies to all requests
- `route` - Applies to specific route
- `user` - Applies to specific user (requires target_id)
- `organization` - Applies to specific organization (requires target_id)

**Units**: `second`, `minute`, `hour`, `day`

**Response** (201):
```json
{
  "rule_id": "auth.login",
  "scope": "route",
  "target_id": null,
  "max_requests": 5,
  "window_size": 1,
  "unit": "minute",
  "http_method": "POST",
  "route_pattern": "/api/v1/auth/login",
  "description": "Limit login attempts to 5 per minute",
  "is_active": true,
  "priority": 10,
  "created_at": "2026-07-08T08:00:00+00:00",
  "updated_at": "2026-07-08T08:00:00+00:00"
}
```

### 2. List Rate Limit Configurations

**Endpoint**: `GET /api/v1/admin/rate-limits/configs`

**Query Parameters**:
- `scope` - Filter by scope (global, route, user, organization)
- `target_id` - Filter by target ID
- `route_pattern` - Filter by route pattern
- `is_active` - Filter by active status (true/false)
- `page` - Page number (default: 1)
- `per_page` - Results per page (default: 50)

**Example**:
```bash
GET /api/v1/admin/rate-limits/configs?scope=route&is_active=true&page=1&per_page=20
```

**Response** (200):
```json
{
  "total": 15,
  "page": 1,
  "per_page": 20,
  "limits": [
    {
      "rule_id": "auth.login",
      "scope": "route",
      "max_requests": 5,
      "window_size": 1,
      "unit": "minute",
      "http_method": "POST",
      "route_pattern": "/api/v1/auth/login",
      "description": "Limit login attempts to 5 per minute",
      "is_active": true,
      "priority": 10,
      "created_at": "2026-07-08T08:00:00+00:00",
      "updated_at": "2026-07-08T08:00:00+00:00"
    }
  ],
  "filters": {
    "scope": "route",
    "is_active": true
  }
}
```

### 3. Get Specific Rate Limit Configuration

**Endpoint**: `GET /api/v1/admin/rate-limits/configs/{rule_id}`

**Example**:
```bash
GET /api/v1/admin/rate-limits/configs/auth.login
```

### 4. Update Rate Limit Configuration

**Endpoint**: `PATCH /api/v1/admin/rate-limits/configs/{rule_id}`

**Request Body** (all fields optional):
```json
{
  "max_requests": 10,
  "window_size": 2,
  "unit": "minute",
  "description": "Updated to 10 requests per 2 minutes",
  "is_active": true,
  "priority": 15
}
```

### 5. Toggle Rate Limit Active Status

**Endpoint**: `POST /api/v1/admin/rate-limits/configs/{rule_id}/toggle`

Quickly enable/disable a rate limit rule without modifying its configuration.

### 6. Delete Rate Limit Configuration

**Endpoint**: `DELETE /api/v1/admin/rate-limits/configs/{rule_id}`

### 7. Bulk Update Rate Limits

**Endpoint**: `POST /api/v1/admin/rate-limits/configs/bulk/update`

**Request Body**:
```json
{
  "rule_ids": ["auth.login", "auth.refresh", "auth.logout"],
  "updates": {
    "max_requests": 20,
    "is_active": true
  }
}
```

### 8. Reset Rate Limit Counter

**Endpoint**: `POST /api/v1/admin/rate-limits/counters/reset`

Manually reset a counter for a user, organization, or route.

**Request Body**:
```json
{
  "scope": "user",
  "target": "user-uuid-12345",
  "route": "/api/v1/auth/login",
  "method": "POST"
}
```

### 9. Get Rate Limit Logs

**Endpoint**: `GET /api/v1/admin/rate-limits/logs`

**Query Parameters**:
- `user_id` - Filter by user ID
- `organization_id` - Filter by organization ID
- `route_pattern` - Filter by route pattern
- `blocked` - Filter by blocked status (true/false)
- `page` - Page number (default: 1)
- `per_page` - Results per page (default: 50)

**Example**:
```bash
GET /api/v1/admin/rate-limits/logs?blocked=true&page=1&per_page=50
```

**Response** (200):
```json
{
  "total": 42,
  "page": 1,
  "per_page": 50,
  "logs": [
    {
      "user_id": "user-123",
      "organization_id": "org-456",
      "route_pattern": "/api/v1/auth/login",
      "http_method": "POST",
      "ip_address": "192.168.1.1",
      "rule_id": "auth.login",
      "blocked": true,
      "request_count": 6,
      "max_allowed": 5,
      "timestamp": "2026-07-08T08:15:30+00:00"
    }
  ],
  "filters": {
    "blocked": true
  }
}
```

### 10. Get Rate Limit Status

**Endpoint**: `GET /api/v1/admin/rate-limits/status`

Get current rate limit configuration status with optional filtering.

**Query Parameters**:
- `user_id` - Get limits for specific user
- `organization_id` - Get limits for specific organization
- `route_pattern` - Get limits for specific route

**Example**:
```bash
GET /api/v1/admin/rate-limits/status?route_pattern=/api/v1/auth/login
```

## Using Rate Limiting in Routes

### Option 1: Using the @rate_limit Decorator

```python
from flask import request, jsonify
from app.middleware.rate_limit import rate_limit

@app.route('/api/v1/users', methods=['GET'])
@rate_limit(
    route_pattern='users.list',
    default_max_requests=100,
    default_window_minutes=1
)
def list_users():
    # Your route logic here
    return jsonify({"users": []})
```

**Response Headers** (automatically added):
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 87
X-RateLimit-Reset: 1625745600
```

**When Rate Limited (429)**:
```json
{
  "error": "Rate limit exceeded",
  "message": "Too many requests. Max 100 requests per minute.",
  "rate_limit": {
    "limit": 100,
    "window": "1 minute",
    "current": 101,
    "reset_at": 1625745600
  }
}
```

### Option 2: Using Advanced Decorator

```python
from app.middleware.rate_limit import rate_limit_by_endpoint

endpoints_config = {
    'auth.login': {'max_requests': 5, 'window_minutes': 1},
    'users.list': {'max_requests': 100, 'window_minutes': 1},
    'api.search': {'max_requests': 50, 'window_minutes': 1},
}

@app.route('/api/v1/auth/login', methods=['POST'])
@rate_limit_by_endpoint(endpoints_config)
def login():
    # Your logic here
    pass
```

### Option 3: Manual Service Usage

```python
from app.services.rate_limit import get_rate_limit_service
from flask import request, jsonify, g

@app.route('/api/v1/custom-endpoint', methods=['GET'])
def custom_endpoint():
    service = get_rate_limit_service()
    
    allowed, metadata = service.check_rate_limit(
        route_pattern='custom.endpoint',
        http_method=request.method,
        user_uuid=g.get('user_id'),
        organization_uuid=g.get('organization_id'),
        identifier=request.remote_addr,
    )
    
    if not allowed:
        return jsonify({
            "error": "Rate limit exceeded",
            "reset_at": metadata['reset_time']
        }), 429
    
    # Your logic here
    return jsonify({"data": "success"})
```

## Database Models

### RateLimitConfig

Stores rate limit configurations:

```python
{
    "_id": ObjectId,
    "rule_id": str,  # Unique identifier
    "scope": str,  # global, user, route, organization
    "target_id": str,  # Optional: user_uuid, org_uuid
    "max_requests": int,
    "window_size": int,
    "unit": str,  # second, minute, hour, day
    "http_method": str,  # Optional: GET, POST, etc.
    "route_pattern": str,  # Optional: /api/v1/users
    "description": str,
    "is_active": bool,
    "priority": int,  # Higher = higher priority
    "created_at": datetime,
    "updated_at": datetime,
    "created_by": Reference(User),
    "updated_by": Reference(User),
}
```

### RateLimitLog

Logs rate limit events:

```python
{
    "_id": ObjectId,
    "user_id": str,  # User UUID
    "organization_id": str,  # Organization UUID
    "route_pattern": str,
    "http_method": str,
    "ip_address": str,
    "rule_id": str,  # Reference to RateLimitConfig
    "blocked": bool,
    "request_count": int,
    "max_allowed": int,
    "timestamp": datetime,
}
```

## Example Usage Scenarios

### Scenario 1: Protect Login Endpoint

Create a strict rate limit for login attempts:

```bash
curl -X POST http://localhost:5000/api/v1/admin/rate-limits/configs \
  -H "Authorization: Bearer <super_admin_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "rule_id": "auth.login",
    "scope": "global",
    "max_requests": 5,
    "window_size": 1,
    "unit": "minute",
    "http_method": "POST",
    "route_pattern": "/api/v1/auth/login",
    "description": "Prevent brute force attacks on login",
    "is_active": true,
    "priority": 100
  }'
```

### Scenario 2: User-Specific Override

Allow a specific user to make more API calls:

```bash
curl -X POST http://localhost:5000/api/v1/admin/rate-limits/configs \
  -H "Authorization: Bearer <super_admin_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "rule_id": "user.premium.search",
    "scope": "user",
    "target_id": "user-uuid-12345",
    "max_requests": 500,
    "window_size": 1,
    "unit": "minute",
    "route_pattern": "/api/v1/search",
    "description": "Premium user gets higher search limit",
    "is_active": true,
    "priority": 200
  }'
```

### Scenario 3: Organization-Specific Limits

Set limits per organization:

```bash
curl -X POST http://localhost:5000/api/v1/admin/rate-limits/configs \
  -H "Authorization: Bearer <super_admin_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "rule_id": "org.api.calls",
    "scope": "organization",
    "target_id": "org-uuid-789",
    "max_requests": 10000,
    "window_size": 1,
    "unit": "hour",
    "description": "Organization-wide API call limit",
    "is_active": true,
    "priority": 50
  }'
```

### Scenario 4: View and Analyze Rate Limit Events

Find all users hitting rate limits:

```bash
curl -X GET "http://localhost:5000/api/v1/admin/rate-limits/logs?blocked=true&page=1&per_page=50" \
  -H "Authorization: Bearer <super_admin_token>"
```

### Scenario 5: Emergency Response - Disable All Limits

If you need to quickly disable all rate limits (e.g., during maintenance):

```bash
curl -X POST http://localhost:5000/api/v1/admin/rate-limits/configs/bulk/update \
  -H "Authorization: Bearer <super_admin_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "rule_ids": ["auth.login", "auth.refresh", "api.search", "api.create"],
    "updates": {
      "is_active": false
    }
  }'
```

## Best Practices

1. **Start Conservative**: Begin with lower rate limits and gradually increase based on usage patterns.

2. **Monitor Blocked Requests**: Regularly check the logs to identify legitimate users hitting limits.

3. **Use Meaningful Rule IDs**: Use descriptive IDs like `auth.login`, `api.search` for easy identification.

4. **Set Appropriate Priorities**: Higher priority for more restrictive limits that should override others.

5. **Document Limits**: Always add a description to explain why a limit exists.

6. **Test with Admin Overrides**: Create user-specific overrides for testing without affecting other users.

7. **Gradual Rollout**: When adding new limits, start with `is_active=false` and enable after testing.

8. **Monitor Redis**: If using Redis, monitor its performance as rate limiting is in the critical path.

## Troubleshooting

### Rate Limits Not Applied

1. Check if the rule is active: `GET /api/v1/admin/rate-limits/configs/{rule_id}`
2. Verify the route pattern matches your endpoint
3. Check logs for errors: `GET /api/v1/admin/rate-limits/logs?route_pattern=/your/route`

### Wrong Rate Limit Applied

Remember the priority order:
1. User-specific (highest)
2. Organization-specific
3. Route-specific
4. Global (lowest)

Check which rule has the highest priority for your route.

### Redis Connection Issues

If Redis is not available, the system falls back to in-memory tracking. Check logs for:
```
Redis not available for rate limiting: [error]
```

## API Response Codes

- `200` - Success
- `201` - Resource created
- `400` - Bad request (validation error)
- `401` - Unauthorized (missing/invalid authentication)
- `404` - Resource not found
- `429` - Rate limit exceeded
- `500` - Server error

## Performance Considerations

- **Redis Recommended**: For production systems with multiple instances
- **TTL Management**: Rate limit keys auto-expire in Redis
- **Logging**: Rate limit logs are written to MongoDB; consider archiving old logs
- **In-Memory Limits**: In-memory tracking is limited by available RAM

