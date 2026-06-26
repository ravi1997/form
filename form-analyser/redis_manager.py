"""
redis_manager.py
----------------
Wrapper around Redis cache and RQ queue interactions.
"""

from __future__ import annotations
import json
import logging
from redis import Redis
from rq import Queue
from rq.job import Job

logger = logging.getLogger(__name__)

_redis_client: Redis | None = None

def get_redis_client(redis_url: str) -> Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis.from_url(redis_url)
    return _redis_client


def get_cached_result(redis_url: str, definition_id: str) -> dict | None:
    """Retrieve cached analysis result from Redis."""
    try:
        r = get_redis_client(redis_url)
        cache_key = f"cache:analysis:{definition_id}"
        cached = r.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception as e:
        logger.error(f"Redis cache read error: {e}")
    return None


def set_cached_result(redis_url: str, definition_id: str, result: dict, ttl: int = 300) -> bool:
    """Store analysis result in Redis cache."""
    try:
        r = get_redis_client(redis_url)
        cache_key = f"cache:analysis:{definition_id}"
        r.setex(cache_key, ttl, json.dumps(result))
        return True
    except Exception as e:
        logger.error(f"Redis cache write error: {e}")
    return False


def delete_cached_result(redis_url: str, definition_id: str) -> bool:
    """Evict cached analysis result from Redis."""
    try:
        r = get_redis_client(redis_url)
        cache_key = f"cache:analysis:{definition_id}"
        r.delete(cache_key)
        return True
    except Exception as e:
        logger.error(f"Redis cache delete error: {e}")
    return False


def enqueue_analysis_run(
    redis_url: str,
    definition_id: str,
    mongo_uri: str,
    db_name: str,
    definitions_col: str,
    results_col: str,
    webhooks_col: str,
    extra_filters: list | None = None
) -> str:
    """Enqueue analysis run task into RQ."""
    r = get_redis_client(redis_url)
    q = Queue("analysis", connection=r)
    
    from tasks import run_analysis_task
    
    job = q.enqueue(
        run_analysis_task,
        args=(
            definition_id,
            mongo_uri,
            db_name,
            definitions_col,
            results_col,
            webhooks_col,
            redis_url
        ),
        kwargs={"extra_filters": extra_filters},
        job_timeout="10m"
    )
    return job.get_id()


def get_job_status(redis_url: str, job_id: str) -> dict:
    """Fetch status and result of a background job."""
    r = get_redis_client(redis_url)
    try:
        job = Job.fetch(job_id, connection=r)
        return {
            "job_id": job_id,
            "status": job.get_status(),
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "ended_at": job.ended_at.isoformat() if job.ended_at else None,
            "result": job.result if job.is_finished else None,
            "error": job.exc_info if job.is_failed else None
        }
    except Exception as e:
        return {"job_id": job_id, "status": "unknown", "error": str(e)}
