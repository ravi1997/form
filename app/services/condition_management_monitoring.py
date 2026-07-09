from __future__ import annotations

from collections import Counter, defaultdict
from functools import lru_cache
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

from app.models.condition_management import ConditionEvaluationStat
from app.models.form import Condition
from app.services.condition_evaluator import ConditionEvaluator
from app.services.condition_management_analysis import invalidate_condition_usage_cache
from app.services.condition_management_graph import (
    build_dependency_graph,
    detect_circular_references,
    invalidate_dependency_graph_cache,
)

DEFAULT_MONITORING_STATS_RETENTION_DAYS = 30


def record_evaluation_stat(
    condition: Condition, matched: bool, duration_ms: float, endpoint: str = ""
) -> None:
    ConditionEvaluationStat(
        condition_uuid=condition.uuid,
        endpoint=endpoint,
        matched=matched,
        duration_ms=duration_ms,
        operator=condition.operator,
        condition_type=condition.conditionType,
    ).save()
    invalidate_monitoring_cache()


def ensure_monitoring_stats_retention_index(
    retention_days: int = DEFAULT_MONITORING_STATS_RETENTION_DAYS,
) -> None:
    expire_after_seconds = max(1, int(retention_days)) * 24 * 60 * 60
    collection = ConditionEvaluationStat._get_collection()
    collection.create_index(
        [("created_at", 1)],
        name="created_at_ttl",
        expireAfterSeconds=expire_after_seconds,
    )


@lru_cache(maxsize=32)
def _get_monitoring_snapshot_cached(window_days: int = 30) -> Dict[str, Any]:
    since = datetime.now(timezone.utc) - timedelta(days=window_days)
    rows = ConditionEvaluationStat.objects(created_at__gte=since)

    usage: Counter[str] = Counter()
    matched: Counter[str] = Counter()
    durations: Dict[str, List[float]] = defaultdict(list)
    heatmap: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for row in rows:
        usage[row.condition_uuid] += 1
        if row.matched:
            matched[row.condition_uuid] += 1
        durations[row.condition_uuid].append(row.duration_ms)
        day_key = row.created_at.strftime("%Y-%m-%d")
        heatmap[day_key][row.condition_uuid] += 1

    all_condition_uuids = [c.uuid for c in Condition.objects]
    unused = [cid for cid in all_condition_uuids if usage[cid] == 0]
    most_used = usage.most_common(10)

    evaluation_stats = []
    for condition_uuid, count in usage.items():
        avg = sum(durations[condition_uuid]) / len(durations[condition_uuid])
        evaluation_stats.append(
            {
                "condition_uuid": condition_uuid,
                "total_evaluations": count,
                "matched": matched[condition_uuid],
                "match_rate": matched[condition_uuid] / count if count else 0,
                "avg_duration_ms": round(avg, 3),
            }
        )

    graph = []
    for condition in Condition.objects:
        for sub in condition.subConditions or []:
            ref = sub.fetch() if hasattr(sub, "fetch") else sub
            if ref and ref.uuid:
                graph.append({"from": condition.uuid, "to": ref.uuid})

    return {
        "graph": graph,
        "heatmap": {day: dict(values) for day, values in heatmap.items()},
        "unused": unused,
        "most_used": [
            {"condition_uuid": cid, "count": count} for cid, count in most_used
        ],
        "evaluation_stats": evaluation_stats,
    }


def invalidate_monitoring_cache() -> None:
    _get_monitoring_snapshot_cached.cache_clear()
    invalidate_dependency_graph_cache()
    invalidate_condition_usage_cache()


def get_monitoring_snapshot(window_days: int = 30) -> Dict[str, Any]:
    return _get_monitoring_snapshot_cached(window_days)


def operator_metadata() -> Dict[str, Dict[str, Any]]:
    return dict(ConditionEvaluator.OPERATOR_METADATA)


def monitoring_dashboard_snapshot() -> Dict[str, Any]:
    snapshot = get_monitoring_snapshot()
    graph = build_dependency_graph()
    return {
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "total_conditions": Condition.objects.count(),
        "active_conditions": Condition.objects(isActive=True).count(),
        "circular_references": detect_circular_references(graph),
        "dependency_graph": graph,
        "monitoring": snapshot,
    }
