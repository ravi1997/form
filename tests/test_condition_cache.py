"""
Tests for condition cache layer and caching functionality.

Covers:
- Request-level evaluation cache
- TTL-based historical pattern cache
- Negative caching
- Cache statistics tracking
- Cache invalidation
- Timing instrumentation
"""

import time
from app.models.form import Condition
from app.services.condition_cache import (
    RequestLevelCache,
    TTLEvaluationCache,
    NegativeCache,
    CacheStats,
    CacheInvalidationManager,
)
from app.services.condition_evaluator import (
    ConditionEvaluator,
    get_regex_cache_stats,
)


class TestCacheStats:
    """Tests for CacheStats class."""

    def test_cache_stats_initialization(self):
        """CacheStats should initialize with zero values."""
        stats = CacheStats()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.evictions == 0
        assert stats.total_keys == 0
        assert stats.memory_bytes == 0

    def test_cache_stats_hit_ratio(self):
        """CacheStats should calculate hit ratio correctly."""
        stats = CacheStats(hits=8, misses=2)
        assert stats.hit_ratio == 80.0

    def test_cache_stats_hit_ratio_zero(self):
        """CacheStats should return 0 hit ratio with no operations."""
        stats = CacheStats()
        assert stats.hit_ratio == 0.0

    def test_cache_stats_to_dict(self):
        """CacheStats should convert to dictionary."""
        stats = CacheStats(hits=10, misses=5, evictions=2, total_keys=5)
        result = stats.to_dict()
        assert result["hits"] == 10
        assert result["misses"] == 5
        assert result["evictions"] == 2
        assert result["total_keys"] == 5
        assert "hit_ratio_percent" in result


class TestRequestLevelCache:
    """Tests for request-level evaluation cache."""

    def test_request_cache_initialization(self):
        """RequestLevelCache should initialize empty."""
        cache = RequestLevelCache()
        assert cache.get_stats().total_keys == 0

    def test_request_cache_set_and_get(self):
        """RequestLevelCache should cache and retrieve results."""
        cache = RequestLevelCache()
        context = {"value": "test"}
        cache.set("cond-1", context, True, 10.5)

        result = cache.get("cond-1", context)
        assert result is not None
        assert result[0] is True
        assert result[1] == 10.5

    def test_request_cache_miss(self):
        """RequestLevelCache should return None on cache miss."""
        cache = RequestLevelCache()
        context = {"value": "test"}
        result = cache.get("cond-1", context)
        assert result is None

    def test_request_cache_stats_tracking(self):
        """RequestLevelCache should track hits and misses."""
        cache = RequestLevelCache()
        context = {"value": "test"}

        # Miss
        cache.get("cond-1", context)
        # Hit
        cache.set("cond-1", context, True, 10.0)
        cache.get("cond-1", context)

        stats = cache.get_stats()
        assert stats.hits >= 1
        assert stats.misses >= 1

    def test_request_cache_different_contexts(self):
        """RequestLevelCache should distinguish different contexts."""
        cache = RequestLevelCache()
        context1 = {"value": "test1"}
        context2 = {"value": "test2"}

        cache.set("cond-1", context1, True, 10.0)
        cache.set("cond-1", context2, False, 20.0)

        result1 = cache.get("cond-1", context1)
        result2 = cache.get("cond-1", context2)

        assert result1[0] is True
        assert result2[0] is False

    def test_request_cache_clear(self):
        """RequestLevelCache should clear all entries."""
        cache = RequestLevelCache()
        context = {"value": "test"}
        cache.set("cond-1", context, True, 10.0)
        cache.clear()

        result = cache.get("cond-1", context)
        assert result is None
        assert cache.get_stats().total_keys == 0


class TestTTLEvaluationCache:
    """Tests for TTL-based evaluation cache."""

    def test_ttl_cache_initialization(self):
        """TTLEvaluationCache should initialize with parameters."""
        cache = TTLEvaluationCache(ttl_seconds=60, max_size=500)
        assert cache.get_stats().total_keys == 0

    def test_ttl_cache_set_and_get(self):
        """TTLEvaluationCache should cache results."""
        cache = TTLEvaluationCache(ttl_seconds=3600)
        context = {"value": "test"}
        cache.set("cond-1", context, True, 15.0)

        result = cache.get("cond-1", context)
        assert result is not None
        assert result[0] is True
        assert result[1] == 15.0

    def test_ttl_cache_expiration(self):
        """TTLEvaluationCache should expire old entries."""
        cache = TTLEvaluationCache(ttl_seconds=1, max_size=100)
        context = {"value": "test"}
        cache.set("cond-1", context, True, 10.0)

        # Wait for expiration
        time.sleep(1.1)

        result = cache.get("cond-1", context)
        assert result is None

    def test_ttl_cache_warmup(self):
        """TTLEvaluationCache should warmup with pre-populated results."""
        cache = TTLEvaluationCache(ttl_seconds=3600)
        context1 = {"value": "test1"}
        context2 = {"value": "test2"}

        warmup_data = [
            ("cond-1", context1, True, 10.0),
            ("cond-1", context2, False, 20.0),
        ]
        cache.warmup(warmup_data)

        result1 = cache.get("cond-1", context1)
        result2 = cache.get("cond-1", context2)

        assert result1[0] is True
        assert result2[0] is False

    def test_ttl_cache_clear(self):
        """TTLEvaluationCache should clear all entries."""
        cache = TTLEvaluationCache()
        context = {"value": "test"}
        cache.set("cond-1", context, True, 10.0)
        cache.clear()

        result = cache.get("cond-1", context)
        assert result is None


class TestNegativeCache:
    """Tests for negative cache (always-false tracking)."""

    def test_negative_cache_initialization(self):
        """NegativeCache should initialize empty."""
        cache = NegativeCache()
        assert cache.get_stats().total_keys == 0

    def test_negative_cache_mark_and_check(self):
        """NegativeCache should track always-false conditions."""
        cache = NegativeCache()
        context = {"value": "test"}

        # Initially should return False (not marked)
        assert cache.is_always_false("cond-1", context) is False

        # Mark as always false
        cache.mark_always_false("cond-1", context)

        # Should now return True
        assert cache.is_always_false("cond-1", context) is True

    def test_negative_cache_different_contexts(self):
        """NegativeCache should distinguish different contexts."""
        cache = NegativeCache()
        context1 = {"value": "test1"}
        context2 = {"value": "test2"}

        cache.mark_always_false("cond-1", context1)

        # context1 should be marked, context2 should not
        assert cache.is_always_false("cond-1", context1) is True
        assert cache.is_always_false("cond-1", context2) is False

    def test_negative_cache_stats(self):
        """NegativeCache should track hits and misses."""
        cache = NegativeCache()
        context = {"value": "test"}

        cache.is_always_false("cond-1", context)  # Miss
        cache.mark_always_false("cond-1", context)
        cache.is_always_false("cond-1", context)  # Hit

        stats = cache.get_stats()
        assert stats.hits >= 1
        assert stats.misses >= 1

    def test_negative_cache_clear(self):
        """NegativeCache should clear all entries."""
        cache = NegativeCache()
        context = {"value": "test"}
        cache.mark_always_false("cond-1", context)
        cache.clear()

        result = cache.is_always_false("cond-1", context)
        assert result is False


class TestCacheInvalidationManager:
    """Tests for cache invalidation manager."""

    def test_cache_invalidation_manager_initialization(self):
        """CacheInvalidationManager should initialize."""
        manager = CacheInvalidationManager()
        assert manager is not None

    def test_cache_invalidation_register_caches(self):
        """CacheInvalidationManager should register caches."""
        manager = CacheInvalidationManager()
        request_cache = RequestLevelCache()
        ttl_cache = TTLEvaluationCache()

        manager.register_request_cache("req-1", request_cache)
        manager.register_ttl_cache(ttl_cache)

        # Should not raise exception

    def test_cache_invalidation_clears_caches(self):
        """CacheInvalidationManager should clear caches on invalidation."""
        manager = CacheInvalidationManager()
        request_cache = RequestLevelCache()
        ttl_cache = TTLEvaluationCache()

        manager.register_request_cache("req-1", request_cache)
        manager.register_ttl_cache(ttl_cache)

        # Add some data
        context = {"value": "test"}
        request_cache.set("cond-1", context, True, 10.0)
        ttl_cache.set("cond-1", context, True, 10.0)

        # Invalidate
        manager.invalidate_condition("cond-1")

        # Caches should be cleared
        assert request_cache.get("cond-1", context) is None
        assert ttl_cache.get("cond-1", context) is None


class TestConditionEvaluatorWithCaching:
    """Tests for ConditionEvaluator with caching features."""

    def test_evaluator_with_request_cache(self):
        """ConditionEvaluator should use request cache."""
        condition = Condition(
            uuid="cond-1",
            conditionType="comparison",
            targetField="value",
            operator="equals",
            operands=["test"],
            isActive=True,
        )
        context = {"value": "test"}

        evaluator = ConditionEvaluator(context, enable_request_cache=True)
        result1 = evaluator.evaluate(condition)
        result2 = evaluator.evaluate(condition)

        assert result1 is True
        assert result2 is True

        # Check cache stats
        stats = evaluator.get_request_cache_stats()
        assert stats is not None
        assert stats.hits >= 1

    def test_evaluator_with_timing(self):
        """ConditionEvaluator should track evaluation timing."""
        condition = Condition(
            uuid="cond-1",
            conditionType="comparison",
            targetField="value",
            operator="equals",
            operands=["test"],
            isActive=True,
        )
        context = {"value": "test"}

        evaluator = ConditionEvaluator(context, enable_timing=True)
        evaluator.evaluate(condition)

        times = evaluator.get_evaluation_times()
        assert "cond-1" in times
        assert times["cond-1"] >= 0

    def test_evaluator_without_caching(self):
        """ConditionEvaluator should work without caching."""
        condition = Condition(
            uuid="cond-1",
            conditionType="comparison",
            targetField="value",
            operator="equals",
            operands=["test"],
            isActive=True,
        )
        context = {"value": "test"}

        evaluator = ConditionEvaluator(
            context, enable_request_cache=False, enable_timing=False
        )
        result = evaluator.evaluate(condition)

        assert result is True
        assert evaluator.get_request_cache_stats() is None

    def test_evaluator_slow_conditions_detection(self):
        """ConditionEvaluator should detect slow conditions."""
        # This is harder to test without mocking time
        evaluator = ConditionEvaluator({"value": "test"}, enable_timing=True)
        evaluator._evaluation_times["slow-cond"] = 150.0
        evaluator._evaluation_times["fast-cond"] = 50.0

        slow = evaluator.get_slow_conditions(threshold_ms=100.0)
        assert len(slow) == 1
        assert slow[0][0] == "slow-cond"


class TestRegexCacheStats:
    """Tests for regex pattern cache statistics."""

    def test_regex_cache_stats(self):
        """Regex cache should provide statistics."""
        from app.services.condition_evaluator import _compile_regex_pattern

        # Clear cache
        _compile_regex_pattern.cache_clear()

        # Compile pattern (miss)
        _compile_regex_pattern(r"\d+")

        # Compile same pattern (hit)
        _compile_regex_pattern(r"\d+")

        stats = get_regex_cache_stats()
        assert stats["hits"] >= 1
        assert stats["misses"] >= 1
        assert stats["maxsize"] == 256
        assert "hit_ratio_percent" in stats


class TestEvaluateAllWithCaching:
    """Tests for evaluate_all with short-circuit optimization."""

    def test_evaluate_all_and_short_circuit(self):
        """evaluate_all AND should short-circuit on first false."""
        cond1 = Condition(
            uuid="cond-1",
            conditionType="comparison",
            targetField="value",
            operator="equals",
            operands=["true"],
            isActive=True,
        )
        cond2 = Condition(
            uuid="cond-2",
            conditionType="comparison",
            targetField="value",
            operator="equals",
            operands=["false"],
            isActive=True,
        )

        context = {"value": "true"}
        evaluator = ConditionEvaluator(context, enable_timing=True)

        # Should short-circuit: cond1 evaluates to true, cond2 to false, result is false
        result = evaluator.evaluate_all([cond1, cond2], logical_join="AND")
        assert result is False

    def test_evaluate_all_or_short_circuit(self):
        """evaluate_all OR should short-circuit on first true."""
        cond1 = Condition(
            uuid="cond-1",
            conditionType="comparison",
            targetField="value",
            operator="equals",
            operands=["true"],
            isActive=True,
        )
        cond2 = Condition(
            uuid="cond-2",
            conditionType="comparison",
            targetField="value",
            operator="equals",
            operands=["false"],
            isActive=True,
        )

        context = {"value": "true"}
        evaluator = ConditionEvaluator(context, enable_timing=True)

        # Should short-circuit: cond1 is true, result is true
        result = evaluator.evaluate_all([cond1, cond2], logical_join="OR")
        assert result is True
