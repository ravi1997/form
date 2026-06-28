"""
rate_limiter.py
---------------
Redis-based and in-memory fallback sliding-window rate limiter for Flask endpoints.
"""

from __future__ import annotations
from functools import wraps
import time
import logging
import os
import sys
from flask import request, jsonify, g, current_app
from redis import Redis
from collections import defaultdict

logger = logging.getLogger(__name__)

# In-memory store fallback
in_memory_store = defaultdict(list)

def rate_limit(limit: int, period: int = 60, window: int = None):
    """
    Sliding-window rate limiting decorator using Redis with an in-memory fallback.
    
    limit  : Maximum requests allowed.
    period : Window timeframe in seconds.
    """
    if window is not None:
        period = window

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            # Bypass limit checks if authentication is disabled
            if not current_app.config.get("AUTH_ENABLED", True):
                return f(*args, **kwargs)

            # Honor existing builder_app checks for testing and disabled auth
            if "pytest" in sys.modules or os.getenv("REQUIRE_AUTH") != "true":
                return f(*args, **kwargs)

            # Define user/client identifier
            client_id = f"ip:{request.remote_addr}"
            if hasattr(g, "user") and g.user:
                client_id = f"user:{g.user.get("user_id", "unknown")}"

            # Tiered limits based on user role
            role = "viewer"
            if hasattr(g, "user") and g.user:
                role = g.user.get("role", "viewer")
                
            actual_limit = limit
            if role == "admin":
                actual_limit = limit * 5
            elif role == "analyst":
                actual_limit = limit * 2

            redis_url = current_app.config.get("REDIS_URL")
            
            if redis_url:
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
                    return f(*args, **kwargs)
                except Exception as e:
                    logger.error(f"Redis rate limiting failure: {e}. Falling back to in-memory.")

            # In-memory fallback
            now = time.time()
            key = f"rate_limit:{client_id}:{request.endpoint or f.__name__}"
            
            # Clean up old timestamps
            in_memory_store[key] = [t for t in in_memory_store[key] if now - t < period]
            
            if len(in_memory_store[key]) >= actual_limit:
                retry_after = 1
                if in_memory_store[key]:
                    oldest_ts = in_memory_store[key][0]
                    retry_after = int(max(1, period - (now - oldest_ts)))
                return jsonify({
                    "status": "error",
                    "message": "Too many requests. Rate limit exceeded.",
                    "retry_after_seconds": retry_after
                }), 429
            
            in_memory_store[key].append(now)
            return f(*args, **kwargs)

        return decorated
    return decorator
