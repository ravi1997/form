import pytest

from app.services.safe_dsl import (
    DSLValidationError,
    evaluate_expression,
    parse_and_validate_expression,
)


def test_safe_dsl_arithmetic_and_logical():
    context = {"a": 5, "b": 3, "arr": [1, 2, 3]}
    assert evaluate_expression("a + b >= 8 AND a IN [5,6]", context) is True


def test_safe_dsl_function_support():
    context = {"scores": [10, 20, 30]}
    assert evaluate_expression("average(scores) == 20", context) is True
    assert evaluate_expression("sum(scores) == 60", context) is True


def test_safe_dsl_rejects_unknown_function():
    with pytest.raises(DSLValidationError):
        parse_and_validate_expression("exec(cmd)")


def test_safe_dsl_rejects_bad_syntax():
    with pytest.raises(DSLValidationError):
        evaluate_expression("(a + 2", {"a": 1})
