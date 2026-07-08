from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, Dict, Any
import redis
from flask import current_app

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

    def __init__(self):
        self.redis_client = None
        self.cache = {}
        self._initialize_redis()

    def _initialize_redis(self):
        """Initialize Redis connection for distributed rate limiting."""
        try:
            if current_app.config.get("REDIS_URL"):
                self.redis_client = redis.from_url(
                    current_app.config["REDIS_URL"], decode_responses=True
                )
                self.redis_client.ping()
                logger.log_app_event("Redis connection established for rate limiting")
        except Exception as e:
            logger.log_app_event(
                "Redis not available for rate limiting; using in-memory fallback",
                level="WARNING",
                context={"error": str(e)},
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
        limits = []

        # User-specific limit
        if user_uuid:
            user_limit = RateLimitConfig.objects(
                scope="user",
                target_id=user_uuid,
                route_pattern=route_pattern,
                http_method=http_method or "",
                is_active=True,
            ).first()
            if user_limit:
                limits.append((user_limit.priority + 4, user_limit))

        # Organization-specific limit
        if organization_uuid:
            org_limit = RateLimitConfig.objects(
                scope="organization",
                target_id=organization_uuid,
                route_pattern=route_pattern,
                http_method=http_method or "",
                is_active=True,
            ).first()
            if org_limit:
                limits.append((org_limit.priority + 3, org_limit))

        # Route-specific limit
        route_limit = RateLimitConfig.objects(
            scope="route",
            route_pattern=route_pattern,
            http_method=http_method or "",
            is_active=True,
        ).first()
        if route_limit:
            limits.append((route_limit.priority + 2, route_limit))

        # Global limit (no target_id)
        global_limit = RateLimitConfig.objects(
            scope="global",
            route_pattern=route_pattern,
            http_method=http_method or "",
            is_active=True,
        ).first()
        if global_limit:
            limits.append((global_limit.priority + 1, global_limit))

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
                    # Window expired, reset counter
                    self.redis_client.delete(key)
                    self.redis_client.delete(ts_key)
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

        except Exception as e:
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

        # Check if window is still valid
        if ts_key in self.cache:
            window_start = self.cache[ts_key]
            if current_time > window_start + window_duration:
                # Window expired
                if key in self.cache:
                    del self.cache[key]
                del self.cache[ts_key]
                count = 0
            else:
                count = self.cache.get(key, 0)
        else:
            count = 0

        # Increment counter
        count += 1
        self.cache[key] = count
        self.cache[ts_key] = current_time

        is_exceeded = count > max_requests
        return count, is_exceeded

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

        except Exception as e:
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
            # In case of error, allow the request
            return True, {"error": str(e), "message": "Rate limit check failed"}

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
        except Exception as e:
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

            if user_uuid:
                query = query.filter(
                    (RateLimitConfig.scope == "user")
                    | (RateLimitConfig.target_id == user_uuid)
                )

            if organization_uuid:
                query = query.filter(
                    (RateLimitConfig.scope == "organization")
                    | (RateLimitConfig.target_id == organization_uuid)
                )

            if route_pattern:
                query = query.filter(
                    (RateLimitConfig.route_pattern == route_pattern)
                    | (RateLimitConfig.route_pattern == None)  # noqa: E711
                )

            limits = query.order_by("-priority")
            return {
                "limits": [limit.to_dict() for limit in limits],
                "total": len(limits),
            }
        except Exception as e:
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
        except Exception as e:
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
