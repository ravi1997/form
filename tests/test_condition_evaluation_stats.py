from app.models.condition_management import ConditionEvaluationStat


def test_condition_evaluation_stats_use_ttl_retention():
    ttl_indexes = [
        index
        for index in ConditionEvaluationStat._meta["indexes"]
        if isinstance(index, dict) and index.get("fields") == ["created_at"]
    ]

    assert ttl_indexes, "expected a TTL index on created_at"
    assert ttl_indexes[0]["expireAfterSeconds"] == 60 * 60 * 24 * 30
