"""
rate_limiter.py
---------------
Redis-based sliding-window rate limiter for Flask endpoints.
"""

from __future__ import annotations
from functools import wraps
import time
import logging
from flask import request, jsonify, g, current_app
from redis import Redis

logger = logging.getLogger(__name__)

def rate_limit(limit: int, period: int = 60):
    """
    Redis-based rate limiting decorator using a sliding window.
    
    limit  : Maximum requests allowed.
    period : Window timeframe in seconds.
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            # Bypass limit checks if authentication is disabled
            if not current_app.config.get("AUTH_ENABLED", True):
                return f(*args, **kwargs)

            redis_url = current_app.config.get("REDIS_URL")
            if not redis_url:
                return f(*args, **kwargs)

            # Define user/client identifier
            client_id = f"ip:{request.remote_addr}"
            if hasattr(g, "user") and g.user:
                client_id = f"user:{g.user.get('user_id', 'unknown')}"

            # Tiered limits based on user role
            role = "viewer"
            if hasattr(g, "user") and g.user:
                role = g.user.get("role", "viewer")
                
            actual_limit = limit
            if role == "admin":
                actual_limit = limit * 5
            elif role == "analyst":
                actual_limit = limit * 2

            try:
                r = Redis.from_url(redis_url)
                now = time.time()
                key = f"rate_limit:{client_id}:{request.endpoint}"
                
                # Remove timestamps older than the sliding window boundary
                r.zremrangebyscore(key, 0, now - period)
                
                # Count current elements in zset
                current_requests = r.zcard(key)
                
                if current_requests >= actual_limit:
                    # Fetch oldest timestamp to calculate accurate retry time
                    oldest_range = r.zrange(key, 0, 0, withscores=True)
                    retry_after = 1
                    if oldest_range:
                        oldest_ts = oldest_range[0][1]
                        retry_after = int(max(1, period - (now - oldest_ts)))
                    
                    return jsonify({
                        "status": "error",
                        "message": "Too many requests. Rate limit exceeded.",
                        "retry_after_seconds": retry_after
                    }), 429
                
                # Add current request to zset
                r.zadd(key, {str(now): now})
                r.expire(key, period)
                
            except Exception as e:
                logger.error(f"Rate limiting failure: {e}")
                
            return f(*args, **kwargs)
        return decorated
    return decorator
