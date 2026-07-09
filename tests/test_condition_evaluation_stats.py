from app.config import BaseConfig
from app.models.condition_management import ConditionEvaluationStat
from app.services.condition_management_monitoring import (
    ensure_monitoring_stats_retention_index,
)


def test_condition_evaluation_stats_use_ttl_retention():
    ensure_monitoring_stats_retention_index(BaseConfig.MONITORING_STATS_RETENTION_DAYS)
    ttl_indexes = [
        index
        for index in ConditionEvaluationStat._get_collection()
        .index_information()
        .values()
        if index.get("key") == [("created_at", 1)]
    ]

    assert ttl_indexes, "expected a TTL index on created_at"
    assert ttl_indexes[0]["expireAfterSeconds"] == 60 * 60 * 24 * 30
