"""Tests for condition evaluation service."""

import pytest
from app.models.form import Condition
from app.services.condition_evaluator import (
    ConditionEvaluator,
    ConditionEvaluationContext,
    ConditionEvaluationError,
)


class TestRegexConditionEvaluation:
    """Tests for regex condition evaluation."""

    def test_regex_condition_matches_pattern(self):
        """Regex condition should match valid patterns."""
        condition = Condition(
            uuid="cond-1",
            conditionType="regex",
            targetField="value",
            expression=r"^\d{3}-\d{4}$",
            isActive=True,
        )
        context = {"value": "123-4567"}
        evaluator = ConditionEvaluator(context)
        assert evaluator.evaluate(condition) is True

    def test_regex_condition_does_not_match_pattern(self):
        """Regex condition should return false for non-matching patterns."""
        condition = Condition(
            uuid="cond-1",
            conditionType="regex",
            targetField="value",
            expression=r"^\d{3}-\d{4}$",
            isActive=True,
        )
        context = {"value": "abc-defg"}
        evaluator = ConditionEvaluator(context)
        assert evaluator.evaluate(condition) is False

    def test_regex_condition_with_negation(self):
        """Regex condition with negation should return opposite result."""
        condition = Condition(
            uuid="cond-1",
            conditionType="regex",
            targetField="value",
            expression=r"^\d{3}-\d{4}$",
            isActive=True,
            isNegated=True,
        )
        context = {"value": "abc-defg"}
        evaluator = ConditionEvaluator(context)
        assert evaluator.evaluate(condition) is True

    def test_regex_condition_with_inactive_flag(self):
        """Inactive condition should always return true."""
        condition = Condition(
            uuid="cond-1",
            conditionType="regex",
            targetField="value",
            expression=r"^\d{3}-\d{4}$",
            isActive=False,
        )
        context = {"value": "abc-defg"}
        evaluator = ConditionEvaluator(context)
        assert evaluator.evaluate(condition) is True

    def test_regex_condition_invalid_expression(self):
        """Invalid regex expression should raise error."""
        condition = Condition(
            uuid="cond-1",
            conditionType="regex",
            targetField="value",
            expression=r"[invalid(",
            isActive=True,
        )
        context = {"value": "test"}
        evaluator = ConditionEvaluator(context)
        with pytest.raises(ConditionEvaluationError):
            evaluator.evaluate(condition)

    def test_regex_condition_missing_field(self):
        """Regex condition should return false for missing field."""
        condition = Condition(
            uuid="cond-1",
            conditionType="regex",
            targetField="value",
            expression=r"^\d+$",
            isActive=True,
        )
        context = {}
        evaluator = ConditionEvaluator(context)
        assert evaluator.evaluate(condition) is False


class TestComparisonConditionEvaluation:
    """Tests for comparison condition evaluation."""

    def test_equals_operator(self):
        """Equals operator should compare values correctly."""
        condition = Condition(
            uuid="cond-1",
            conditionType="comparison",
            targetField="status",
            operator="equals",
            operands=["approved"],
            isActive=True,
        )
        context = {"status": "approved"}
        evaluator = ConditionEvaluator(context)
        assert evaluator.evaluate(condition) is True

    def test_not_equals_operator(self):
        """Not equals operator should work correctly."""
        condition = Condition(
            uuid="cond-1",
            conditionType="comparison",
            targetField="status",
            operator="not_equals",
            operands=["rejected"],
            isActive=True,
        )
        context = {"status": "approved"}
        evaluator = ConditionEvaluator(context)
        assert evaluator.evaluate(condition) is True

    def test_greater_than_operator(self):
        """Greater than operator should compare numbers."""
        condition = Condition(
            uuid="cond-1",
            conditionType="comparison",
            targetField="score",
            operator="greater_than",
            operands=["50"],
            isActive=True,
        )
        context = {"score": 75}
        evaluator = ConditionEvaluator(context)
        assert evaluator.evaluate(condition) is True

    def test_contains_operator(self):
        """Contains operator should find substring."""
        condition = Condition(
            uuid="cond-1",
            conditionType="comparison",
            targetField="text",
            operator="contains",
            operands=["hello"],
            isActive=True,
        )
        context = {"text": "hello world"}
        evaluator = ConditionEvaluator(context)
        assert evaluator.evaluate(condition) is True

    def test_starts_with_operator(self):
        """Starts with operator should check string prefix."""
        condition = Condition(
            uuid="cond-1",
            conditionType="comparison",
            targetField="name",
            operator="starts_with",
            operands=["John"],
            isActive=True,
        )
        context = {"name": "John Doe"}
        evaluator = ConditionEvaluator(context)
        assert evaluator.evaluate(condition) is True

    def test_ends_with_operator(self):
        """Ends with operator should check string suffix."""
        condition = Condition(
            uuid="cond-1",
            conditionType="comparison",
            targetField="email",
            operator="ends_with",
            operands=["@example.com"],
            isActive=True,
        )
        context = {"email": "user@example.com"}
        evaluator = ConditionEvaluator(context)
        assert evaluator.evaluate(condition) is True

    def test_is_empty_operator(self):
        """Is empty operator should detect empty values."""
        condition = Condition(
            uuid="cond-1",
            conditionType="comparison",
            targetField="value",
            operator="is_empty",
            isActive=True,
        )
        context = {"value": None}
        evaluator = ConditionEvaluator(context)
        assert evaluator.evaluate(condition) is True

    def test_is_not_empty_operator(self):
        """Is not empty operator should detect non-empty values."""
        condition = Condition(
            uuid="cond-1",
            conditionType="comparison",
            targetField="value",
            operator="is_not_empty",
            isActive=True,
        )
        context = {"value": "data"}
        evaluator = ConditionEvaluator(context)
        assert evaluator.evaluate(condition) is True

    def test_comparison_multiple_operands_or_logic(self):
        """Multiple operands should be OR'd together."""
        condition = Condition(
            uuid="cond-1",
            conditionType="comparison",
            targetField="status",
            operator="equals",
            operands=["approved", "submitted"],
            isActive=True,
        )
        context = {"status": "submitted"}
        evaluator = ConditionEvaluator(context)
        assert evaluator.evaluate(condition) is True


class TestLogicalConditionEvaluation:
    """Tests for logical condition evaluation."""

    def test_logical_and_all_true(self, app_context):
        """Logical AND should return true when all sub-conditions are true."""
        # Create sub-conditions
        sub_cond1 = Condition(
            uuid="sub-1",
            conditionType="comparison",
            targetField="status",
            operator="equals",
            operands=["approved"],
            isActive=True,
        )
        sub_cond1.save()

        sub_cond2 = Condition(
            uuid="sub-2",
            conditionType="comparison",
            targetField="score",
            operator="greater_than",
            operands=["50"],
            isActive=True,
        )
        sub_cond2.save()

        # Create logical condition
        condition = Condition(
            uuid="logical-1",
            conditionType="logical",
            logicalJoinType="AND",
            subConditions=[sub_cond1, sub_cond2],
            isActive=True,
        )
        condition.save()

        context = {"status": "approved", "score": 75}
        evaluator = ConditionEvaluator(context)
        assert evaluator.evaluate(condition) is True

    def test_logical_and_one_false(self, app_context):
        """Logical AND should return false when one sub-condition is false."""
        # Create sub-conditions
        sub_cond1 = Condition(
            uuid="sub-1",
            conditionType="comparison",
            targetField="status",
            operator="equals",
            operands=["approved"],
            isActive=True,
        )
        sub_cond1.save()

        sub_cond2 = Condition(
            uuid="sub-2",
            conditionType="comparison",
            targetField="score",
            operator="greater_than",
            operands=["80"],
            isActive=True,
        )
        sub_cond2.save()

        # Create logical condition
        condition = Condition(
            uuid="logical-1",
            conditionType="logical",
            logicalJoinType="AND",
            subConditions=[sub_cond1, sub_cond2],
            isActive=True,
        )
        condition.save()

        context = {"status": "approved", "score": 75}
        evaluator = ConditionEvaluator(context)
        assert evaluator.evaluate(condition) is False

    def test_logical_or_one_true(self, app_context):
        """Logical OR should return true when at least one sub-condition is true."""
        # Create sub-conditions
        sub_cond1 = Condition(
            uuid="sub-1",
            conditionType="comparison",
            targetField="status",
            operator="equals",
            operands=["rejected"],
            isActive=True,
        )
        sub_cond1.save()

        sub_cond2 = Condition(
            uuid="sub-2",
            conditionType="comparison",
            targetField="score",
            operator="greater_than",
            operands=["50"],
            isActive=True,
        )
        sub_cond2.save()

        # Create logical condition
        condition = Condition(
            uuid="logical-1",
            conditionType="logical",
            logicalJoinType="OR",
            subConditions=[sub_cond1, sub_cond2],
            isActive=True,
        )
        condition.save()

        context = {"status": "approved", "score": 75}
        evaluator = ConditionEvaluator(context)
        assert evaluator.evaluate(condition) is True

    def test_logical_or_all_false(self, app_context):
        """Logical OR should return false when all sub-conditions are false."""
        # Create sub-conditions
        sub_cond1 = Condition(
            uuid="sub-1",
            conditionType="comparison",
            targetField="status",
            operator="equals",
            operands=["rejected"],
            isActive=True,
        )
        sub_cond1.save()

        sub_cond2 = Condition(
            uuid="sub-2",
            conditionType="comparison",
            targetField="score",
            operator="greater_than",
            operands=["80"],
            isActive=True,
        )
        sub_cond2.save()

        # Create logical condition
        condition = Condition(
            uuid="logical-1",
            conditionType="logical",
            logicalJoinType="OR",
            subConditions=[sub_cond1, sub_cond2],
            isActive=True,
        )
        condition.save()

        context = {"status": "approved", "score": 75}
        evaluator = ConditionEvaluator(context)
        assert evaluator.evaluate(condition) is False


class TestDotNotationFieldAccess:
    """Tests for accessing nested fields using dot notation."""

    def test_simple_field_access(self):
        """Simple field access should work."""
        condition = Condition(
            uuid="cond-1",
            conditionType="comparison",
            targetField="value",
            operator="equals",
            operands=["test"],
            isActive=True,
        )
        context = {"value": "test"}
        evaluator = ConditionEvaluator(context)
        assert evaluator.evaluate(condition) is True

    def test_nested_field_access(self):
        """Nested field access with dot notation should work."""
        condition = Condition(
            uuid="cond-1",
            conditionType="comparison",
            targetField="metadata.priority",
            operator="equals",
            operands=["high"],
            isActive=True,
        )
        context = {"metadata": {"priority": "high", "tags": ["urgent"]}}
        evaluator = ConditionEvaluator(context)
        assert evaluator.evaluate(condition) is True

    def test_deeply_nested_field_access(self):
        """Deeply nested field access should work."""
        condition = Condition(
            uuid="cond-1",
            conditionType="comparison",
            targetField="response.metadata.priority",
            operator="equals",
            operands=["critical"],
            isActive=True,
        )
        context = {"response": {"metadata": {"priority": "critical"}}}
        evaluator = ConditionEvaluator(context)
        assert evaluator.evaluate(condition) is True

    def test_missing_nested_field_returns_none(self):
        """Missing nested field should return None and evaluate to false."""
        condition = Condition(
            uuid="cond-1",
            conditionType="comparison",
            targetField="metadata.missing",
            operator="equals",
            operands=["value"],
            isActive=True,
        )
        context = {"metadata": {"other": "value"}}
        evaluator = ConditionEvaluator(context)
        assert evaluator.evaluate(condition) is False


class TestConditionEvaluationContext:
    """Tests for ConditionEvaluationContext helper."""

    def test_from_response_item(self):
        """Should build context from response item."""
        response_item = {
            "value": "test",
            "status": "pending",
            "metadata": {"key": "val"},
            "validation_errors": ["error1"],
            "score": 85,
        }
        context = ConditionEvaluationContext.from_response_item(response_item)
        assert context["value"] == "test"
        assert context["status"] == "pending"
        assert context["metadata"]["key"] == "val"
        assert "error1" in context["validation_errors"]
        assert context["score"] == 85

    def test_from_form_response(self):
        """Should build context from form response."""
        form_response = {
            "status": "submitted",
            "workflow_state": "in_review",
            "metadata": {"key": "val"},
            "responses": {"q1": "answer1"},
        }
        context = ConditionEvaluationContext.from_form_response(form_response)
        assert context["status"] == "submitted"
        assert context["workflow_state"] == "in_review"
        assert context["metadata"]["key"] == "val"

    def test_merged_context(self):
        """Should merge context from multiple sources."""
        response_item = {"value": "test", "status": "pending"}
        form_response = {"workflow_state": "in_review"}
        extra = {"custom": "data"}

        context = ConditionEvaluationContext.merged(
            response_item=response_item,
            form_response=form_response,
            extra=extra,
        )

        assert context["value"] == "test"
        assert context["status"] == "pending"
        assert context["workflow_state"] == "in_review"
        assert context["custom"] == "data"


class TestEvaluateAllConditions:
    """Tests for evaluating multiple conditions."""

    def test_evaluate_all_and_logic(self):
        """Should AND multiple conditions."""
        cond1 = Condition(
            uuid="c1",
            conditionType="comparison",
            targetField="status",
            operator="equals",
            operands=["approved"],
            isActive=True,
        )
        cond2 = Condition(
            uuid="c2",
            conditionType="comparison",
            targetField="score",
            operator="greater_than",
            operands=["50"],
            isActive=True,
        )
        context = {"status": "approved", "score": 75}
        evaluator = ConditionEvaluator(context)

        result = evaluator.evaluate_all([cond1, cond2], logical_join="AND")
        assert result is True

    def test_evaluate_all_or_logic(self):
        """Should OR multiple conditions."""
        cond1 = Condition(
            uuid="c1",
            conditionType="comparison",
            targetField="status",
            operator="equals",
            operands=["rejected"],
            isActive=True,
        )
        cond2 = Condition(
            uuid="c2",
            conditionType="comparison",
            targetField="score",
            operator="greater_than",
            operands=["50"],
            isActive=True,
        )
        context = {"status": "approved", "score": 75}
        evaluator = ConditionEvaluator(context)

        result = evaluator.evaluate_all([cond1, cond2], logical_join="OR")
        assert result is True

    def test_evaluate_all_empty_list(self):
        """Should return true for empty condition list."""
        context = {}
        evaluator = ConditionEvaluator(context)
        result = evaluator.evaluate_all([], logical_join="AND")
        assert result is True


class TestActionConditionIntegration:
    """Tests for action visibility and enabled conditions."""

    def test_visibility_condition_check(self, app_context):
        """Visibility condition should control action visibility."""
        # Create a visibility condition
        vis_condition = Condition(
            uuid="vis-1",
            conditionType="comparison",
            targetField="status",
            operator="equals",
            operands=["in_review"],
            isActive=True,
        )
        vis_condition.save()

        # Context where condition is true
        context = {"status": "in_review"}
        evaluator = ConditionEvaluator(context)
        assert evaluator.evaluate(vis_condition) is True

        # Context where condition is false
        context = {"status": "draft"}
        evaluator = ConditionEvaluator(context)
        assert evaluator.evaluate(vis_condition) is False

    def test_enabled_condition_check(self, app_context):
        """Enabled condition should control action enablement."""
        # Create an enabled condition
        enabled_condition = Condition(
            uuid="en-1",
            conditionType="comparison",
            targetField="score",
            operator="greater_than",
            operands=["70"],
            isActive=True,
        )
        enabled_condition.save()

        # Context where condition is true
        context = {"score": 85}
        evaluator = ConditionEvaluator(context)
        assert evaluator.evaluate(enabled_condition) is True

        # Context where condition is false
        context = {"score": 50}
        evaluator = ConditionEvaluator(context)
        assert evaluator.evaluate(enabled_condition) is False
