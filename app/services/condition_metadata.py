from __future__ import annotations

from typing import Any, Dict, Set


CONDITION_OPERATOR_METADATA: Dict[str, Dict[str, Any]] = {
    "regex": {"operators": {"regex"}},
    "comparison": {
        "operators": {
            "equals",
            "not_equals",
            "greater_than",
            "less_than",
            "greater_than_or_equals",
            "less_than_or_equals",
            "contains",
            "not_contains",
            "starts_with",
            "ends_with",
            "is_empty",
            "is_not_empty",
            "in_list",
            "not_in_list",
            "between",
            "matches_any",
            "matches_all",
            "contains_any",
            "contains_all",
        }
    },
    "logical": {"operators": set()},
    "custom": {"operators": set()},
    "dsl": {"operators": set()},
    "temporal": {
        "operators": {
            "created_within_days",
            "updated_within_days",
            "older_than_days",
            "duration_exceeds",
            "duration_less_than",
        }
    },
    "arithmetic": {"operators": set()},
    "set": {"operators": {"any", "all", "none", "subset", "superset", "intersects"}},
}


def allowed_operators(condition_type: str) -> Set[str]:
    return set(CONDITION_OPERATOR_METADATA.get(condition_type, {}).get("operators", set()))


def validate_condition_operator(condition_type: str, operator: str | None) -> None:
    if not operator:
        return

    allowed = allowed_operators(condition_type)
    if allowed and operator not in allowed:
        raise ValueError(
            f"Operator '{operator}' is not valid for conditionType '{condition_type}'"
        )

