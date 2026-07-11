from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, Dict, Any
import redis
from flask import current_app
from mongoengine.errors import OperationError, ValidationError
from mongoengine.queryset.visitor import Q
from pymongo.errors import PyMongoError

from app.models.rate_limit import RateLimitConfig, RateLimitLog
from app.services import get_rotating_logger

logger = get_rotating_logger()


class RateLimitError(Exception):
    """Raised when rate limit is exceeded."""

    pass


class RateLimitService:
    """
    Core service for managing and enforcing rate limits.

    Supports multiple scopes with priority-based resolution:
    1. User-specific overrides (highest priority)
    2. Organization-specific limits
    3. Route-specific defaults
    4. Global defaults (lowest priority)
    """

    # Redis key patterns
    RATE_LIMIT_KEY = "rate_limit:{scope}:{target}:{route}:{method}"
    RATE_LIMIT_TIMESTAMP_KEY = "rate_limit_ts:{scope}:{target}:{route}:{method}"
    # Shared in-memory fallback so counters survive repeated service construction.
    cache: "OrderedDict[str, Any]" = OrderedDict()
    memory_cache_max_entries = 1000

    def __init__(self):
        self.redis_client = None
        self.backend = "memory"
        self._initialize_redis()

    def _initialize_redis(self):
        """Initialize Redis connection for distributed rate limiting."""
        redis_url = current_app.config.get("REDIS_URL")
        try:
            if redis_url:
                self.redis_client = redis.from_url(redis_url, decode_responses=True)
                self.redis_client.ping()
                self.backend = "redis"
                logger.log_app_event("Redis connection established for rate limiting")
                logger.log_app_event(
                    "rate_limit_backend_selected",
                    context={"backend": "redis"},
                )
            else:
                logger.log_app_event(
                    "rate_limit_backend_selected",
                    level="WARNING",
                    context={
                        "backend": "memory fallback (unsafe)",
                        "reason": "missing_redis_url",
                    },
                )
        except (redis.RedisError, ValueError, TypeError) as e:
            self.backend = "memory"
            logger.log_app_event(
                "rate_limit_backend_selected",
                level="WARNING",
                context={
                    "backend": "memory fallback (unsafe)",
                    "error": str(e),
                },
            )
            self.redis_client = None

    def get_applicable_limit(
        self,
        route_pattern: str,
        http_method: str = None,
        user_uuid: str = None,
        organization_uuid: str = None,
    ) -> Optional[RateLimitConfig]:
        """
        Determine applicable rate limit based on priority.

        Returns the highest priority applicable limit.
        Priority order:
        1. User-specific limit (highest)
        2. Organization-specific limit
        3. Route-specific limit
        4. Global limit (lowest)
        """
        query = RateLimitConfig.objects(is_active=True)
        method_filter = http_method or ""
        scope_filter = Q(scope="global") | Q(scope="route")
        if user_uuid:
            scope_filter |= Q(scope="user", target_id=user_uuid)
        if organization_uuid:
            scope_filter |= Q(scope="organization", target_id=organization_uuid)

        limits = []
        for rule in query.filter(
            scope_filter,
            route_pattern=route_pattern,
            http_method=method_filter,
        ):
            priority_bias = {
                "user": 4,
                "organization": 3,
                "route": 2,
                "global": 1,
            }.get(rule.scope, 0)
            limits.append((rule.priority + priority_bias, rule))

        if not limits:
            return None

        # Return the limit with highest priority
        limits.sort(key=lambda x: x[0], reverse=True)
        return limits[0][1]

    def _get_window_duration(self, unit: str, window_size: int) -> timedelta:
        """Convert unit and window_size to timedelta."""
        if unit == "second":
            return timedelta(seconds=window_size)
        elif unit == "minute":
            return timedelta(minutes=window_size)
        elif unit == "hour":
            return timedelta(hours=window_size)
        elif unit == "day":
            return timedelta(days=window_size)
        else:
            raise ValueError(f"Unknown unit: {unit}")

    def _get_redis_key(self, scope: str, target: str, route: str, method: str) -> str:
        """Generate Redis key for rate limit tracking."""
        return self.RATE_LIMIT_KEY.format(
            scope=scope, target=target or "global", route=route, method=method or "all"
        )

    def _get_redis_ts_key(
        self, scope: str, target: str, route: str, method: str
    ) -> str:
        """Generate Redis key for window timestamp tracking."""
        return self.RATE_LIMIT_TIMESTAMP_KEY.format(
            scope=scope, target=target or "global", route=route, method=method or "all"
        )

    def _increment_redis(
        self,
        key: str,
        ts_key: str,
        window_duration: timedelta,
        max_requests: int,
    ) -> Tuple[int, bool]:
        """
        Increment counter in Redis and check if limit is exceeded.

        Returns: (current_count, is_exceeded)
        """
        try:
            if not self.redis_client:
                return self._increment_memory(
                    key, ts_key, window_duration, max_requests
                )

            current_time = datetime.now(timezone.utc)

            # Check if window is still valid
            window_ts = self.redis_client.get(ts_key)
            if window_ts:
                window_start = datetime.fromisoformat(window_ts)
                if current_time > window_start + window_duration:
                    # Window expired, reset counter and clear local reference so
                    # the timestamp is written again below.
                    self.redis_client.delete(key)
                    self.redis_client.delete(ts_key)
                    window_ts = None
                    count = 0
                else:
                    count = int(self.redis_client.get(key) or 0)
            else:
                # New window
                count = 0

            # Increment counter
            count += 1

            # Set keys with expiration
            ttl_seconds = int(window_duration.total_seconds()) + 10
            self.redis_client.setex(key, ttl_seconds, count)

            if not window_ts:
                self.redis_client.setex(ts_key, ttl_seconds, current_time.isoformat())

            is_exceeded = count > max_requests
            return count, is_exceeded

        except (redis.RedisError, ValueError, TypeError) as e:
            logger.log_error(
                "Redis error in rate limiting; falling back to memory",
                exception=e,
                context={"key": key, "ts_key": ts_key},
            )
            return self._increment_memory(key, ts_key, window_duration, max_requests)

    def _increment_memory(
        self,
        key: str,
        ts_key: str,
        window_duration: timedelta,
        max_requests: int,
    ) -> Tuple[int, bool]:
        """Fallback in-memory rate limit tracking (not suitable for distributed systems)."""
        current_time = datetime.now(timezone.utc)

        self._cleanup_memory_cache(current_time=current_time, window_duration=window_duration)

        window_start = self.cache.get(ts_key)
        if window_start and current_time <= window_start + window_duration:
            count = int(self.cache.get(key, 0))
        else:
            count = 0

        count += 1
        self.cache[key] = count
        self.cache[ts_key] = current_time
        self.cache.move_to_end(key)
        self.cache.move_to_end(ts_key)
        self._trim_memory_cache()

        is_exceeded = count > max_requests
        return count, is_exceeded

    def _cleanup_memory_cache(
        self, *, current_time: datetime, window_duration: timedelta
    ) -> None:
        expired_keys = []
        for cache_key, value in list(self.cache.items()):
            if not cache_key.startswith("rate_limit_ts:"):
                continue
            if current_time > value + window_duration:
                expired_keys.append(cache_key)
                expired_keys.append(cache_key.replace("rate_limit_ts:", "rate_limit:", 1))

        for cache_key in expired_keys:
            self.cache.pop(cache_key, None)

    def _trim_memory_cache(self) -> None:
        while len(self.cache) > self.memory_cache_max_entries:
            self.cache.popitem(last=False)

    def check_rate_limit(
        self,
        route_pattern: str,
        http_method: str = "GET",
        user_uuid: str = None,
        organization_uuid: str = None,
        identifier: str = None,  # IP or custom identifier
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if request is within rate limits.

        Returns: (allowed, metadata)
        where metadata contains: current_count, max_allowed, reset_time, blocked, etc.
        """
        try:
            logger.log_debug(
                "rate_limit_decision_started",
                context={
                    "route_pattern": route_pattern,
                    "http_method": http_method,
                    "user_uuid": user_uuid,
                    "organization_uuid": organization_uuid,
                },
            )
            # Get applicable limit
            limit_config = self.get_applicable_limit(
                route_pattern,
                http_method,
                user_uuid,
                organization_uuid,
            )

            if not limit_config:
                # No rate limit applies
                logger.log_debug(
                    "rate_limit_not_configured",
                    context={
                        "route_pattern": route_pattern,
                        "http_method": http_method,
                    },
                )
                return True, {"message": "No rate limit configured"}

            if not limit_config.is_active:
                logger.log_debug(
                    "rate_limit_inactive",
                    context={
                        "rule_id": limit_config.rule_id,
                        "route_pattern": route_pattern,
                    },
                )
                return True, {"message": "Rate limit is inactive"}

            # Determine the scope target for tracking
            if limit_config.scope == "user":
                scope_target = user_uuid
            elif limit_config.scope == "organization":
                scope_target = organization_uuid
            elif limit_config.scope == "route":
                scope_target = route_pattern
            else:  # global
                scope_target = "global"

            # Get window duration
            window_duration = self._get_window_duration(
                limit_config.unit, limit_config.window_size
            )

            # Get Redis keys
            redis_key = self._get_redis_key(
                limit_config.scope, scope_target, route_pattern, http_method
            )
            ts_key = self._get_redis_ts_key(
                limit_config.scope, scope_target, route_pattern, http_method
            )

            # Increment and check
            current_count, is_exceeded = self._increment_redis(
                redis_key,
                ts_key,
                window_duration,
                limit_config.max_requests,
            )

            # Calculate reset time
            reset_time = (datetime.now(timezone.utc) + window_duration).timestamp()

            metadata = {
                "rule_id": limit_config.rule_id,
                "current_count": current_count,
                "max_allowed": limit_config.max_requests,
                "window_size": limit_config.window_size,
                "unit": limit_config.unit,
                "reset_time": reset_time,
                "blocked": is_exceeded,
                "scope": limit_config.scope,
            }

            # Log the rate limit event
            self._log_rate_limit(
                user_uuid,
                organization_uuid,
                route_pattern,
                http_method,
                identifier,
                limit_config.rule_id,
                current_count,
                limit_config.max_requests,
                is_exceeded,
            )

            return not is_exceeded, metadata

        except (
            ValidationError,
            OperationError,
            PyMongoError,
            ValueError,
            TypeError,
            redis.RedisError,
        ) as e:
            logger.log_error(
                "Error checking rate limit",
                exception=e,
                context={
                    "route_pattern": route_pattern,
                    "http_method": http_method,
                    "user_uuid": user_uuid,
                    "organization_uuid": organization_uuid,
                },
            )
            return False, {"error": str(e), "message": "Rate limit check failed"}

    def _log_rate_limit(
        self,
        user_uuid: str,
        organization_uuid: str,
        route_pattern: str,
        http_method: str,
        ip_address: str,
        rule_id: str,
        request_count: int,
        max_allowed: int,
        blocked: bool,
    ):
        """Log rate limit events for audit purposes."""
        try:
            query_started = datetime.now(timezone.utc)
            log = RateLimitLog(
                user_id=user_uuid,
                organization_id=organization_uuid,
                route_pattern=route_pattern,
                http_method=http_method,
                ip_address=ip_address,
                rule_id=rule_id,
                blocked=blocked,
                request_count=request_count,
                max_allowed=max_allowed,
            )
            log.save()
            logger.log_debug(
                "rate_limit_log_saved",
                context={
                    "rule_id": rule_id,
                    "blocked": blocked,
                    "request_count": request_count,
                    "duration_ms": round(
                        (datetime.now(timezone.utc) - query_started).total_seconds()
                        * 1000,
                        2,
                    ),
                },
            )
        except (ValidationError, OperationError, PyMongoError, TypeError) as e:
            logger.log_error(
                "Error logging rate limit",
                exception=e,
                context={"rule_id": rule_id, "route_pattern": route_pattern},
            )

    def get_rate_limit_status(
        self,
        user_uuid: str = None,
        organization_uuid: str = None,
        route_pattern: str = None,
    ) -> Dict[str, Any]:
        """Get current rate limit status for a user/org/route."""
        try:
            query = RateLimitConfig.objects(is_active=True)
            filters = Q()
            if user_uuid:
                filters |= Q(scope="user", target_id=user_uuid)
            if organization_uuid:
                filters |= Q(scope="organization", target_id=organization_uuid)
            if route_pattern:
                filters |= Q(scope="route", route_pattern=route_pattern)
            filters |= Q(scope="global")
            query = query.filter(filters)
            if route_pattern:
                query = query.filter(route_pattern=route_pattern)

            limits = query.order_by("-priority")
            return {
                "limits": [limit.to_dict() for limit in limits],
                "total": len(limits),
            }
        except (ValidationError, OperationError, ValueError, TypeError) as e:
            logger.log_error(
                "Error getting rate limit status",
                exception=e,
                context={
                    "user_uuid": user_uuid,
                    "organization_uuid": organization_uuid,
                    "route_pattern": route_pattern,
                },
            )
            return {"error": str(e), "limits": []}

    def reset_counter(
        self,
        scope: str,
        target: str,
        route: str,
        method: str,
    ) -> bool:
        """Manually reset a rate limit counter."""
        try:
            key = self._get_redis_key(scope, target, route, method)
            ts_key = self._get_redis_ts_key(scope, target, route, method)

            if self.redis_client:
                self.redis_client.delete(key)
                self.redis_client.delete(ts_key)
            else:
                if key in self.cache:
                    del self.cache[key]
                if ts_key in self.cache:
                    del self.cache[ts_key]

            return True
        except (redis.RedisError, ValueError, TypeError) as e:
            logger.log_error(
                "Error resetting counter",
                exception=e,
                context={
                    "scope": scope,
                    "target": target,
                    "route": route,
                    "method": method,
                },
            )
            return False


# Global instance
_rate_limit_service = None


def get_rate_limit_service() -> RateLimitService:
    """Get or create the rate limit service."""
    global _rate_limit_service
    if _rate_limit_service is None:
        _rate_limit_service = RateLimitService()
    return _rate_limit_service
