"""Tests for Redis-backed rate limiting behavior."""

from datetime import datetime, timedelta, timezone

import redis
from flask import Flask

from app.middleware.rate_limit import rate_limit
from app.services.rate_limit import RateLimitService


class FakeRedisClient:
    def __init__(self):
        self.store = {}

    def ping(self):
        return True

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, _ttl_seconds, value):
        self.store[key] = value

    def delete(self, key):
        self.store.pop(key, None)


def test_rate_limit_uses_redis_backend_when_configured(app_context, monkeypatch):
    shared_client = FakeRedisClient()
    monkeypatch.setattr(
        "app.services.rate_limit.redis.from_url",
        lambda *_args, **_kwargs: shared_client,
    )

    from app.services.rate_limit import RateLimitService

    service = RateLimitService()

    assert service.backend == "redis"
    assert service.redis_client is shared_client


def test_rate_limit_falls_back_with_clear_warning_when_redis_missing(
    app_context, monkeypatch
):
    from flask import current_app

    current_app.config["REDIS_URL"] = ""

    monkeypatch.setattr(
        "app.services.rate_limit.redis.from_url",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(redis.RedisError("down")),
    )

    from app.services.rate_limit import RateLimitService

    service = RateLimitService()

    assert service.backend == "memory"
    assert service.redis_client is None


def test_rate_limit_shared_backend_counts_across_workers(app_context):
    shared_client = FakeRedisClient()

    service_one = RateLimitService()
    service_two = RateLimitService()
    service_one.redis_client = shared_client
    service_two.redis_client = shared_client
    service_one.backend = "redis"
    service_two.backend = "redis"

    key = "rate_limit:global:target:/api/v1/test:GET"
    ts_key = "rate_limit_ts:global:target:/api/v1/test:GET"

    count_one, exceeded_one = service_one._increment_redis(
        key,
        ts_key,
        timedelta(minutes=1),
        max_requests=5,
    )
    count_two, exceeded_two = service_two._increment_redis(
        key,
        ts_key,
        timedelta(minutes=1),
        max_requests=5,
    )

    assert count_one == 1
    assert exceeded_one is False
    assert count_two == 2
    assert exceeded_two is False


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


def test_memory_cache_discards_expired_entries(app_context):
    service = RateLimitService()
    service.redis_client = None
    service.cache.clear()

    key = "rate_limit:global:target:/api/v1/test:GET"
    ts_key = "rate_limit_ts:global:target:/api/v1/test:GET"
    expired_start = datetime.now(timezone.utc) - timedelta(minutes=10)
    service.cache[key] = 99
    service.cache[ts_key] = expired_start

    count, exceeded = service._increment_memory(
        key,
        ts_key,
        timedelta(minutes=1),
        max_requests=5,
    )

    assert count == 1
    assert exceeded is False
    assert len(service.cache) == 2


def test_memory_cache_is_bounded(app_context):
    service = RateLimitService()
    service.redis_client = None
    service.cache.clear()
    service.memory_cache_max_entries = 10

    window = timedelta(minutes=1)
    for idx in range(20):
        key = f"rate_limit:global:target:/api/v1/test-{idx}:GET"
        ts_key = f"rate_limit_ts:global:target:/api/v1/test-{idx}:GET"
        service._increment_memory(key, ts_key, window, max_requests=5)

    assert len(service.cache) <= 10


def test_rate_limit_decorator_returns_503_when_redis_down(app_context, monkeypatch):
    app = Flask(__name__)

    class FailingService:
        def check_rate_limit(self, **_kwargs):
            raise redis.RedisError("redis down")

    monkeypatch.setattr(
        "app.middleware.rate_limit.get_rate_limit_service",
        lambda: FailingService(),
    )

    @app.route("/limited")
    @rate_limit("limited.route")
    def limited_route():
        return {"ok": True}

    with app.test_client() as client:
        response = client.get("/limited")

    assert response.status_code == 503
    assert response.get_json()["error"] == "Rate limiting unavailable"


def test_rate_limit_decorator_raises_when_fail_open_disabled(app_context, monkeypatch):
    app = Flask(__name__)
    app.config["RATE_LIMIT_FAIL_OPEN"] = False

    class FailingService:
        def check_rate_limit(self, **_kwargs):
            raise redis.RedisError("redis down")

    monkeypatch.setattr(
        "app.middleware.rate_limit.get_rate_limit_service",
        lambda: FailingService(),
    )

    @app.route("/limited")
    @rate_limit("limited.route")
    def limited_route():
        return {"ok": True}

    with app.test_client() as client:
        response = client.get("/limited")

    assert response.status_code == 500
