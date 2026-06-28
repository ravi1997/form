"""
scheduler.py
------------
Background scheduler for automatic analysis runs.

Each analysis definition may include a 'schedule' field:

  "schedule": {
    "enabled": true,
    "cron": "0 8 * * 1",        // standard 5-field cron (min hr dom mon dow)
    "timezone": "Asia/Kolkata"   // optional, defaults to UTC
  }

Cron cheatsheet:
  "0 8 * * *"    → every day at 08:00
  "0 8 * * 1"    → every Monday at 08:00
  "0 */6 * * *"  → every 6 hours
  "0 8 1 * *"    → 1st of every month at 08:00

On app startup, all definitions with schedule.enabled=true are auto-registered.
Results are saved to the analysis_results collection and webhooks are fired.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from bson import ObjectId

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


# ---------------------------------------------------------------------------
# Scheduler singleton
# ---------------------------------------------------------------------------

def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(daemon=True)
    return _scheduler


def start_scheduler():
    sched = get_scheduler()
    if not sched.running:
        sched.start()
        logger.info("APScheduler started.")


def shutdown_scheduler():
    sched = get_scheduler()
    if sched.running:
        sched.shutdown(wait=False)
        logger.info("APScheduler stopped.")


# ---------------------------------------------------------------------------
# Job function (runs in a background thread — creates its own DB connection)
# ---------------------------------------------------------------------------

def _run_scheduled_analysis(
    definition_id: str,
    mongo_uri: str,
    db_name: str,
    definitions_col_name: str,
    results_col_name: str,
    webhooks_col_name: str,
):
    """Execute a stored analysis definition and cache the result + fire webhooks."""
    from pymongo import MongoClient
    from analysis_engine import run_analysis
    from webhook_dispatcher import fire_webhooks

    client = MongoClient(mongo_uri)
    db = client[db_name]
    definitions_col = db[definitions_col_name]
    results_col = db[results_col_name]
    webhooks_col = db[webhooks_col_name]

    doc = definitions_col.find_one({"_id": ObjectId(definition_id)})
    if not doc:
        logger.warning(f"Scheduled analysis '{definition_id}' not found — skipping.")
        return

    analysis_name = doc.get("name", definition_id)
    run_at = datetime.now(timezone.utc)

    # Enforce multi-tenant isolation
    org_id = doc.get("organization_id")
    if org_id:
        doc.setdefault("filters", [])
        doc["filters"].append({"field": "organization_id", "operator": "eq", "value": org_id})

    try:
        result = run_analysis(db, doc)

        results_col.insert_one({
            "definition_id": ObjectId(definition_id),
            "run_at": run_at,
            "trigger": "scheduled",
            "extra_filters": [],
            "result": result,
        })

        fire_webhooks(
            webhooks_col, definition_id, analysis_name,
            result, "success",
        )
        logger.info(f"Scheduled run of '{analysis_name}' succeeded.")

    except Exception as exc:
        logger.error(f"Scheduled run of '{analysis_name}' failed: {exc}")

        results_col.insert_one({
            "definition_id": ObjectId(definition_id),
            "run_at": run_at,
            "trigger": "scheduled",
            "extra_filters": [],
            "error": str(exc),
        })

        try:
            fire_webhooks(
                webhooks_col, definition_id, analysis_name,
                None, "failed", str(exc),
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Registration helpers
# ---------------------------------------------------------------------------

def _job_id(definition_id: str) -> str:
    return f"analysis_{definition_id}"


def register_schedule(
    definition_id: str,
    schedule_cfg: dict,
    mongo_uri: str,
    db_name: str,
    definitions_col_name: str,
    results_col_name: str,
    webhooks_col_name: str,
):
    """
    Register (or replace) a cron job for an analysis definition.
    If schedule_cfg is empty or schedule_cfg['enabled'] is False, the job is removed.
    """
    scheduler = get_scheduler()
    job_id = _job_id(definition_id)

    # Always remove old job first
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    if not schedule_cfg or not schedule_cfg.get("enabled", False):
        return  # disabled — don't register

    cron_expr = schedule_cfg.get("cron", "0 8 * * *")
    tz = schedule_cfg.get("timezone", "UTC")

    parts = cron_expr.split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron '{cron_expr}' — must have exactly 5 fields.")

    minute, hour, day, month, dow = parts
    trigger = CronTrigger(
        minute=minute, hour=hour, day=day,
        month=month, day_of_week=dow,
        timezone=tz,
    )

    scheduler.add_job(
        _run_scheduled_analysis,
        trigger=trigger,
        id=job_id,
        name=f"Analysis: {definition_id}",
        kwargs={
            "definition_id": definition_id,
            "mongo_uri": mongo_uri,
            "db_name": db_name,
            "definitions_col_name": definitions_col_name,
            "results_col_name": results_col_name,
            "webhooks_col_name": webhooks_col_name,
        },
        replace_existing=True,
    )
    logger.info(f"Scheduled '{definition_id}': '{cron_expr}' ({tz})")


def deregister_schedule(definition_id: str):
    """Remove a scheduled job for an analysis definition."""
    scheduler = get_scheduler()
    job_id = _job_id(definition_id)
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        logger.info(f"Deregistered schedule for '{definition_id}'.")


def list_scheduled_jobs() -> list[dict]:
    """Return metadata of all active scheduled jobs."""
    return [
        {
            "job_id": job.id,
            "name": job.name,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
        }
        for job in get_scheduler().get_jobs()
    ]


def load_all_schedules(
    definitions_col,
    mongo_uri: str,
    db_name: str,
    definitions_col_name: str,
    results_col_name: str,
    webhooks_col_name: str,
):
    """Called once on startup: re-register all enabled schedules from MongoDB."""
    docs = list(definitions_col.find({"schedule.enabled": True}))
    count = 0
    for doc in docs:
        try:
            register_schedule(
                str(doc["_id"]),
                doc["schedule"],
                mongo_uri, db_name,
                definitions_col_name, results_col_name, webhooks_col_name,
            )
            count += 1
        except Exception as exc:
            logger.error(f"Failed to register schedule for {doc['_id']}: {exc}")
    logger.info(f"Loaded {count} scheduled job(s) on startup.")
