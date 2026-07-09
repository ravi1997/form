#!/usr/bin/env python
"""
Rate Limit Configuration Initialization Script

This script sets up default rate limit configurations for common routes.
Run this after deploying the rate limiting system.

Usage:
    python scripts/init_rate_limits.py
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_openapi_app
from app.models.rate_limit import RateLimitConfig


def init_default_rate_limits():
    """Initialize default rate limit configurations."""

    app = create_openapi_app()

    with app.app_context():
        # Default configurations to create
        default_configs = [
            # Authentication endpoints
            {
                "rule_id": "auth.login",
                "scope": "global",
                "max_requests": 5,
                "window_size": 1,
                "unit": "minute",
                "http_method": "POST",
                "route_pattern": "/api/v1/auth/login",
                "description": "Limit login attempts to prevent brute force attacks",
                "is_active": True,
                "priority": 100,
            },
            {
                "rule_id": "auth.register",
                "scope": "global",
                "max_requests": 3,
                "window_size": 1,
                "unit": "hour",
                "http_method": "POST",
                "route_pattern": "/api/v1/auth/register",
                "description": "Limit registration attempts per hour",
                "is_active": True,
                "priority": 100,
            },
            {
                "rule_id": "auth.refresh",
                "scope": "global",
                "max_requests": 20,
                "window_size": 1,
                "unit": "minute",
                "http_method": "POST",
                "route_pattern": "/api/v1/auth/refresh",
                "description": "Limit token refresh requests",
                "is_active": True,
                "priority": 90,
            },
            # General API endpoints
            {
                "rule_id": "api.search",
                "scope": "global",
                "max_requests": 50,
                "window_size": 1,
                "unit": "minute",
                "http_method": "GET",
                "route_pattern": "/api/v1/search",
                "description": "Limit search requests to prevent DoS",
                "is_active": True,
                "priority": 50,
            },
            {
                "rule_id": "api.list",
                "scope": "global",
                "max_requests": 100,
                "window_size": 1,
                "unit": "minute",
                "http_method": "GET",
                "description": "Default limit for list endpoints",
                "is_active": True,
                "priority": 10,
            },
            {
                "rule_id": "api.create",
                "scope": "global",
                "max_requests": 50,
                "window_size": 1,
                "unit": "minute",
                "http_method": "POST",
                "description": "Default limit for create endpoints",
                "is_active": True,
                "priority": 10,
            },
            {
                "rule_id": "api.update",
                "scope": "global",
                "max_requests": 100,
                "window_size": 1,
                "unit": "minute",
                "http_method": "PATCH",
                "description": "Default limit for update endpoints",
                "is_active": True,
                "priority": 10,
            },
            {
                "rule_id": "api.delete",
                "scope": "global",
                "max_requests": 50,
                "window_size": 1,
                "unit": "minute",
                "http_method": "DELETE",
                "description": "Default limit for delete endpoints",
                "is_active": True,
                "priority": 10,
            },
            # Global fallback
            {
                "rule_id": "global.default",
                "scope": "global",
                "max_requests": 1000,
                "window_size": 1,
                "unit": "hour",
                "description": "Global hourly limit for all requests",
                "is_active": True,
                "priority": 1,
            },
        ]

        created_count = 0
        skipped_count = 0

        for config_data in default_configs:
            rule_id = config_data["rule_id"]

            # Check if already exists
            existing = RateLimitConfig.objects(rule_id=rule_id).first()
            if existing:
                print(f"⊘ Skipped '{rule_id}' - already exists")
                skipped_count += 1
                continue

            # Create new config
            config = RateLimitConfig(**config_data)
            config.save()
            print(f"✓ Created '{rule_id}'")
            created_count += 1

        print("\n✓ Initialization complete!")
        print(f"  - Created: {created_count}")
        print(f"  - Skipped: {skipped_count}")
        print(f"  - Total: {created_count + skipped_count}")

        return created_count, skipped_count


if __name__ == "__main__":
    try:
        created, skipped = init_default_rate_limits()
        sys.exit(0 if created > 0 or skipped > 0 else 1)
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"✗ Error: {exc}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)
