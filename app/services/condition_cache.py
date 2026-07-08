"""Condition cache layers: request, TTL/historical, negative, and invalidation."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any, Dict, Optional, Tuple

from cachetools import TTLCache


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    total_keys: int = 0
    memory_bytes: int = 0

    @property
    def hit_ratio(self) -> float:
        total = self.hits + self.misses
        return (self.hits / total * 100) if total else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "total_keys": self.total_keys,
            "memory_bytes": self.memory_bytes,
            "hit_ratio_percent": round(self.hit_ratio, 2),
        }


class _BaseCache:
    @staticmethod
    def _generate_cache_key(condition_uuid: str, context_hash: str) -> str:
        return f"{condition_uuid}:{context_hash}"

    @staticmethod
    def _hash_context(context: Dict[str, Any]) -> str:
        context_str = str(sorted(context.items()))
        return hashlib.md5(context_str.encode(), usedforsecurity=False).hexdigest()


class RequestLevelCache(_BaseCache):
    def __init__(self):
        self._cache: Dict[str, Tuple[bool, float]] = {}
        self._stats = CacheStats()
        self._lock = Lock()
        self._start_time = time.time()

    def get(
        self, condition_uuid: str, context: Dict[str, Any]
    ) -> Optional[Tuple[bool, float]]:
        key = self._generate_cache_key(condition_uuid, self._hash_context(context))
        with self._lock:
            if key in self._cache:
                self._stats.hits += 1
                return self._cache[key]
            self._stats.misses += 1
            return None

    def set(
        self,
        condition_uuid: str,
        context: Dict[str, Any],
        result: bool,
        evaluation_time_ms: float,
    ) -> None:
        key = self._generate_cache_key(condition_uuid, self._hash_context(context))
        with self._lock:
            self._cache[key] = (result, evaluation_time_ms)
            self._stats.total_keys = len(self._cache)

    def invalidate_condition(self, condition_uuid: str) -> int:
        with self._lock:
            keys = [k for k in self._cache if k.startswith(f"{condition_uuid}:")]
            for k in keys:
                self._cache.pop(k, None)
            self._stats.evictions += len(keys)
            self._stats.total_keys = len(self._cache)
            return len(keys)

    def clear(self) -> None:
        with self._lock:
            old_size = len(self._cache)
            self._cache.clear()
            self._stats.evictions += old_size
            self._stats.total_keys = 0

    def get_stats(self) -> CacheStats:
        with self._lock:
            import sys

            memory_bytes = sys.getsizeof(self._cache)
            for key, value in self._cache.items():
                memory_bytes += sys.getsizeof(key) + sys.getsizeof(value)
            self._stats.memory_bytes = memory_bytes
            return CacheStats(**self._stats.__dict__)


class TTLEvaluationCache(_BaseCache):
    def __init__(self, ttl_seconds: int = 300, max_size: int = 1000):
        self._cache: TTLCache[str, Tuple[bool, float]] = TTLCache(
            maxsize=max_size, ttl=ttl_seconds
        )
        self._stats = CacheStats()
        self._lock = Lock()
        self._ttl_seconds = ttl_seconds
        self._max_size = max_size

    def get(
        self, condition_uuid: str, context: Dict[str, Any]
    ) -> Optional[Tuple[bool, float]]:
        key = self._generate_cache_key(condition_uuid, self._hash_context(context))
        with self._lock:
            try:
                if key in self._cache:
                    self._stats.hits += 1
                    return self._cache[key]
                self._stats.misses += 1
                return None
            except KeyError:
                self._stats.misses += 1
                return None

    def set(
        self,
        condition_uuid: str,
        context: Dict[str, Any],
        result: bool,
        evaluation_time_ms: float,
    ) -> None:
        key = self._generate_cache_key(condition_uuid, self._hash_context(context))
        with self._lock:
            old_size = len(self._cache)
            self._cache[key] = (result, evaluation_time_ms)
            self._stats.total_keys = len(self._cache)
            if len(self._cache) < old_size:
                self._stats.evictions += old_size - len(self._cache)

    def invalidate_condition(self, condition_uuid: str) -> int:
        with self._lock:
            keys = [
                k
                for k in list(self._cache.keys())
                if k.startswith(f"{condition_uuid}:")
            ]
            for k in keys:
                del self._cache[k]
            self._stats.evictions += len(keys)
            self._stats.total_keys = len(self._cache)
            return len(keys)

    def clear(self) -> None:
        with self._lock:
            old_size = len(self._cache)
            self._cache.clear()
            self._stats.evictions += old_size
            self._stats.total_keys = 0

    def get_stats(self) -> CacheStats:
        with self._lock:
            import sys

            memory_bytes = sys.getsizeof(self._cache)
            for key, value in self._cache.items():
                memory_bytes += sys.getsizeof(key) + sys.getsizeof(value)
            self._stats.memory_bytes = memory_bytes
            return CacheStats(**self._stats.__dict__)

    def warmup(self, conditions_and_contexts: list) -> None:
        for condition_uuid, context, result, time_ms in conditions_and_contexts:
            self.set(condition_uuid, context, result, time_ms)


class HistoricalEvaluationCache(TTLEvaluationCache):
    """TTL cache variant that tracks usage frequency for historical patterns."""

    def __init__(self, ttl_seconds: int = 3600, max_size: int = 5000):
        super().__init__(ttl_seconds=ttl_seconds, max_size=max_size)
        self._frequency: Dict[str, int] = {}

    def get(
        self, condition_uuid: str, context: Dict[str, Any]
    ) -> Optional[Tuple[bool, float]]:
        result = super().get(condition_uuid, context)
        if result is not None:
            key = self._generate_cache_key(condition_uuid, self._hash_context(context))
            self._frequency[key] = self._frequency.get(key, 0) + 1
        return result

    def get_hot_keys(self, threshold: int = 3) -> Dict[str, int]:
        return {k: v for k, v in self._frequency.items() if v >= threshold}


class NegativeCache(_BaseCache):
    """Bloom-like negative cache with hashed buckets + exact check."""

    def __init__(self, max_entries: int = 10000, bucket_count: int = 2048):
        self._cache: Dict[str, bool] = {}
        self._buckets = [False] * max(bucket_count, 128)
        self._stats = CacheStats()
        self._lock = Lock()
        self._max_entries = max_entries

    def _bucket_indexes(self, key: str) -> Tuple[int, int, int]:
        digest = hashlib.sha256(key.encode()).hexdigest()
        cap = len(self._buckets)
        return (
            int(digest[:8], 16) % cap,
            int(digest[8:16], 16) % cap,
            int(digest[16:24], 16) % cap,
        )

    def is_always_false(self, condition_uuid: str, context: Dict[str, Any]) -> bool:
        key = self._generate_cache_key(condition_uuid, self._hash_context(context))
        with self._lock:
            buckets = self._bucket_indexes(key)
            probable = all(self._buckets[idx] for idx in buckets)
            if not probable:
                self._stats.misses += 1
                return False
            if key in self._cache:
                self._stats.hits += 1
                return self._cache[key]
            self._stats.misses += 1
            return False

    def mark_always_false(self, condition_uuid: str, context: Dict[str, Any]) -> None:
        key = self._generate_cache_key(condition_uuid, self._hash_context(context))
        with self._lock:
            if len(self._cache) >= self._max_entries:
                oldest = next(iter(self._cache))
                self._cache.pop(oldest, None)
                self._stats.evictions += 1
            for idx in self._bucket_indexes(key):
                self._buckets[idx] = True
            self._cache[key] = True
            self._stats.total_keys = len(self._cache)

    def invalidate_condition(self, condition_uuid: str) -> int:
        with self._lock:
            keys = [k for k in self._cache if k.startswith(f"{condition_uuid}:")]
            for k in keys:
                self._cache.pop(k, None)
            self._stats.evictions += len(keys)
            self._stats.total_keys = len(self._cache)
            return len(keys)

    def clear(self) -> None:
        with self._lock:
            old_size = len(self._cache)
            self._cache.clear()
            self._buckets = [False] * len(self._buckets)
            self._stats.evictions += old_size
            self._stats.total_keys = 0

    def get_stats(self) -> CacheStats:
        with self._lock:
            import sys

            memory_bytes = sys.getsizeof(self._cache) + sys.getsizeof(self._buckets)
            for key, value in self._cache.items():
                memory_bytes += sys.getsizeof(key) + sys.getsizeof(value)
            self._stats.memory_bytes = memory_bytes
            return CacheStats(**self._stats.__dict__)


class CacheInvalidationManager:
    def __init__(self):
        self._request_caches: Dict[str, RequestLevelCache] = {}
        self._ttl_cache: Optional[TTLEvaluationCache] = None
        self._historical_cache: Optional[HistoricalEvaluationCache] = None
        self._negative_cache: Optional[NegativeCache] = None
        self._lock = Lock()

    def register_request_cache(self, request_id: str, cache: RequestLevelCache) -> None:
        with self._lock:
            self._request_caches[request_id] = cache

    def register_ttl_cache(self, cache: TTLEvaluationCache) -> None:
        with self._lock:
            self._ttl_cache = cache

    def register_historical_cache(self, cache: HistoricalEvaluationCache) -> None:
        with self._lock:
            self._historical_cache = cache

    def register_negative_cache(self, cache: NegativeCache) -> None:
        with self._lock:
            self._negative_cache = cache

    def invalidate_condition(self, condition_uuid: str) -> Dict[str, int]:
        with self._lock:
            result = {"request": 0, "ttl": 0, "historical": 0, "negative": 0}
            if self._ttl_cache:
                result["ttl"] = self._ttl_cache.invalidate_condition(condition_uuid)
            if self._historical_cache:
                result["historical"] = self._historical_cache.invalidate_condition(
                    condition_uuid
                )
            if self._negative_cache:
                result["negative"] = self._negative_cache.invalidate_condition(
                    condition_uuid
                )
            for cache in self._request_caches.values():
                result["request"] += cache.invalidate_condition(condition_uuid)
            return result

    def cleanup_request_cache(self, request_id: str) -> None:
        with self._lock:
            self._request_caches.pop(request_id, None)


_global_ttl_cache: Optional[TTLEvaluationCache] = None
_global_historical_cache: Optional[HistoricalEvaluationCache] = None
_global_negative_cache: Optional[NegativeCache] = None
_global_invalidation_manager: Optional[CacheInvalidationManager] = None


def initialize_global_caches(
    ttl_seconds: int = 300,
    ttl_max_size: int = 1000,
    negative_cache_max_entries: int = 10000,
) -> None:
    global \
        _global_ttl_cache, \
        _global_historical_cache, \
        _global_negative_cache, \
        _global_invalidation_manager

    _global_ttl_cache = TTLEvaluationCache(ttl_seconds, ttl_max_size)
    _global_historical_cache = HistoricalEvaluationCache(
        ttl_seconds=ttl_seconds * 4, max_size=ttl_max_size * 2
    )
    _global_negative_cache = NegativeCache(negative_cache_max_entries)
    _global_invalidation_manager = CacheInvalidationManager()
    _global_invalidation_manager.register_ttl_cache(_global_ttl_cache)
    _global_invalidation_manager.register_historical_cache(_global_historical_cache)
    _global_invalidation_manager.register_negative_cache(_global_negative_cache)


def get_global_ttl_cache() -> Optional[TTLEvaluationCache]:
    return _global_ttl_cache


def get_global_historical_cache() -> Optional[HistoricalEvaluationCache]:
    return _global_historical_cache


def get_global_negative_cache() -> Optional[NegativeCache]:
    return _global_negative_cache


def get_global_invalidation_manager() -> Optional[CacheInvalidationManager]:
    return _global_invalidation_manager
