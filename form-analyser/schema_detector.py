"""
schema_detector.py
------------------
Scan a MongoDB collection and auto-generate a suggested analysis definition.

Updated to understand the form-backend schema where:
  - All question answers live inside the `data` dict
  - Keys inside `data` are question variable_names
  - Top-level fields like organization_id, submitted_by, status are system fields
  - Multi-select answers are stored as arrays → suggest array_frequency

Detection logic per field type:
  few unique strings / booleans  →  frequency
  many unique strings            →  top_n
  numbers                        →  aggregate (avg)
  string arrays (multi-select)   →  array_frequency
  fields often null              →  missing (if >20% null)
  top categorical pairs          →  crosstab
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any


# ---------------------------------------------------------------------------
# Fields to skip during detection
# ---------------------------------------------------------------------------

# System / internal fields from form-backend that are not analysis targets
_SKIP_FIELDS = frozenset({
    # MongoDB internals
    "_id", "_cls",
    # form-backend system fields
    "organization_id", "submitted_by", "ip_address", "user_agent",
    "is_deleted", "deleted_at", "deleted_by",
    "is_draft", "is_sensitive",
    "updated_by", "created_by",
    "ai_results", "encrypted_data", "status_log",
    "meta_data", "tags",
    # Timestamp fields (matched by suffix below too)
    "created_at", "updated_at", "submitted_at", "deleted_at",
    # Reference ID fields (UUIDs pointing to other collections)
    "form", "form_version", "project", "version",
    "__v",
})

_TIMESTAMP_RE = re.compile(r"(at|date|time|timestamp)$", re.IGNORECASE)
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_schema(
    collection,
    sample_size: int = 200,
    id_field: str | None = None,
    form_id_value: str | None = None,
    extra_skip_fields: list[str] | None = None,
    organization_id: str | None = None,
) -> dict:
    """
    Sample documents and return a suggested analysis definition JSON.

    For form-backend data, the most useful call is:
      detect_schema(collection, id_field="form", form_id_value="<form-uuid>")

    This scopes detection to one form and focuses on the `data` subdocument.
    """
    skip = set(_SKIP_FIELDS)
    if extra_skip_fields:
        skip.update(extra_skip_fields)

    pipeline: list[dict] = []
    if organization_id:
        pipeline.append({"$match": {"organization_id": organization_id}})
    if id_field and form_id_value:
        pipeline.append({"$match": {id_field: form_id_value}})
    pipeline.append({"$sample": {"size": sample_size}})

    docs = list(collection.aggregate(pipeline))
    if not docs:
        return {
            "error": "No documents found. Check collection name and filters.",
            "steps": [],
        }

    field_stats = _collect_field_stats(docs, skip)
    steps, categorical_fields = _generate_steps(field_stats, len(docs))
    steps.extend(_generate_crosstabs(categorical_fields))

    filters = []
    if id_field and form_id_value:
        filters.append({"field": id_field, "operator": "eq", "value": form_id_value})
    # Always suggest filtering out soft-deleted docs
    filters.append({"field": "is_deleted", "operator": "eq", "value": False})

    return {
        "name": f"Auto-detected — {collection.name}",
        "description": (
            f"Suggested from {len(docs)} sampled documents. "
            "Review steps before using in production. "
            "Field paths use 'data.<variable_name>' to target question answers."
        ),
        "source_collection": collection.name,
        "filters": filters,
        "steps": steps,
        "_detection_meta": {
            "sample_size": len(docs),
            "fields_analyzed": len(field_stats),
            "steps_suggested": len(steps),
        },
    }


def get_field_list(
    collection,
    sample_size: int = 200,
    id_field: str | None = None,
    form_id_value: str | None = None,
    organization_id: str | None = None,
) -> list[dict]:
    """
    Return a catalogue of all detected fields with type, null rate, and sample values.
    Fields inside the `data` dict are marked with data_field=True.
    """
    pipeline: list[dict] = []
    if organization_id:
        pipeline.append({"$match": {"organization_id": organization_id}})
    if id_field and form_id_value:
        pipeline.append({"$match": {id_field: form_id_value}})
    pipeline.append({"$sample": {"size": sample_size}})

    docs = list(collection.aggregate(pipeline))
    if not docs:
        return []

    field_stats = _collect_field_stats(docs, set(_SKIP_FIELDS))
    n = len(docs)

    result = []
    for path, stats in sorted(field_stats.items()):
        values = stats["values"]
        unique_vals = sorted({str(v) for v in values if not _looks_like_uuid(str(v))})
        result.append({
            "field": path,
            "is_data_field": path.startswith("data."),   # True = inside data dict (question answer)
            "types": sorted(stats["types"]),
            "null_count": stats["null_count"],
            "null_pct": round(stats["null_count"] / n * 100, 1) if n else 0,
            "unique_count": len({str(v) for v in values}),
            "sample_values": unique_vals[:10],
            "suggested_step": _classify_field(stats, n),
        })
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _looks_like_uuid(val: str) -> bool:
    return bool(_UUID_RE.match(val))


def _flatten(obj: Any, prefix: str, depth: int, max_depth: int = 4):
    """Recursively yield (path, value) pairs from nested dicts."""
    if not isinstance(obj, dict) or depth > max_depth:
        return
    for key, value in obj.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            yield from _flatten(value, path, depth + 1, max_depth)
        else:
            yield path, value


def _should_skip(path: str, skip: set) -> bool:
    base = path.split(".")[-1]
    return base in skip or bool(_TIMESTAMP_RE.search(base))


def _collect_field_stats(docs: list[dict], skip: set) -> dict:
    stats: dict[str, dict] = defaultdict(lambda: {
        "types": set(),
        "values": [],
        "null_count": 0,
        "array_values": [],   # sample of items inside array fields
    })
    for doc in docs:
        for path, value in _flatten(doc, "", 0):
            if _should_skip(path, skip):
                continue
            s = stats[path]
            if value is None:
                s["null_count"] += 1
                s["types"].add("null")
            elif isinstance(value, bool):
                s["types"].add("boolean")
                s["values"].append(value)
            elif isinstance(value, (int, float)):
                s["types"].add("number")
                s["values"].append(value)
            elif isinstance(value, str):
                if value.strip() and not _looks_like_uuid(value):
                    s["types"].add("string")
                    s["values"].append(value)
                elif not value.strip():
                    s["null_count"] += 1
                # UUIDs are skipped — they're reference IDs
            elif isinstance(value, list):
                s["types"].add("array")
                # Sample string contents for array_frequency detection
                str_items = [i for i in value if isinstance(i, str) and i.strip()]
                s["array_values"].extend(str_items[:5])
    return dict(stats)


def _safe_id(path: str) -> str:
    return re.sub(r"[^a-z0-9]", "_", path.lower()).strip("_")


def _classify_field(stats: dict, doc_count: int) -> str:
    types = stats["types"] - {"null"}
    values = stats["values"]
    if not values and not stats.get("array_values"):
        return "missing"
    if "array" in types:
        return "array_frequency" if stats.get("array_values") else "missing"
    if "number" in types:
        return "aggregate"
    unique_count = len(set(str(v) for v in values))
    if "string" in types or "boolean" in types:
        return "frequency" if unique_count <= 15 else "top_n"
    return "unknown"


def _generate_steps(field_stats: dict, doc_count: int) -> tuple[list, list]:
    """Return (steps_list, categorical_field_paths)."""
    steps = []
    categorical_fields: list[tuple[str, int]] = []

    for path, stats in sorted(field_stats.items()):
        types = stats["types"] - {"null"}
        values = stats["values"]
        array_values = stats.get("array_values", [])
        null_pct = stats["null_count"] / doc_count * 100 if doc_count else 0
        unique_count = len(set(str(v) for v in values))

        # Suggest "missing" if >20% null and field has some real values
        if null_pct > 20 and (values or array_values):
            steps.append({
                "id": f"missing_{_safe_id(path)}",
                "type": "missing",
                "field": path,
                "label": f"Missing values — {path}",
            })

        # --- Array fields (multi-select / checkboxes) → array_frequency ---
        if "array" in types:
            if array_values:
                steps.append({
                    "id": f"arr_freq_{_safe_id(path)}",
                    "type": "array_frequency",
                    "field": path,
                    "label": f"Multi-select Distribution — {path}",
                })
            continue   # don't also add frequency/top_n for arrays

        if not values:
            continue

        # --- Numeric fields → aggregate ---
        if "number" in types:
            steps.append({
                "id": f"avg_{_safe_id(path)}",
                "type": "aggregate",
                "field": path,
                "operation": "avg",
                "label": f"Average — {path}",
            })

        # --- Categorical / boolean fields ---
        elif "string" in types or "boolean" in types:
            if unique_count <= 15:
                steps.append({
                    "id": f"freq_{_safe_id(path)}",
                    "type": "frequency",
                    "field": path,
                    "label": f"Distribution — {path}",
                })
                categorical_fields.append((path, unique_count))
            else:
                steps.append({
                    "id": f"top5_{_safe_id(path)}",
                    "type": "top_n",
                    "field": path,
                    "n": 5,
                    "label": f"Top 5 — {path}",
                })

    return steps, categorical_fields


def _generate_crosstabs(categorical_fields: list, max_crosstabs: int = 3) -> list:
    """Suggest crosstabs between the top categorical field pairs."""
    if len(categorical_fields) < 2:
        return []

    sorted_fields = sorted(categorical_fields, key=lambda x: x[1])
    steps = []
    seen: set = set()

    for i, (row_field, _) in enumerate(sorted_fields):
        for col_field, _ in sorted_fields[i + 1:]:
            if len(steps) >= max_crosstabs:
                break
            key = (row_field, col_field)
            if key not in seen:
                seen.add(key)
                steps.append({
                    "id": f"cross_{_safe_id(row_field)}_vs_{_safe_id(col_field)}",
                    "type": "crosstab",
                    "row_field": row_field,
                    "col_field": col_field,
                    "label": f"Crosstab — {row_field} × {col_field}",
                })

    return steps
