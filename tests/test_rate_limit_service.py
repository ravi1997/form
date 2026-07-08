"""Tests for Redis-backed rate limiting behavior."""

from datetime import datetime, timedelta, timezone

from app.services.rate_limit import RateLimitService


class FakeRedisClient:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, _ttl_seconds, value):
        self.store[key] = value

    def delete(self, key):
        self.store.pop(key, None)


def test_increment_redis_resets_expired_window(app_context):
    service = RateLimitService()
    service.redis_client = FakeRedisClient()

    key = "rate_limit:global:target:/api/v1/test:GET"
    ts_key = "rate_limit_ts:global:target:/api/v1/test:GET"
    expired_start = datetime.now(timezone.utc) - timedelta(minutes=10)
    service.redis_client.store[ts_key] = expired_start.isoformat()
    service.redis_client.store[key] = 99

    count, exceeded = service._increment_redis(
        key,
        ts_key,
        timedelta(minutes=1),
        max_requests=5,
    )

    assert count == 1
    assert exceeded is False
    assert ts_key in service.redis_client.store
    assert service.redis_client.store[key] == 1
