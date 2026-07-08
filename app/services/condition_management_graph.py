from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

from app.models.form import Condition
from app.services.condition_evaluator import ConditionEvaluator


def build_dependency_graph() -> Dict[str, List[str]]:
    graph = defaultdict(list)
    for condition in Condition.objects:
        deps = []
        for sub in condition.subConditions or []:
            ref = sub.fetch() if hasattr(sub, "fetch") else sub
            if ref and ref.uuid:
                deps.append(ref.uuid)
        graph[condition.uuid] = sorted(set(deps))
    return dict(graph)


def reverse_dependency_graph(
    graph: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, List[str]]:
    base = graph or build_dependency_graph()
    reverse = defaultdict(list)
    for condition_uuid, deps in base.items():
        for dep in deps:
            reverse[dep].append(condition_uuid)
    for key in base:
        reverse.setdefault(key, [])
    return {key: sorted(set(values)) for key, values in reverse.items()}


def detect_circular_references(
    graph: Optional[Dict[str, List[str]]] = None,
) -> List[List[str]]:
    base = graph or build_dependency_graph()
    visited = set()
    stack = set()
    path: List[str] = []
    cycles: List[List[str]] = []

    def dfs(node: str) -> None:
        visited.add(node)
        stack.add(node)
        path.append(node)
        for child in base.get(node, []):
            if child not in visited:
                dfs(child)
            elif child in stack:
                start = path.index(child)
                cycles.append(path[start:] + [child])
        stack.remove(node)
        path.pop()

    for node in base.keys():
        if node not in visited:
            dfs(node)
    return cycles


def calculate_complexity_score(
    condition: Condition, graph: Optional[Dict[str, List[str]]] = None
) -> Dict[str, Any]:
    base_score = ConditionEvaluator().complexity_score(condition)
    deps = (
        graph.get(condition.uuid, [])
        if graph
        else build_dependency_graph().get(condition.uuid, [])
    )
    score = base_score + len(deps)
    level = "low"
    if score >= 12:
        level = "high"
    elif score >= 7:
        level = "medium"
    return {"score": score, "level": level, "dependency_count": len(deps)}
