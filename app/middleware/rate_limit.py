from functools import wraps
from flask import request, g, jsonify
from mongoengine.errors import OperationError, ValidationError
from pymongo.errors import PyMongoError
import redis
from app.services.rate_limit import get_rate_limit_service
from app.services import get_rotating_logger

logger = get_rotating_logger()


def rate_limit(
    route_pattern: str = None,
    default_max_requests: int = 100,
    default_window_minutes: int = 1,
):
    """
    Decorator to apply rate limiting to a Flask route.

    Args:
        route_pattern: Unique identifier for the route (e.g., 'auth.login', 'users.list')
        default_max_requests: Default max requests if no config found
        default_window_minutes: Default time window in minutes

    Usage:
        @app.route('/api/auth/login', methods=['POST'])
        @rate_limit('auth.login', default_max_requests=5, default_window_minutes=1)
        def login():
            ...
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                # Get request metadata
                http_method = request.method
                ip_address = request.remote_addr

                # Try to get user info from g or token
                user_uuid = getattr(g, "user_id", None)
                organization_uuid = getattr(g, "organization_id", None)

                # Determine route pattern
                final_route_pattern = route_pattern or request.endpoint or request.path

                # Get rate limit service
                service = get_rate_limit_service()

                # Check rate limit
                allowed, metadata = service.check_rate_limit(
                    route_pattern=final_route_pattern,
                    http_method=http_method,
                    user_uuid=user_uuid,
                    organization_uuid=organization_uuid,
                    identifier=ip_address,
                )

                # Store metadata in g for potential use in route handler
                g.rate_limit = metadata

                if not allowed:
                    # Rate limit exceeded
                    logger.log_app_event(
                        "rate_limit_exceeded",
                        level="WARNING",
                        context={
                            "route_pattern": final_route_pattern,
                            "user_uuid": user_uuid,
                            "ip_address": ip_address,
                            "request_id": getattr(g, "request_id", None),
                        },
                    )

                    reset_time = metadata.get("reset_time")
                    response = jsonify(
                        {
                            "error": "Rate limit exceeded",
                            "message": f"Too many requests. Max {metadata.get('max_allowed')} "
                            f"requests per {metadata.get('unit')}.",
                            "rate_limit": {
                                "limit": metadata.get("max_allowed"),
                                "window": f"{metadata.get('window_size')} {metadata.get('unit')}",
                                "current": metadata.get("current_count"),
                                "reset_at": reset_time,
                            },
                        }
                    )
                    response.status_code = 429  # Too Many Requests

                    # Add rate limit headers
                    response.headers["X-RateLimit-Limit"] = str(
                        metadata.get("max_allowed", 0)
                    )
                    response.headers["X-RateLimit-Remaining"] = str(
                        max(
                            0,
                            metadata.get("max_allowed", 0)
                            - metadata.get("current_count", 0),
                        )
                    )
                    response.headers["X-RateLimit-Reset"] = str(reset_time or 0)

                    return response

                # Request allowed, call the actual route handler
                response = func(*args, **kwargs)

                # Add rate limit headers to response
                if isinstance(response, tuple):
                    response_obj = response[0]
                else:
                    response_obj = response

                # If response is already a Flask Response object, add headers
                if hasattr(response_obj, "headers"):
                    response_obj.headers["X-RateLimit-Limit"] = str(
                        metadata.get("max_allowed", 0)
                    )
                    response_obj.headers["X-RateLimit-Remaining"] = str(
                        max(
                            0,
                            metadata.get("max_allowed", 0)
                            - metadata.get("current_count", 0),
                        )
                    )
                    response_obj.headers["X-RateLimit-Reset"] = str(
                        metadata.get("reset_time", 0)
                    )

                return response

            except (
                ValidationError,
                OperationError,
                PyMongoError,
                ValueError,
                TypeError,
                redis.RedisError,
            ) as e:
                logger.log_error(
                    "Error in rate_limit decorator",
                    exception=e,
                    context={"endpoint": request.endpoint, "path": request.path},
                )
                response = jsonify(
                    {
                        "error": "Rate limiting unavailable",
                        "message": "The request cannot be processed right now.",
                    }
                )
                response.status_code = 503
                return response

        return wrapper

    return decorator


def rate_limit_by_endpoint(
    endpoints_config: dict,
):
    """
    Advanced decorator for complex rate limiting per endpoint.

    Args:
        endpoints_config: Dict with endpoint names as keys and rate limit config as values

        Example:
        {
            'auth.login': {'max_requests': 5, 'window_minutes': 1},
            'users.list': {'max_requests': 100, 'window_minutes': 1},
            'api.search': {'max_requests': 50, 'window_minutes': 1},
        }
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                endpoint = request.endpoint or request.path
                config = endpoints_config.get(endpoint, {})

                if not config:
                    # No config for this endpoint, allow
                    return func(*args, **kwargs)

                http_method = request.method
                ip_address = request.remote_addr
                user_uuid = getattr(g, "user_id", None)
                organization_uuid = getattr(g, "organization_id", None)

                service = get_rate_limit_service()

                allowed, metadata = service.check_rate_limit(
                    route_pattern=endpoint,
                    http_method=http_method,
                    user_uuid=user_uuid,
                    organization_uuid=organization_uuid,
                    identifier=ip_address,
                )

                g.rate_limit = metadata

                if not allowed:
                    reset_time = metadata.get("reset_time")
                    response = jsonify(
                        {
                            "error": "Rate limit exceeded",
                            "message": f"Too many requests. Max {metadata.get('max_allowed')} "
                            f"requests per {metadata.get('window_size')} {metadata.get('unit')}.",
                            "rate_limit": {
                                "limit": metadata.get("max_allowed"),
                                "window": f"{metadata.get('window_size')} {metadata.get('unit')}",
                                "current": metadata.get("current_count"),
                                "reset_at": reset_time,
                            },
                        }
                    )
                    response.status_code = 429
                    response.headers["X-RateLimit-Limit"] = str(
                        metadata.get("max_allowed", 0)
                    )
                    response.headers["X-RateLimit-Remaining"] = str(
                        max(
                            0,
                            metadata.get("max_allowed", 0)
                            - metadata.get("current_count", 0),
                        )
                    )
                    response.headers["X-RateLimit-Reset"] = str(reset_time or 0)
                    return response

                return func(*args, **kwargs)

            except (
                ValidationError,
                OperationError,
                PyMongoError,
                ValueError,
                TypeError,
                redis.RedisError,
            ) as e:
                logger.log_error(
                    "Error in rate_limit_by_endpoint decorator",
                    exception=e,
                    context={"endpoint": request.endpoint, "path": request.path},
                )
                response = jsonify(
                    {
                        "error": "Rate limiting unavailable",
                        "message": "The request cannot be processed right now.",
                    }
                )
                response.status_code = 503
                return response

        return wrapper

    return decorator
