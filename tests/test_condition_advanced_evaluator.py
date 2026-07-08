from datetime import datetime, timedelta

import pytest

from app.models.form import Condition
from app.services.condition_evaluator import (
    ConditionEvaluationError,
    ConditionEvaluator,
)


def test_temporal_created_within_days():
    c = Condition(
        uuid="t1",
        conditionType="temporal",
        targetField="created_at",
        operator="created_within_days",
        operands=["2"],
        isActive=True,
    )
    ctx = {"created_at": (datetime.utcnow() - timedelta(days=1)).isoformat()}
    assert ConditionEvaluator(ctx).evaluate(c) is True


def test_arithmetic_condition_uses_safe_dsl():
    c = Condition(
        uuid="a1",
        conditionType="arithmetic",
        expression="sum(scores) >= 60",
        isActive=True,
    )
    assert ConditionEvaluator({"scores": [10, 20, 30]}).evaluate(c) is True


def test_set_condition_subset():
    c = Condition(
        uuid="s1",
        conditionType="set",
        targetField="roles",
        operator="superset",
        operands=["admin", "user"],
        isActive=True,
    )
    assert ConditionEvaluator({"roles": ["admin", "user", "owner"]}).evaluate(c) is True


def test_operator_between():
    c = Condition(
        uuid="cmp1",
        conditionType="comparison",
        targetField="score",
        operator="between",
        operands=["10", "20"],
        isActive=True,
    )
    assert ConditionEvaluator({"score": 15}).evaluate(c) is True


def test_cycle_detection(app_context):
    c1 = Condition(
        uuid="cy1", conditionType="logical", logicalJoinType="AND", isActive=True
    )
    c2 = Condition(
        uuid="cy2", conditionType="logical", logicalJoinType="AND", isActive=True
    )
    c1.subConditions = [c2]
    c2.subConditions = [c1]
    c1.save()
    c2.save()
    with pytest.raises(ConditionEvaluationError):
        ConditionEvaluator({}).evaluate(c1)


def test_complexity_and_observability():
    c = Condition(
        uuid="obs1",
        conditionType="comparison",
        targetField="value",
        operator="equals",
        operands=["ok"],
        isActive=True,
    )
    ev = ConditionEvaluator({"value": "ok"}, enable_tracing=True)
    assert ev.evaluate(c) is True
    snap = ev.get_observability_snapshot()
    assert snap["execution_path"] == ["obs1"]
    assert ev.complexity_score(c) >= 1
