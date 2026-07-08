"""
Rate Limiting Examples

This file contains practical examples of how to use the rate limiting system.
"""

# ============================================================================
# EXAMPLE 1: Basic Route Protection
# ============================================================================

from flask import Blueprint, jsonify, request
from app.middleware.rate_limit import rate_limit

bp = Blueprint('auth', __name__, url_prefix='/api/v1/auth')


@bp.route('/login', methods=['POST'])
@rate_limit(
    route_pattern='auth.login',
    default_max_requests=5,
    default_window_minutes=1
)
def login():
    """
    Login endpoint with rate limiting.
    
    - Allows 5 login attempts per minute
    - Returns 429 if limit exceeded
    - Includes X-RateLimit-* headers in response
    """
    # Your login logic here
    return jsonify({"token": "..."})


# ============================================================================
# EXAMPLE 2: Multiple Routes with Different Limits
# ============================================================================

@bp.route('/register', methods=['POST'])
@rate_limit(
    route_pattern='auth.register',
    default_max_requests=3,
    default_window_minutes=60  # 1 hour
)
def register():
    """Register with stricter rate limit (3 per hour)."""
    return jsonify({"user": "..."})


@bp.route('/refresh', methods=['POST'])
@rate_limit(
    route_pattern='auth.refresh',
    default_max_requests=20,
    default_window_minutes=1
)
def refresh_token():
    """Refresh token with more lenient limit (20 per minute)."""
    return jsonify({"token": "..."})


# ============================================================================
# EXAMPLE 3: Advanced - Using the Service Directly
# ============================================================================

from flask import g
from app.services.rate_limit import get_rate_limit_service, RateLimitError

def protected_endpoint():
    """
    Example of manually checking rate limits using the service.
    Useful for complex scenarios or custom responses.
    """
    service = get_rate_limit_service()
    
    allowed, metadata = service.check_rate_limit(
        route_pattern='/api/v1/custom/endpoint',
        http_method=request.method,
        user_uuid=g.get('user_id'),
        organization_uuid=g.get('organization_id'),
        identifier=request.remote_addr,
    )
    
    if not allowed:
        # Custom error response
        return jsonify({
            "error": "Rate limit exceeded",
            "reset_at": metadata['reset_time'],
            "limit": metadata['max_allowed'],
        }), 429
    
    # Your endpoint logic here
    return jsonify({"data": "success"})


# ============================================================================
# EXAMPLE 4: Admin API - Create a Rate Limit
# ============================================================================

def create_rate_limit_example():
    """
    Example of creating a rate limit via the admin API.
    """
    import requests
    
    admin_token = "your-super-admin-token"
    
    # Create a rate limit for login endpoint
    response = requests.post(
        'http://localhost:5000/api/v1/admin/rate-limits/configs',
        headers={
            'Authorization': f'Bearer {admin_token}',
            'Content-Type': 'application/json',
        },
        json={
            "rule_id": "auth.login",
            "scope": "global",
            "max_requests": 5,
            "window_size": 1,
            "unit": "minute",
            "http_method": "POST",
            "route_pattern": "/api/v1/auth/login",
            "description": "Prevent brute force attacks on login",
            "is_active": True,
            "priority": 100,
        }
    )
    
    assert response.status_code == 201
    return response.json()


# ============================================================================
# EXAMPLE 5: Admin API - Give Premium User Higher Limits
# ============================================================================

def give_premium_user_limits_example():
    """
    Example of creating a user-specific rate limit override.
    """
    import requests
    
    admin_token = "your-super-admin-token"
    premium_user_id = "user-uuid-12345"
    
    # Create user-specific override with higher limits
    response = requests.post(
        'http://localhost:5000/api/v1/admin/rate-limits/configs',
        headers={
            'Authorization': f'Bearer {admin_token}',
            'Content-Type': 'application/json',
        },
        json={
            "rule_id": f"premium_user_{premium_user_id}",
            "scope": "user",
            "target_id": premium_user_id,
            "max_requests": 10000,
            "window_size": 1,
            "unit": "hour",
            "route_pattern": "/api/v1/search",
            "description": "Premium user gets higher search limits",
            "is_active": True,
            "priority": 200,  # Higher priority than global limits
        }
    )
    
    assert response.status_code == 201
    print(f"Premium user limits created: {response.json()['rule_id']}")


# ============================================================================
# EXAMPLE 6: Admin API - View Rate Limit Logs
# ============================================================================

def view_rate_limit_violations():
    """
    Example of viewing rate limit violations.
    """
    import requests
    
    admin_token = "your-super-admin-token"
    
    # Get all blocked requests
    response = requests.get(
        'http://localhost:5000/api/v1/admin/rate-limits/logs',
        headers={'Authorization': f'Bearer {admin_token}'},
        params={
            'blocked': 'true',
            'page': 1,
            'per_page': 50,
        }
    )
    
    logs = response.json()
    print(f"Total violations: {logs['total']}")
    
    for log in logs['logs']:
        print(f"\n- User: {log['user_id']}")
        print(f"  Route: {log['route_pattern']}")
        print(f"  Requests: {log['request_count']}/{log['max_allowed']}")
        print(f"  Time: {log['timestamp']}")


# ============================================================================
# EXAMPLE 7: Admin API - Emergency Response - Disable All Limits
# ============================================================================

def emergency_disable_all_limits():
    """
    Example of emergency response - disable all rate limits.
    """
    import requests
    
    admin_token = "your-super-admin-token"
    
    # Get all active rules
    response = requests.get(
        'http://localhost:5000/api/v1/admin/rate-limits/configs',
        headers={'Authorization': f'Bearer {admin_token}'},
        params={'is_active': 'true'},
    )
    
    all_rules = response.json()
    rule_ids = [rule['rule_id'] for rule in all_rules['limits']]
    
    # Disable all
    response = requests.post(
        'http://localhost:5000/api/v1/admin/rate-limits/configs/bulk/update',
        headers={
            'Authorization': f'Bearer {admin_token}',
            'Content-Type': 'application/json',
        },
        json={
            "rule_ids": rule_ids,
            "updates": {"is_active": False}
        }
    )
    
    result = response.json()
    print(f"Disabled {result['updated_count']} rate limit rules")


# ============================================================================
# EXAMPLE 8: Admin API - Reset User's Counter
# ============================================================================

def reset_user_counter():
    """
    Example of manually resetting a user's rate limit counter.
    Useful for account recovery or maintenance.
    """
    import requests
    
    admin_token = "your-super-admin-token"
    user_id = "user-uuid-12345"
    
    # Reset login counter for specific user
    response = requests.post(
        'http://localhost:5000/api/v1/admin/rate-limits/counters/reset',
        headers={
            'Authorization': f'Bearer {admin_token}',
            'Content-Type': 'application/json',
        },
        json={
            "scope": "user",
            "target": user_id,
            "route": "/api/v1/auth/login",
            "method": "POST"
        }
    )
    
    assert response.json()['success']
    print(f"User {user_id} login counter reset")


# ============================================================================
# EXAMPLE 9: Admin API - View Rate Limit Status
# ============================================================================

def view_rate_limit_status():
    """
    Example of viewing current rate limit status for a route.
    """
    import requests
    
    admin_token = "your-super-admin-token"
    
    # Get all limits for login route
    response = requests.get(
        'http://localhost:5000/api/v1/admin/rate-limits/status',
        headers={'Authorization': f'Bearer {admin_token}'},
        params={'route_pattern': '/api/v1/auth/login'},
    )
    
    status = response.json()
    print(f"Active limits for login route: {status['total']}")
    
    for limit in status['limits']:
        print(f"\n- Rule: {limit['rule_id']}")
        print(f"  Scope: {limit['scope']}")
        print(f"  Limit: {limit['max_requests']} per {limit['window_size']} {limit['unit']}")
        print(f"  Active: {limit['is_active']}")


# ============================================================================
# EXAMPLE 10: Rate Limiting with Organization Limits
# ============================================================================

def create_organization_limits():
    """
    Example of creating organization-specific rate limits.
    """
    import requests
    
    admin_token = "your-super-admin-token"
    org_id = "org-uuid-456"
    
    # Create org-specific API limits
    response = requests.post(
        'http://localhost:5000/api/v1/admin/rate-limits/configs',
        headers={
            'Authorization': f'Bearer {admin_token}',
            'Content-Type': 'application/json',
        },
        json={
            "rule_id": f"org_{org_id}_api_limit",
            "scope": "organization",
            "target_id": org_id,
            "max_requests": 100000,
            "window_size": 24,
            "unit": "hour",
            "description": f"Organization {org_id} daily API limit",
            "is_active": True,
            "priority": 75,
        }
    )
    
    assert response.status_code == 201
    print(f"Organization limits created for {org_id}")


# ============================================================================
# EXAMPLE 11: Testing Rate Limits
# ============================================================================

def test_rate_limits():
    """
    Example of testing rate limits programmatically.
    """
    import requests
    import time
    
    # Simulate rate limit being exceeded
    url = "http://localhost:5000/api/v1/auth/login"
    
    # Make requests until we hit the limit
    for i in range(7):  # If limit is 5
        response = requests.post(url, json={
            "email": "test@example.com",
            "password": "password123"
        })
        
        if response.status_code == 429:
            print(f"\n✓ Rate limit triggered on request {i+1}")
            data = response.json()
            print(f"  - Error: {data['error']}")
            print(f"  - Limit: {data['rate_limit']['limit']} per {data['rate_limit']['window']}")
            print(f"  - Remaining: {response.headers.get('X-RateLimit-Remaining', 'N/A')}")
            break
        elif response.status_code == 200:
            print(f"Request {i+1}: OK")
        else:
            print(f"Request {i+1}: {response.status_code}")


if __name__ == "__main__":
    print("Rate Limiting Examples\n")
    print("This file demonstrates common rate limiting use cases.")
    print("\nSee individual functions for examples of:")
    print("1. Basic route protection with decorators")
    print("2. Admin API usage")
    print("3. User-specific overrides")
    print("4. Organization limits")
    print("5. Emergency responses")
    print("6. Testing and monitoring")
