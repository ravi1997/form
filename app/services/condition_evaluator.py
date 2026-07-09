"""Condition evaluation service with caching, DSL, and observability."""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.models.form import Condition
from app.services.condition_cache import (
    RequestLevelCache,
    get_global_negative_cache,
    get_global_ttl_cache,
)
from app.services.safe_dsl import DSLTokenizer, DSLValidationError, evaluate_expression


class ConditionEvaluationError(Exception):
    pass


def _is_safe_custom_condition_expression(
    expression: str, allowed_keys: set[str]
) -> bool:
    tokens = DSLTokenizer().tokenize(expression)
    for index, token in enumerate(tokens):
        if token.kind != "ident":
            continue

        next_token = tokens[index + 1] if index + 1 < len(tokens) else None
        if next_token and next_token.kind == "op" and next_token.value == "(":
            # Function names are validated by the DSL engine itself.
            continue

        parts = token.value.split(".")
        if any(not part or part.startswith("__") for part in parts):
            return False
        if parts[0] not in allowed_keys:
            return False
    return True


@lru_cache(maxsize=256)
def _compile_regex_pattern(pattern: str):
    return re.compile(pattern)


def get_regex_cache_stats() -> Dict[str, Any]:
    cache_info = _compile_regex_pattern.cache_info()
    total = cache_info.hits + cache_info.misses
    return {
        "hits": cache_info.hits,
        "misses": cache_info.misses,
        "maxsize": cache_info.maxsize,
        "currsize": cache_info.currsize,
        "hit_ratio_percent": round(
            (cache_info.hits / total * 100) if total else 0.0, 2
        ),
    }


class ConditionEvaluator:
    """Evaluates conditions with caching, metrics, and execution traces."""

    COMPARISON_OPERATORS = {
        "equals": lambda a, b: a == b,
        "not_equals": lambda a, b: a != b,
        "greater_than": lambda a, b: a > b,
        "less_than": lambda a, b: a < b,
        "greater_than_or_equals": lambda a, b: a >= b,
        "less_than_or_equals": lambda a, b: a <= b,
        "contains": lambda a, b: (
            b in a if isinstance(a, (str, list, set, tuple)) else False
        ),
        "not_contains": lambda a, b: (
            b not in a if isinstance(a, (str, list, set, tuple)) else True
        ),
        "starts_with": lambda a, b: (
            str(a).startswith(str(b)) if a is not None else False
        ),
        "ends_with": lambda a, b: str(a).endswith(str(b)) if a is not None else False,
        "is_empty": lambda a, _b: a in (None, "", [], {}, ()),
        "is_not_empty": lambda a, _b: a not in (None, "", [], {}, ()),
        "in_list": lambda a, b: a in b if isinstance(b, (list, set, tuple)) else False,
        "not_in_list": lambda a, b: (
            a not in b if isinstance(b, (list, set, tuple)) else True
        ),
        "between": lambda a, b: (
            isinstance(b, (list, tuple)) and len(b) == 2 and b[0] <= a <= b[1]
        ),
        "matches_any": lambda a, b: (
            isinstance(b, (list, tuple, set)) and any(str(a) == str(i) for i in b)
        ),
        "matches_all": lambda a, b: (
            isinstance(a, (list, tuple, set))
            and isinstance(b, (list, tuple, set))
            and all(i in a for i in b)
        ),
        "regex": lambda a, b: (
            bool(re.search(str(b), str(a)))
            if a is not None and b is not None
            else False
        ),
        "contains_any": lambda a, b: (
            isinstance(a, (list, tuple, set, str))
            and isinstance(b, (list, tuple, set))
            and any(i in a for i in b)
        ),
        "contains_all": lambda a, b: (
            isinstance(a, (list, tuple, set, str))
            and isinstance(b, (list, tuple, set))
            and all(i in a for i in b)
        ),
    }

    OPERATOR_METADATA: Dict[str, Dict[str, Any]] = {
        "equals": {"types": ["any"], "operands": 1},
        "not_equals": {"types": ["any"], "operands": 1},
        "greater_than": {"types": ["number", "datetime"], "operands": 1},
        "less_than": {"types": ["number", "datetime"], "operands": 1},
        "greater_than_or_equals": {"types": ["number", "datetime"], "operands": 1},
        "less_than_or_equals": {"types": ["number", "datetime"], "operands": 1},
        "contains": {"types": ["string", "list"], "operands": 1},
        "not_contains": {"types": ["string", "list"], "operands": 1},
        "starts_with": {"types": ["string"], "operands": 1},
        "ends_with": {"types": ["string"], "operands": 1},
        "is_empty": {"types": ["any"], "operands": 0},
        "is_not_empty": {"types": ["any"], "operands": 0},
        "in_list": {"types": ["any"], "operands": 1},
        "not_in_list": {"types": ["any"], "operands": 1},
        "between": {"types": ["number", "datetime"], "operands": 2},
        "matches_all": {"types": ["list"], "operands": 1},
        "matches_any": {"types": ["any"], "operands": 1},
        "regex": {"types": ["string"], "operands": 1},
        "contains_any": {"types": ["string", "list"], "operands": 1},
        "contains_all": {"types": ["string", "list"], "operands": 1},
    }

    CONDITION_TYPES = {
        "regex",
        "comparison",
        "logical",
        "custom",
        "dsl",
        "temporal",
        "arithmetic",
        "set",
    }

    def __init__(
        self,
        context: Optional[Dict[str, Any]] = None,
        enable_tracing: bool = False,
        enable_request_cache: bool = True,
        enable_timing: bool = True,
        max_depth: int = 10,
        max_operands: int = 50,
        timeout_ms: int = 1000,
        metrics_hook: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        external_provider: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
    ):
        self.context = context or {}
        self.enable_tracing = enable_tracing
        self.enable_request_cache = enable_request_cache
        self.enable_timing = enable_timing
        self.max_depth = max_depth
        self.max_operands = max_operands
        self.timeout_ms = timeout_ms
        self.metrics_hook = metrics_hook
        self.external_provider = external_provider

        self.trace: List[Dict[str, Any]] = []
        self._request_cache = RequestLevelCache() if enable_request_cache else None
        self._evaluation_times: Dict[str, float] = {}
        self._slow_conditions_threshold_ms = 100.0
        self._execution_path: List[str] = []

    def get_trace(self) -> List[Dict[str, Any]]:
        return self.trace

    def get_request_cache_stats(self):
        return self._request_cache.get_stats() if self._request_cache else None

    def get_evaluation_times(self) -> Dict[str, float]:
        return self._evaluation_times.copy()

    def get_slow_conditions(
        self, threshold_ms: Optional[float] = None
    ) -> List[Tuple[str, float]]:
        threshold = threshold_ms or self._slow_conditions_threshold_ms
        slow = [
            (uuid, ms) for uuid, ms in self._evaluation_times.items() if ms > threshold
        ]
        return sorted(slow, key=lambda i: i[1], reverse=True)

    def get_observability_snapshot(self) -> Dict[str, Any]:
        total_ms = sum(self._evaluation_times.values())
        return {
            "trace": self.trace,
            "evaluation_times": self._evaluation_times,
            "execution_path": self._execution_path,
            "slow_conditions": [
                {"condition_uuid": cid, "duration_ms": ms}
                for cid, ms in self.get_slow_conditions()
            ],
            "total_duration_ms": round(total_ms, 3),
        }

    def evaluate(
        self,
        condition: Optional[Condition],
        _depth: int = 0,
        _visited: Optional[set] = None,
    ) -> bool:
        if condition is None:
            return True
        if not condition.isActive:
            return True

        if _depth > self.max_depth:
            raise ConditionEvaluationError(
                f"Condition nesting exceeds max depth {self.max_depth}"
            )

        if _visited is None:
            _visited = set()
        if condition.uuid in _visited:
            raise ConditionEvaluationError(
                f"Circular reference detected at condition {condition.uuid}"
            )
        _visited.add(condition.uuid)

        start = time.perf_counter()
        cache_identity = self._cache_identity(condition)

        if self._request_cache:
            cached = self._request_cache.get(cache_identity, self.context)
            if cached is not None:
                result, cached_ms = cached
                if self.enable_timing:
                    self._evaluation_times[condition.uuid] = cached_ms
                self._record_trace(condition, result, event="request_cache_hit")
                return result

        ttl_cache = get_global_ttl_cache()
        if ttl_cache:
            ttl_hit = ttl_cache.get(cache_identity, self.context)
            if ttl_hit is not None:
                result, cached_ms = ttl_hit
                if self.enable_timing:
                    self._evaluation_times[condition.uuid] = cached_ms
                self._record_trace(condition, result, event="ttl_cache_hit")
                if self._request_cache:
                    self._request_cache.set(
                        cache_identity, self.context, result, cached_ms
                    )
                return result

        negative_cache = get_global_negative_cache()
        if (
            negative_cache
            and not condition.isNegated
            and negative_cache.is_always_false(cache_identity, self.context)
        ):
            self._record_trace(condition, False, event="negative_cache_hit")
            return False

        try:
            result = self._evaluate_condition(
                condition, _depth=_depth, _visited=_visited
            )
            if condition.isNegated:
                result = not result

            elapsed_ms = (time.perf_counter() - start) * 1000
            if elapsed_ms > self.timeout_ms:
                raise ConditionEvaluationError(
                    f"Condition evaluation timeout after {elapsed_ms:.2f}ms"
                )

            if self.enable_timing:
                self._evaluation_times[condition.uuid] = elapsed_ms

            if self._request_cache:
                self._request_cache.set(
                    cache_identity, self.context, result, elapsed_ms
                )
            if ttl_cache:
                ttl_cache.set(cache_identity, self.context, result, elapsed_ms)
            if negative_cache and not result:
                negative_cache.mark_always_false(cache_identity, self.context)

            if self.metrics_hook:
                self.metrics_hook(
                    "condition_evaluated",
                    {
                        "condition_uuid": condition.uuid,
                        "condition_type": condition.conditionType,
                        "duration_ms": elapsed_ms,
                        "result": result,
                    },
                )

            self._record_trace(condition, result, duration_ms=elapsed_ms)
            if elapsed_ms > self._slow_conditions_threshold_ms:
                self._record_trace(
                    condition, result, event="slow_evaluation", duration_ms=elapsed_ms
                )
            return result
        except DSLValidationError as exc:
            raise ConditionEvaluationError(str(exc)) from exc
        except (
            TypeError,
            ValueError,
            KeyError,
            ZeroDivisionError,
            ConditionEvaluationError,
        ) as exc:
            if isinstance(exc, ConditionEvaluationError):
                raise
            raise ConditionEvaluationError(
                f"Failed to evaluate condition {condition.uuid}: {exc}"
            ) from exc
        finally:
            _visited.discard(condition.uuid)

    @staticmethod
    def _cache_identity(condition: Condition) -> str:
        updated_at = getattr(condition, "updated_at", None)
        if isinstance(updated_at, datetime):
            return f"{condition.uuid}:{updated_at.timestamp()}"
        return str(condition.uuid)

    def evaluate_all(
        self, conditions: Optional[List[Condition]], logical_join: str = "AND"
    ) -> bool:
        if not conditions:
            return True

        join = logical_join.upper()
        if join not in {"AND", "OR"}:
            raise ConditionEvaluationError(f"Invalid logical join type: {logical_join}")

        if join == "AND":
            for cond in conditions:
                if not self.evaluate(cond):
                    return False
            return True

        for cond in conditions:
            if self.evaluate(cond):
                return True
        return False

    def complexity_score(self, condition: Condition) -> int:
        base = 1
        if condition.conditionType == "logical":
            base += len(condition.subConditions or []) * 2
        base += len(condition.operands or [])
        base += 1 if condition.expression else 0
        return base

    def _record_trace(self, condition: Condition, result: bool, **extras: Any) -> None:
        self._execution_path.append(condition.uuid)
        if not self.enable_tracing:
            return
        payload = {
            "condition_uuid": condition.uuid,
            "condition_type": condition.conditionType,
            "result": result,
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            **extras,
        }
        self.trace.append(payload)

    def _evaluate_condition(
        self, condition: Condition, _depth: int, _visited: set
    ) -> bool:
        ctype = (condition.conditionType or "").lower()
        if ctype not in self.CONDITION_TYPES:
            raise ConditionEvaluationError(
                f"Unknown condition type: {condition.conditionType}"
            )

        if ctype == "regex":
            return self._evaluate_regex_condition(condition)
        if ctype == "comparison":
            return self._evaluate_comparison_condition(condition)
        if ctype == "logical":
            return self._evaluate_logical_condition(condition, _depth, _visited)
        if ctype == "custom":
            return self._evaluate_custom_condition(condition)
        if ctype == "dsl":
            return self._evaluate_custom_condition(condition)
        if ctype == "temporal":
            return self._evaluate_temporal_condition(condition)
        if ctype == "arithmetic":
            return self._evaluate_arithmetic_condition(condition)
        if ctype == "set":
            return self._evaluate_set_condition(condition)
        raise ConditionEvaluationError(
            f"Unsupported condition type: {condition.conditionType}"
        )

    def _evaluate_regex_condition(self, condition: Condition) -> bool:
        if not condition.targetField or not condition.expression:
            raise ConditionEvaluationError(
                "Regex condition requires targetField and expression"
            )
        value = self._get_field_value(condition.targetField)
        if value is None:
            return False
        try:
            return (
                _compile_regex_pattern(condition.expression).search(str(value))
                is not None
            )
        except re.error as exc:
            raise ConditionEvaluationError(
                f"Invalid regex pattern '{condition.expression}': {exc}"
            ) from exc

    def _evaluate_comparison_condition(self, condition: Condition) -> bool:
        if not condition.targetField or not condition.operator:
            raise ConditionEvaluationError(
                "Comparison condition requires targetField and operator"
            )

        operator = condition.operator
        if operator not in self.COMPARISON_OPERATORS:
            raise ConditionEvaluationError(f"Unknown comparison operator: {operator}")

        value = self._get_field_value(condition.targetField)
        metadata = self.OPERATOR_METADATA.get(operator, {})
        required_operands = metadata.get("operands", 1)
        operands = list(condition.operands or [])

        if operator in {"is_empty", "is_not_empty"}:
            return bool(self.COMPARISON_OPERATORS[operator](value, None))

        if len(operands) < required_operands:
            raise ConditionEvaluationError(
                f"Operator '{operator}' requires at least {required_operands} operand(s)"
            )
        if len(operands) > self.max_operands:
            raise ConditionEvaluationError(
                f"Condition has too many operands ({len(operands)} > {self.max_operands})"
            )

        if operator == "between":
            low = self._coerce_value(operands[0], type(value))
            high = self._coerce_value(operands[1], type(value))
            return bool(self.COMPARISON_OPERATORS[operator](value, [low, high]))

        if operator in {
            "in_list",
            "not_in_list",
            "matches_all",
            "matches_any",
            "contains_any",
            "contains_all",
        }:
            parsed = [self._parse_jsonish(x) for x in operands]
            if len(parsed) == 1 and isinstance(parsed[0], list):
                parsed = parsed[0]
            return bool(self.COMPARISON_OPERATORS[operator](value, parsed))

        if operator == "regex":
            return bool(self.COMPARISON_OPERATORS[operator](value, operands[0]))

        comparator = self.COMPARISON_OPERATORS[operator]
        for operand in operands:
            coerced = self._coerce_value(operand, type(value))
            if comparator(value, coerced):
                return True
        return False

    def _evaluate_logical_condition(
        self, condition: Condition, _depth: int, _visited: set
    ) -> bool:
        if not condition.subConditions or not condition.logicalJoinType:
            raise ConditionEvaluationError(
                "Logical condition requires subConditions and logicalJoinType"
            )

        join_type = condition.logicalJoinType.upper()
        if join_type not in {"AND", "OR"}:
            raise ConditionEvaluationError(f"Invalid logical join type: {join_type}")

        if join_type == "AND":
            for sub_condition in condition.subConditions:
                sub = (
                    sub_condition.fetch()
                    if hasattr(sub_condition, "fetch")
                    else sub_condition
                )
                if not self.evaluate(sub, _depth=_depth + 1, _visited=_visited):
                    return False
            return True

        for sub_condition in condition.subConditions:
            sub = (
                sub_condition.fetch()
                if hasattr(sub_condition, "fetch")
                else sub_condition
            )
            sub_result = self.evaluate(sub, _depth=_depth + 1, _visited=_visited)
            if sub_result:
                if getattr(sub, "stopEvaluationIfTrue", False):
                    return True
                # Preserve OR semantics: any truthy sub-condition satisfies the
                # logical condition, but continue only when the current sub-condition
                # does not explicitly request short-circuiting.
                return True
        return False

    def _evaluate_custom_condition(self, condition: Condition) -> bool:
        if not condition.expression:
            raise ConditionEvaluationError("Custom conditions require expression")
        if not _is_safe_custom_condition_expression(
            condition.expression, set(self.context.keys())
        ):
            raise ConditionEvaluationError("Custom condition references unsafe fields")
        result = evaluate_expression(condition.expression, self.context)
        return bool(result)

    def _evaluate_temporal_condition(self, condition: Condition) -> bool:
        if (
            not condition.targetField
            or not condition.operator
            or not condition.operands
        ):
            raise ConditionEvaluationError(
                "Temporal conditions require targetField/operator/operands"
            )

        value = self._get_field_value(condition.targetField)
        if value is None:
            return False
        reference = self._coerce_datetime(value)
        days = float(condition.operands[0])
        # _coerce_datetime strips tzinfo, so keep now as naive UTC for the subtraction.
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        age_days = (now - reference).total_seconds() / 86400

        if condition.operator == "created_within_days":
            return age_days <= days
        if condition.operator == "updated_within_days":
            return age_days <= days
        if condition.operator == "older_than_days":
            return age_days > days
        if condition.operator == "duration_exceeds":
            return age_days > days
        if condition.operator == "duration_less_than":
            return age_days < days
        raise ConditionEvaluationError(
            f"Unsupported temporal operator: {condition.operator}"
        )

    def _evaluate_arithmetic_condition(self, condition: Condition) -> bool:
        if not condition.expression:
            raise ConditionEvaluationError("Arithmetic conditions require expression")
        result = evaluate_expression(condition.expression, self.context)
        return bool(result)

    def _evaluate_set_condition(self, condition: Condition) -> bool:
        if not condition.targetField or not condition.operator:
            raise ConditionEvaluationError(
                "Set conditions require targetField and operator"
            )
        target = self._to_set(self._get_field_value(condition.targetField))
        operand_set = self._to_set(
            [self._parse_jsonish(v) for v in condition.operands or []]
        )

        if condition.operator == "any":
            return bool(target and operand_set)
        if condition.operator == "all":
            return operand_set.issubset(target)
        if condition.operator == "none":
            return target.isdisjoint(operand_set)
        if condition.operator == "subset":
            return target.issubset(operand_set)
        if condition.operator == "superset":
            return target.issuperset(operand_set)
        if condition.operator == "intersects":
            return bool(target.intersection(operand_set))

        raise ConditionEvaluationError(
            f"Unsupported set operator: {condition.operator}"
        )

    def _get_field_value(self, field_path: str) -> Any:
        value: Any = self.context
        for part in field_path.split("."):
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return None
            if value is None:
                return None
        return value

    @staticmethod
    def _coerce_value(value: Any, target_type: type) -> Any:
        if target_type is None or target_type is type(None):
            return value
        if isinstance(value, target_type):
            return value
        if target_type in (int, float):
            try:
                return target_type(value)
            except (TypeError, ValueError):
                return value
        if target_type is bool:
            if isinstance(value, str):
                return value.lower() in {"1", "true", "yes", "y"}
            return bool(value)
        if target_type is str:
            return str(value)
        return value

    @staticmethod
    def _to_set(value: Any) -> set:
        if value is None:
            return set()
        if isinstance(value, set):
            return value
        if isinstance(value, (list, tuple)):
            return set(value)
        return {value}

    @staticmethod
    def _parse_jsonish(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        cleaned = value.strip()
        if cleaned.startswith("[") and cleaned.endswith("]"):
            raw = cleaned[1:-1].strip()
            if not raw:
                return []
            return [item.strip().strip("\"'") for item in raw.split(",")]
        return value

    @staticmethod
    def _coerce_datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc).replace(
                tzinfo=None
            )
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(
                    tzinfo=None
                )
            except ValueError as exc:
                raise ConditionEvaluationError(
                    f"Invalid datetime value: {value}"
                ) from exc
        raise ConditionEvaluationError(
            f"Unsupported datetime value type: {type(value)}"
        )


class ConditionEvaluationContext:
    @staticmethod
    def from_response_item(response_item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "value": response_item.get("value"),
            "status": response_item.get("status"),
            "metadata": response_item.get("metadata", {}),
            "validation_errors": response_item.get("validation_errors", []),
            "score": response_item.get("score"),
            "response": response_item,
        }

    @staticmethod
    def from_form_response(form_response: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "status": form_response.get("status"),
            "workflow_state": form_response.get("workflow_state"),
            "metadata": form_response.get("metadata", {}),
            "responses": form_response.get("responses", {}),
            "form_response": form_response,
        }

    @staticmethod
    def merged(
        response_item: Optional[Dict[str, Any]] = None,
        form_response: Optional[Dict[str, Any]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        context: Dict[str, Any] = {}
        if form_response:
            context.update(ConditionEvaluationContext.from_form_response(form_response))
        if response_item:
            context.update(ConditionEvaluationContext.from_response_item(response_item))
        if extra:
            context.update(extra)
        return context
