"""
analysis_engine.py
------------------
The heart of the system.

Reads an "Analysis Definition" JSON and executes it against a MongoDB
collection of form responses.

Analysis Definition JSON Schema
================================
{
  "name": "Customer Satisfaction Q1 2024",
  "description": "Optional human readable description",
  "source_collection": "form_responses",   // which collection to query
  "filters": [                              // pre-filter: who to include
    {
      "field": "region",
      "operator": "eq",       // eq, ne, gt, gte, lt, lte, in, nin, exists, regex
      "value": "North"
    }
  ],
  "steps": [                                // ordered list of analysis steps
    {
      "id": "q1_breakdown",                 // unique id for this step's result
      "type": "frequency",                  // see STEP TYPES below
      "field": "answers.satisfaction",
      "label": "Satisfaction Breakdown"
    },
    {
      "id": "avg_age",
      "type": "aggregate",
      "field": "answers.age",
      "operation": "avg",                   // avg, sum, min, max, count
      "label": "Average Age"
    },
    {
      "id": "satisfaction_by_region",
      "type": "crosstab",
      "row_field": "answers.satisfaction",
      "col_field": "answers.region",
      "label": "Satisfaction by Region"
    },
    {
      "id": "segment_north",
      "type": "segment",
      "filter": {
        "field": "answers.region",
        "operator": "eq",
        "value": "North"
      },
      "sub_steps": [                        // nested steps run only on this segment
        {
          "id": "north_satisfaction",
          "type": "frequency",
          "field": "answers.satisfaction",
          "label": "Satisfaction (North only)"
        }
      ],
      "label": "North Region Segment"
    }
  ]
}

STEP TYPES
----------
Original:
  frequency            : count & percentage for each unique value of a field
  array_frequency      : frequency for multi-select array fields (uses $unwind)
  aggregate            : single numeric metric (avg / sum / min / max / count)
  crosstab             : cross-tabulation of two categorical fields
  segment              : filter a sub-population and run nested steps on it
  top_n                : top N most frequent values for a field
  missing              : count missing / null values for a field

Advanced / New:
  time_series          : group response counts (or metrics) by time period
  nps                  : Net Promoter Score (promoters / passives / detractors)
  percentile           : p25 / p50 / p75 / p90 / p95 for numeric fields
  pivot_aggregate      : aggregate of value_field grouped by category (e.g. avg rating by region)
  boolean_summary      : true / false / null breakdown for boolean fields
  conditional_frequency: frequency of field_A filtered to where field_B = value
  correlation          : Pearson correlation between two numeric fields
  funnel               : count at each stage of a filter funnel with drop-off
  rank                 : rank categories by aggregate metric
"""

from __future__ import annotations

import re
import math
from typing import Any
from stats_utils import chi2_p_value, student_t_p_value, f_p_value

from pymongo.collection import Collection


# ---------------------------------------------------------------------------
# Operator helpers
# ---------------------------------------------------------------------------

_OPERATOR_MAP = {
    "eq":     "$eq",
    "ne":     "$ne",
    "gt":     "$gt",
    "gte":    "$gte",
    "lt":     "$lt",
    "lte":    "$lte",
    "in":     "$in",
    "nin":    "$nin",
    "exists": "$exists",
    "regex":  "$regex",
}


def _build_mongo_filter(filters: list[dict]) -> dict:
    """Convert a list of filter dicts into a single MongoDB match dict."""
    if not filters:
        return {}

    conditions = {}
    for f in filters:
        field = f["field"]
        operator = f.get("operator", "eq")
        value = f.get("value")

        mongo_op = _OPERATOR_MAP.get(operator)
        if not mongo_op:
            raise ValueError(f"Unknown filter operator: '{operator}'")

        if operator == "regex":
            conditions[field] = {"$regex": re.compile(value, re.IGNORECASE)}
        elif operator == "exists":
            conditions[field] = {"$exists": bool(value)}
        else:
            conditions[field] = {mongo_op: value}

    return conditions


# ---------------------------------------------------------------------------
# Step runners
# ---------------------------------------------------------------------------

def _run_frequency(collection: Collection, match: dict, step: dict) -> dict:
    """Count occurrences and compute percentages for each unique value."""
    field = step["field"]
    pipeline = []
    if match:
        pipeline.append({"$match": match})
    pipeline += [
        {"$group": {"_id": f"${field}", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    raw = list(collection.aggregate(pipeline))

    total = sum(r["count"] for r in raw)
    rows = [
        {
            "value": r["_id"],
            "count": r["count"],
            "percentage": round(r["count"] / total * 100, 2) if total else 0,
        }
        for r in raw
    ]
    return {
        "type": "frequency",
        "label": step.get("label", field),
        "field": field,
        "total_responses": total,
        "breakdown": rows,
    }


def _run_aggregate(collection: Collection, match: dict, step: dict) -> dict:
    """Compute a single numeric metric (avg, sum, min, max, count)."""
    field = step["field"]
    operation = step.get("operation", "count").lower()

    op_map = {
        "avg":   "$avg",
        "sum":   "$sum",
        "min":   "$min",
        "max":   "$max",
        "count": "$sum",          # $sum with 1 gives count
    }
    if operation not in op_map:
        raise ValueError(f"Unknown aggregate operation: '{operation}'")

    pipeline = []
    if match:
        pipeline.append({"$match": match})

    if operation == "count":
        pipeline.append({"$group": {"_id": None, "result": {"$sum": 1}}})
    else:
        pipeline.append({"$group": {"_id": None, "result": {op_map[operation]: f"${field}"}}})

    raw = list(collection.aggregate(pipeline))
    result = raw[0]["result"] if raw else None

    return {
        "type": "aggregate",
        "label": step.get("label", f"{operation}({field})"),
        "field": field,
        "operation": operation,
        "result": result,
    }


def _run_crosstab(collection: Collection, match: dict, step: dict) -> dict:
    """Build a cross-tabulation table between two fields."""
    row_field = step["row_field"]
    col_field = step["col_field"]

    pipeline = []
    if match:
        pipeline.append({"$match": match})
    pipeline += [
        {
            "$group": {
                "_id": {
                    "row": f"${row_field}",
                    "col": f"${col_field}",
                },
                "count": {"$sum": 1},
            }
        }
    ]
    raw = list(collection.aggregate(pipeline))

    # Build a 2D dict: { row_value: { col_value: count } }
    table: dict[Any, dict[Any, int]] = {}
    col_values: set = set()
    for r in raw:
        row_val = r["_id"]["row"]
        col_val = r["_id"]["col"]
        col_values.add(col_val)
        table.setdefault(row_val, {})[col_val] = r["count"]

    col_list = sorted(col_values, key=str)
    rows = []
    for row_val in sorted(table.keys(), key=str):
        row_data = {"_row": row_val}
        row_total = 0
        for col_val in col_list:
            count = table[row_val].get(col_val, 0)
            row_data[str(col_val)] = count
            row_total += count
        row_data["_total"] = row_total
        rows.append(row_data)

    return {
        "type": "crosstab",
        "label": step.get("label", f"{row_field} × {col_field}"),
        "row_field": row_field,
        "col_field": col_field,
        "columns": [str(c) for c in col_list],
        "rows": rows,
    }


def _run_top_n(collection: Collection, match: dict, step: dict) -> dict:
    """Return the top N most frequent values for a field."""
    field = step["field"]
    n = step.get("n", 5)

    pipeline = []
    if match:
        pipeline.append({"$match": match})
    pipeline += [
        {"$group": {"_id": f"${field}", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": n},
    ]
    raw = list(collection.aggregate(pipeline))
    total_pipeline = [*([ {"$match": match}] if match else []), {"$count": "total"}]
    total_raw = list(collection.aggregate(total_pipeline))
    total = total_raw[0]["total"] if total_raw else 0

    rows = [
        {
            "value": r["_id"],
            "count": r["count"],
            "percentage": round(r["count"] / total * 100, 2) if total else 0,
        }
        for r in raw
    ]
    return {
        "type": "top_n",
        "label": step.get("label", f"Top {n}: {field}"),
        "field": field,
        "n": n,
        "total_responses": total,
        "top": rows,
    }


def _run_missing(collection: Collection, match: dict, step: dict) -> dict:
    """Count how many responses are missing a value for a field."""
    field = step["field"]

    base_match = dict(match) if match else {}

    total_pipeline = [*([ {"$match": base_match}] if base_match else []), {"$count": "total"}]
    total_raw = list(collection.aggregate(total_pipeline))
    total = total_raw[0]["total"] if total_raw else 0

    missing_match = dict(base_match)
    missing_match[field] = {"$in": [None, "", []]}

    missing_pipeline = [{"$match": missing_match}, {"$count": "missing"}]
    missing_raw = list(collection.aggregate(missing_pipeline))
    missing = missing_raw[0]["missing"] if missing_raw else 0

    filled = total - missing
    return {
        "type": "missing",
        "label": step.get("label", f"Missing: {field}"),
        "field": field,
        "total_responses": total,
        "missing": missing,
        "filled": filled,
        "missing_pct": round(missing / total * 100, 2) if total else 0,
        "filled_pct": round(filled / total * 100, 2) if total else 0,
    }




def _run_array_frequency(collection: Collection, match: dict, step: dict) -> dict:
    """
    Frequency count for fields that store arrays (multi-select, checkboxes, multi_select).

    When a question accepts multiple answers, each response stores an array:
      data.preferred_features = ["Speed", "UI", "Support"]

    Standard 'frequency' groups by the whole array object.
    This step uses $unwind to expand each item before counting,
    so every selected option is counted individually.

    Use this for field_types: checkboxes, multi_select, multi_checkbox
    """
    field = step["field"]
    pipeline = []
    if match:
        pipeline.append({"$match": match})
    pipeline += [
        # Only include docs where the field is a non-empty array
        {"$match": {field: {"$type": "array", "$ne": []}}},
        {"$unwind": f"${field}"},
        {"$group": {"_id": f"${field}", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    raw = list(collection.aggregate(pipeline))

    total_selections = sum(r["count"] for r in raw)

    # Count how many responses had at least one value (for context)
    resp_pipeline = list(([{"$match": match}] if match else []))
    resp_pipeline.append({"$match": {field: {"$type": "array", "$ne": []}}})
    resp_pipeline.append({"$count": "n"})
    resp_raw = list(collection.aggregate(resp_pipeline))
    response_count = resp_raw[0]["n"] if resp_raw else 0

    rows = [
        {
            "value": r["_id"],
            "count": r["count"],
            "percentage_of_selections": round(r["count"] / total_selections * 100, 2) if total_selections else 0,
            "percentage_of_responses": round(r["count"] / response_count * 100, 2) if response_count else 0,
        }
        for r in raw
    ]
    return {
        "type": "array_frequency",
        "label": step.get("label", field),
        "field": field,
        "response_count": response_count,
        "total_selections": total_selections,
        "avg_selections_per_response": (
            round(total_selections / response_count, 2) if response_count else 0
        ),
        "breakdown": rows,
    }


def _run_segment(collection: Collection, match: dict, step: dict) -> dict:
    """Run nested sub-steps on a filtered sub-population."""
    # Merge the outer match with this segment's filter
    segment_filter = _build_mongo_filter([step["filter"]])
    combined_match = {**match, **segment_filter}

    sub_results = {}
    for sub_step in step.get("sub_steps", []):
        sub_id = sub_step.get("id", sub_step["type"])
        sub_results[sub_id] = _run_step(collection, combined_match, sub_step)

    # Count how many docs match this segment
    count_pipeline = [{"$match": combined_match}, {"$count": "count"}] if combined_match else [{"$count": "count"}]
    count_raw = list(collection.aggregate(count_pipeline))
    segment_count = count_raw[0]["count"] if count_raw else 0

    return {
        "type": "segment",
        "label": step.get("label", "Segment"),
        "filter": step["filter"],
        "segment_count": segment_count,
        "sub_results": sub_results,
    }


# ---------------------------------------------------------------------------
# NEW: Advanced step runners
# ---------------------------------------------------------------------------

def _run_time_series(collection: Collection, match: dict, step: dict) -> dict:
    """
    Group responses by time period to reveal trends.

    step keys:
      date_field  : field to group by (default: 'submitted_at')
      period      : 'hour' | 'day' | 'week' | 'month' | 'quarter' | 'year'
      value_field : optional — numeric field to aggregate per period
      operation   : 'count' (default) | 'avg' | 'sum' | 'min' | 'max'
    """
    date_field = step.get("date_field", "submitted_at")
    period     = step.get("period", "month")
    value_field = step.get("value_field")
    operation   = step.get("operation", "count").lower()

    _valid_periods = {"hour", "day", "week", "month", "quarter", "year"}
    if period not in _valid_periods:
        raise ValueError(f"period must be one of {_valid_periods}")

    if period == "year":
        date_expr = {"$dateToString": {"format": "%Y", "date": f"${date_field}"}}
    elif period == "quarter":
        date_expr = {"$concat": [
            {"$dateToString": {"format": "%Y-Q", "date": f"${date_field}"}},
            {"$toString": {"$ceil": {"$divide": [{"$month": f"${date_field}"}, 3]}}},
        ]}
    elif period == "month":
        date_expr = {"$dateToString": {"format": "%Y-%m", "date": f"${date_field}"}}
    elif period == "week":
        date_expr = {"$dateToString": {"format": "%G-W%V", "date": f"${date_field}"}}
    elif period == "day":
        date_expr = {"$dateToString": {"format": "%Y-%m-%d", "date": f"${date_field}"}}
    else:  # hour
        date_expr = {"$dateToString": {"format": "%Y-%m-%dT%H:00", "date": f"${date_field}"}}

    pipeline: list[dict] = []
    if match:
        pipeline.append({"$match": match})
    pipeline.append({"$match": {date_field: {"$ne": None}}})

    op_map = {"avg": "$avg", "sum": "$sum", "min": "$min", "max": "$max"}
    group: dict = {"_id": date_expr, "count": {"$sum": 1}}
    if value_field and operation in op_map:
        group["metric"] = {op_map[operation]: f"${value_field}"}

    pipeline += [{"$group": group}, {"$sort": {"_id": 1}}]
    raw = list(collection.aggregate(pipeline))

    points = []
    for r in raw:
        pt: dict = {"period": r["_id"], "count": r["count"]}
        if "metric" in r:
            m = r["metric"]
            pt["metric"] = round(m, 4) if isinstance(m, float) else m
        points.append(pt)

    return {
        "type": "time_series",
        "label": step.get("label", f"Trend by {period}"),
        "date_field": date_field,
        "period": period,
        "operation": operation,
        "total_periods": len(points),
        "points": points,
    }


def _run_nps(collection: Collection, match: dict, step: dict) -> dict:
    """
    Net Promoter Score — standard 0-10 scale analysis.

    Promoters  : score >= promoter_min (default 9)
    Passives   : passive_min <= score < promoter_min (default 7-8)
    Detractors : score < passive_min (default 0-6)
    NPS        = % Promoters − % Detractors

    step keys:
      field        : the NPS question variable_name
      promoter_min : int, default 9
      passive_min  : int, default 7
    """
    field        = step["field"]
    promoter_min = step.get("promoter_min", 9)
    passive_min  = step.get("passive_min", 7)

    pipeline: list[dict] = []
    if match:
        pipeline.append({"$match": match})
    pipeline += [
        {"$match": {field: {"$ne": None}}},
        {"$group": {
            "_id": None,
            "total":      {"$sum": 1},
            "promoters":  {"$sum": {"$cond": [{"$gte": [f"${field}", promoter_min]}, 1, 0]}},
            "passives":   {"$sum": {"$cond": [
                {"$and": [{"$gte": [f"${field}", passive_min]}, {"$lt": [f"${field}", promoter_min]}]}, 1, 0
            ]}},
            "detractors": {"$sum": {"$cond": [{"$lt": [f"${field}", passive_min]}, 1, 0]}},
            "avg_score":  {"$avg": f"${field}"},
        }},
    ]

    raw = list(collection.aggregate(pipeline))
    if not raw:
        return {
            "type": "nps", "label": step.get("label", "NPS"),
            "field": field, "nps_score": None, "total_responses": 0,
        }

    r        = raw[0]
    total    = r["total"]
    pro_pct  = round(r["promoters"]  / total * 100, 2) if total else 0
    pas_pct  = round(r["passives"]   / total * 100, 2) if total else 0
    det_pct  = round(r["detractors"] / total * 100, 2) if total else 0
    nps      = round(pro_pct - det_pct, 2)

    if   nps > 70: interpretation = "World Class"
    elif nps > 50: interpretation = "Excellent"
    elif nps > 20: interpretation = "Good"
    elif nps > 0:  interpretation = "Needs Improvement"
    else:          interpretation = "Poor"

    return {
        "type": "nps",
        "label": step.get("label", "Net Promoter Score"),
        "field": field,
        "nps_score": nps,
        "interpretation": interpretation,
        "total_responses": total,
        "avg_score": round(r["avg_score"], 2) if r["avg_score"] is not None else None,
        "promoters":  {"count": r["promoters"],  "percentage": pro_pct, "threshold": f">= {promoter_min}"},
        "passives":   {"count": r["passives"],   "percentage": pas_pct, "threshold": f"{passive_min}–{promoter_min - 1}"},
        "detractors": {"count": r["detractors"], "percentage": det_pct, "threshold": f"0–{passive_min - 1}"},
    }


def _run_percentile(collection: Collection, match: dict, step: dict) -> dict:
    """
    Percentile distribution for a numeric field.
    Returns configurable percentile breakpoints plus min / max / mean / IQR.

    ⚠  Loads all values into memory via $push. Use sample_limit for large datasets.

    step keys:
      field        : numeric field
      percentiles  : list of ints, default [25, 50, 75, 90, 95]
      sample_limit : int, cap number of docs sampled (default: unlimited)
    """
    field       = step["field"]
    percentiles = step.get("percentiles", [25, 50, 75, 90, 95])

    pipeline: list[dict] = []
    if match:
        pipeline.append({"$match": match})
    if step.get("sample_limit"):
        pipeline.append({"$sample": {"size": step["sample_limit"]}})
    pipeline += [
        {"$match": {field: {"$ne": None}}},
        {"$sort":  {field: 1}},
        {"$group": {
            "_id":    None,
            "values": {"$push": f"${field}"},
            "count":  {"$sum": 1},
            "sum":    {"$sum": f"${field}"},
            "min":    {"$min": f"${field}"},
            "max":    {"$max": f"${field}"},
        }},
        {"$addFields": {
            "mean": {"$divide": ["$sum", "$count"]},
            **{
                f"p{p}": {"$arrayElemAt": [
                    "$values",
                    {"$floor": {"$multiply": [
                        p / 100.0,
                        {"$subtract": ["$count", 1]},
                    ]}},
                ]}
                for p in percentiles
            },
        }},
        {"$project": {"values": 0}},
    ]

    raw = list(collection.aggregate(pipeline, allowDiskUse=True))
    if not raw:
        return {
            "type": "percentile", "label": step.get("label", f"Percentile — {field}"),
            "field": field, "error": "No numeric data found",
        }

    r = raw[0]
    pct_map = {f"p{p}": r.get(f"p{p}") for p in percentiles}
    iqr = None
    if r.get("p75") is not None and r.get("p25") is not None:
        iqr = round(r["p75"] - r["p25"], 4)

    mean = r.get("mean")
    return {
        "type": "percentile",
        "label": step.get("label", f"Percentile distribution — {field}"),
        "field": field,
        "total": r["count"],
        "min": r["min"],
        "max": r["max"],
        "mean": round(mean, 4) if isinstance(mean, float) else mean,
        "iqr": iqr,
        "percentiles": pct_map,
    }


def _run_pivot_aggregate(collection: Collection, match: dict, step: dict) -> dict:
    """
    For each unique value of group_field, compute an aggregate of value_field.
    Example: average overall_rating for each region.

    step keys:
      group_field : categorical field to group by
      value_field : numeric field to aggregate
      operation   : 'avg' (default) | 'sum' | 'min' | 'max' | 'count'
      sort_by     : 'value' (default, desc) | 'group' (asc)
      limit       : max groups returned (default 20)
      include_count: whether to include response_count per group (default True)
    """
    group_field    = step["group_field"]
    value_field    = step.get("value_field")
    operation      = step.get("operation", "avg").lower()
    sort_by        = step.get("sort_by", "value")
    limit          = step.get("limit", 20)

    op_map = {"avg": "$avg", "sum": "$sum", "min": "$min", "max": "$max"}
    if operation not in op_map and operation != "count":
        raise ValueError(f"operation must be one of: avg, sum, min, max, count")

    pipeline: list[dict] = []
    if match:
        pipeline.append({"$match": match})

    group: dict = {"_id": f"${group_field}", "response_count": {"$sum": 1}}
    if operation == "count":
        group["metric"] = {"$sum": 1}
    else:
        group["metric"] = {op_map[operation]: f"${value_field}"}

    sort_dir = -1 if sort_by == "value" else 1
    sort_key = "metric" if sort_by == "value" else "_id"

    pipeline += [
        {"$group": group},
        {"$sort": {sort_key: sort_dir}},
        {"$limit": limit},
    ]

    raw = list(collection.aggregate(pipeline))
    rows = []
    for r in raw:
        m = r["metric"]
        rows.append({
            "group": r["_id"],
            "response_count": r["response_count"],
            "metric": round(m, 4) if isinstance(m, float) else m,
        })

    return {
        "type": "pivot_aggregate",
        "label": step.get("label", f"{operation}({value_field}) by {group_field}"),
        "group_field": group_field,
        "value_field": value_field,
        "operation": operation,
        "rows": rows,
    }


def _run_boolean_summary(collection: Collection, match: dict, step: dict) -> dict:
    """
    True / False / Null breakdown for boolean / toggle fields.
    Works for Python True/False and also for "yes"/"no" strings if coerce_strings=True.

    step keys:
      field          : boolean field (data.opted_in, data.is_employed, etc.)
      coerce_strings : bool — also treat '1', 'yes', 'true', 'on' as True (default False)
    """
    field          = step["field"]
    coerce_strings = step.get("coerce_strings", False)

    pipeline: list[dict] = []
    if match:
        pipeline.append({"$match": match})

    true_check: Any = {"$eq": [f"${field}", True]}
    false_check: Any = {"$eq": [f"${field}", False]}

    if coerce_strings:
        truthy_vals = [True, "true", "True", "1", "yes", "Yes", "YES", "on"]
        falsy_vals  = [False, "false", "False", "0", "no",  "No",  "NO",  "off"]
        true_check  = {"$in": [f"${field}", truthy_vals]}
        false_check = {"$in": [f"${field}", falsy_vals]}

    pipeline += [
        {"$group": {
            "_id":         None,
            "total":       {"$sum": 1},
            "true_count":  {"$sum": {"$cond": [true_check,  1, 0]}},
            "false_count": {"$sum": {"$cond": [false_check, 1, 0]}},
        }},
    ]

    raw = list(collection.aggregate(pipeline))
    if not raw:
        return {"type": "boolean_summary", "field": field, "total_responses": 0}

    r     = raw[0]
    total = r["total"]
    t     = r["true_count"]
    f     = r["false_count"]
    n     = total - t - f

    def _pct(x): return round(x / total * 100, 2) if total else 0

    return {
        "type": "boolean_summary",
        "label": step.get("label", f"Yes / No — {field}"),
        "field": field,
        "total_responses": total,
        "true":  {"count": t, "percentage": _pct(t), "label": "Yes / True"},
        "false": {"count": f, "percentage": _pct(f), "label": "No / False"},
        "null":  {"count": n, "percentage": _pct(n), "label": "No answer / Null"},
    }


def _run_conditional_frequency(collection: Collection, match: dict, step: dict) -> dict:
    """
    Frequency of 'field' restricted to responses where condition_field = condition_value.
    Useful for: "What issues do North-region customers report?"

    step keys:
      field            : field to analyse
      condition_field  : field to filter on
      condition_value  : single value or list (treated as $in)
      exclude_nulls    : bool, skip null values of field (default True)
    """
    field           = step["field"]
    cond_field      = step["condition_field"]
    cond_value      = step["condition_value"]
    exclude_nulls   = step.get("exclude_nulls", True)

    sub_match = dict(match)
    if isinstance(cond_value, list):
        sub_match[cond_field] = {"$in": cond_value}
    else:
        sub_match[cond_field] = cond_value
    if exclude_nulls:
        sub_match[field] = {"$ne": None}

    pipeline: list[dict] = [
        {"$match": sub_match},
        {"$group": {"_id": f"${field}", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    raw   = list(collection.aggregate(pipeline))
    total = sum(r["count"] for r in raw)

    return {
        "type": "conditional_frequency",
        "label": step.get("label", f"{field} where {cond_field} = {cond_value}"),
        "field": field,
        "condition_field": cond_field,
        "condition_value": cond_value,
        "total_matching": total,
        "breakdown": [
            {
                "value": r["_id"],
                "count": r["count"],
                "percentage": round(r["count"] / total * 100, 2) if total else 0,
            }
            for r in raw
        ],
    }


def _run_correlation(collection: Collection, match: dict, step: dict) -> dict:
    """
    Pearson correlation coefficient between two numeric fields.
    Result is -1.0 to +1.0. Returns r, r², and a plain-English interpretation.

    step keys:
      field_a : first numeric field
      field_b : second numeric field
    """
    field_a = step["field_a"]
    field_b = step["field_b"]

    pipeline: list[dict] = []
    if match:
        pipeline.append({"$match": match})
    pipeline += [
        {"$match": {field_a: {"$ne": None}, field_b: {"$ne": None}}},
        {"$group": {
            "_id":    None,
            "n":      {"$sum": 1},
            "sum_x":  {"$sum": f"${field_a}"},
            "sum_y":  {"$sum": f"${field_b}"},
            "sum_xy": {"$sum": {"$multiply": [f"${field_a}", f"${field_b}"]}},
            "sum_x2": {"$sum": {"$multiply": [f"${field_a}", f"${field_a}"]}},
            "sum_y2": {"$sum": {"$multiply": [f"${field_b}", f"${field_b}"]}},
            "avg_x":  {"$avg": f"${field_a}"},
            "avg_y":  {"$avg": f"${field_b}"},
        }},
        {"$project": {
            "n": 1, "avg_x": 1, "avg_y": 1,
            "numerator": {
                "$subtract": [
                    {"$multiply": ["$n", "$sum_xy"]},
                    {"$multiply": ["$sum_x", "$sum_y"]},
                ]
            },
            "denom_x_sq": {
                "$subtract": [
                    {"$multiply": ["$n", "$sum_x2"]},
                    {"$multiply": ["$sum_x", "$sum_x"]},
                ]
            },
            "denom_y_sq": {
                "$subtract": [
                    {"$multiply": ["$n", "$sum_y2"]},
                    {"$multiply": ["$sum_y", "$sum_y"]},
                ]
            },
        }},
    ]

    raw = list(collection.aggregate(pipeline))
    if not raw:
        return {
            "type": "correlation", "field_a": field_a, "field_b": field_b,
            "error": "No data with both fields populated",
        }

    r   = raw[0]
    num = r["numerator"]
    dx  = r["denom_x_sq"]
    dy  = r["denom_y_sq"]
    denom_product = dx * dy

    if denom_product <= 0:
        corr = None
        strength = "undefined (zero variance in one or both fields)"
    else:
        corr = round(num / (denom_product ** 0.5), 4)
        abs_r = abs(corr)
        direction = "positive" if corr > 0 else "negative"
        if   abs_r >= 0.8: strength = f"very strong {direction}"
        elif abs_r >= 0.6: strength = f"strong {direction}"
        elif abs_r >= 0.4: strength = f"moderate {direction}"
        elif abs_r >= 0.2: strength = f"weak {direction}"
        else:              strength = "negligible"

    return {
        "type": "correlation",
        "label": step.get("label", f"Correlation: {field_a} × {field_b}"),
        "field_a": field_a,
        "field_b": field_b,
        "n": r["n"],
        "correlation": corr,
        "r_squared": round(corr ** 2, 4) if corr is not None else None,
        "strength": strength,
        "mean_a": round(r["avg_x"], 4) if r.get("avg_x") is not None else None,
        "mean_b": round(r["avg_y"], 4) if r.get("avg_y") is not None else None,
    }


def _run_funnel(collection: Collection, match: dict, step: dict) -> dict:
    """
    Count responses at each stage of a filter funnel and compute drop-off.

    mode 'independent' (default): each stage filter applied to the base match only.
    mode 'cumulative':            each stage filter stacks on top of all previous ones.

    step keys:
      stages : list of { label, filter }   (filter = same dict format as top-level filters)
      mode   : 'independent' (default) | 'cumulative'
    """
    stages = step.get("stages", [])
    mode   = step.get("mode", "independent")
    if not stages:
        raise ValueError("Funnel step requires at least one entry in 'stages'")

    base_pipeline = ([{"$match": match}] if match else []) + [{"$count": "total"}]
    base_raw  = list(collection.aggregate(base_pipeline))
    base_total = base_raw[0]["total"] if base_raw else 0

    results   = []
    cum_match = dict(match)

    for stage in stages:
        label        = stage.get("label", "Stage")
        stage_filter = stage.get("filter")

        if stage_filter:
            stage_mongo = _build_mongo_filter([stage_filter])
        else:
            stage_mongo = {}

        if mode == "cumulative":
            cum_match.update(stage_mongo)
            run_match = cum_match
        else:
            run_match = {**match, **stage_mongo}

        pipeline = ([{"$match": run_match}] if run_match else []) + [{"$count": "count"}]
        raw   = list(collection.aggregate(pipeline))
        count = raw[0]["count"] if raw else 0

        results.append({"stage": label, "count": count,
                        "percentage_of_total": round(count / base_total * 100, 2) if base_total else 0,
                        "drop_off": None, "drop_off_pct": None})

    for i in range(1, len(results)):
        prev = results[i - 1]["count"]
        curr = results[i]["count"]
        results[i]["drop_off"]     = prev - curr
        results[i]["drop_off_pct"] = round((prev - curr) / prev * 100, 2) if prev else 0

    return {
        "type": "funnel",
        "label": step.get("label", "Funnel"),
        "mode": mode,
        "base_total": base_total,
        "stages": results,
    }


def _run_rank(collection: Collection, match: dict, step: dict) -> dict:
    """
    Rank categories by an aggregate metric — produces a sorted leaderboard.
    Example: rank regions by average satisfaction score.

    step keys:
      group_field  : categorical field to rank
      value_field  : numeric field to aggregate (optional for count)
      operation    : 'avg' (default) | 'sum' | 'min' | 'max' | 'count'
      order        : 'desc' (default) | 'asc'
      limit        : max entries in ranking (default 20)
      min_count    : minimum response_count to be included (default 1)
    """
    group_field  = step["group_field"]
    value_field  = step.get("value_field")
    operation    = step.get("operation", "avg").lower()
    order        = step.get("order", "desc")
    limit        = step.get("limit", 20)
    min_count    = step.get("min_count", 1)

    op_map = {"avg": "$avg", "sum": "$sum", "min": "$min", "max": "$max"}
    if operation not in op_map and operation != "count":
        raise ValueError(f"operation must be one of: avg, sum, min, max, count")

    pipeline: list[dict] = []
    if match:
        pipeline.append({"$match": match})

    group: dict = {"_id": f"${group_field}", "response_count": {"$sum": 1}}
    if operation == "count":
        group["metric"] = {"$sum": 1}
    elif value_field:
        group["metric"] = {op_map[operation]: f"${value_field}"}
    else:
        raise ValueError("value_field is required when operation != 'count'")

    sort_dir = -1 if order == "desc" else 1

    pipeline += [
        {"$group": group},
        {"$match": {"response_count": {"$gte": min_count}}},
        {"$sort": {"metric": sort_dir, "_id": 1}},
        {"$limit": limit},
    ]

    raw = list(collection.aggregate(pipeline))
    ranked = [
        {
            "rank": i,
            "group": r["_id"],
            "response_count": r["response_count"],
            "metric": round(r["metric"], 4) if isinstance(r["metric"], float) else r["metric"],
        }
        for i, r in enumerate(raw, 1)
    ]

    return {
        "type": "rank",
        "label": step.get("label", f"Ranking by {operation}({value_field or 'count'})"),
        "group_field": group_field,
        "value_field": value_field,
        "operation": operation,
        "order": order,
        "ranked": ranked,
    }


def _run_summarize(collection: Collection, match: dict, step: dict) -> dict:
    """Stata-style summarize, detail for a numeric field."""
    field = step["field"]
    
    pipeline = []
    if match:
        pipeline.append({"$match": match})
    pipeline += [
        {"$match": {field: {"$ne": None}}},
        {"$project": {field: 1, "_id": 0}}
    ]
    raw = list(collection.aggregate(pipeline))
    
    def get_val(doc, path):
        parts = path.split(".")
        val = doc
        for p in parts:
            if isinstance(val, dict) and p in val:
                val = val[p]
            else:
                return None
        return val

    vals = []
    for doc in raw:
        v = get_val(doc, field)
        if isinstance(v, (int, float)):
            vals.append(float(v))
            
    n = len(vals)
    if n == 0:
        return {
            "type": "summarize",
            "field": field,
            "label": step.get("label", f"Summarize: {field}"),
            "count": 0,
            "error": "No numeric values found"
        }
        
    vals.sort()
    v_min = vals[0]
    v_max = vals[-1]
    v_sum = sum(vals)
    mean = v_sum / n
    
    def get_pct(p):
        idx = (p / 100.0) * (n - 1)
        low = math.floor(idx)
        high = math.ceil(idx)
        if low == high:
            return vals[low]
        return vals[low] + (idx - low) * (vals[high] - vals[low])
        
    p1 = get_pct(1)
    p5 = get_pct(5)
    p10 = get_pct(10)
    p25 = get_pct(25)
    p50 = get_pct(50)
    p75 = get_pct(75)
    p90 = get_pct(90)
    p95 = get_pct(95)
    p99 = get_pct(99)
    
    variance = 0.0
    skewness = 0.0
    kurtosis = 0.0
    std_dev = 0.0
    
    if n > 1:
        sq_diff_sum = sum((x - mean) ** 2 for x in vals)
        variance = sq_diff_sum / (n - 1)
        std_dev = math.sqrt(variance)
        
        if std_dev > 0:
            cube_diff_sum = sum(((x - mean) / std_dev) ** 3 for x in vals)
            skewness = cube_diff_sum / n
            quad_diff_sum = sum(((x - mean) / std_dev) ** 4 for x in vals)
            kurtosis = quad_diff_sum / n
            
    return {
        "type": "summarize",
        "field": field,
        "label": step.get("label", f"Summarize: {field}"),
        "count": n,
        "mean": round(mean, 4),
        "std_dev": round(std_dev, 4),
        "variance": round(variance, 4),
        "min": v_min,
        "max": v_max,
        "sum": round(v_sum, 4),
        "skewness": round(skewness, 4),
        "kurtosis": round(kurtosis, 4),
        "percentiles": {
            "p1": round(p1, 4),
            "p5": round(p5, 4),
            "p10": round(p10, 4),
            "p25": round(p25, 4),
            "p50": round(p50, 4),
            "p75": round(p75, 4),
            "p90": round(p90, 4),
            "p95": round(p95, 4),
            "p99": round(p99, 4),
        }
    }


def _run_tabulate_chi2(collection: Collection, match: dict, step: dict) -> dict:
    """Stata-style tabulate row col, chi2. Performs crosstabulation and Chi-Square test."""
    row_field = step["row_field"]
    col_field = step["col_field"]
    
    crosstab_res = _run_crosstab(collection, match, step)
    rows = crosstab_res["rows"]
    cols = crosstab_res["columns"]
    
    if not rows or not cols:
        return {
            "type": "tabulate_chi2",
            "row_field": row_field,
            "col_field": col_field,
            "label": step.get("label", f"Tabulate: {row_field} x {col_field}"),
            "error": "Insufficient data for Chi-Square calculation"
        }
        
    observed = []
    row_totals = []
    for r in rows:
        row_cells = []
        for c in cols:
            row_cells.append(float(r.get(c, 0)))
        observed.append(row_cells)
        row_totals.append(float(r.get("_total", 0)))
        
    grand_total = sum(row_totals)
    if grand_total <= 0:
        return {
            "type": "tabulate_chi2",
            "row_field": row_field,
            "col_field": col_field,
            "label": step.get("label", f"Tabulate: {row_field} x {col_field}"),
            "error": "Grand total is zero"
        }
        
    col_totals = [0.0] * len(cols)
    for c_idx in range(len(cols)):
        for r_idx in range(len(rows)):
            col_totals[c_idx] += observed[r_idx][c_idx]
            
    chi2_stat = 0.0
    for r_idx in range(len(rows)):
        for c_idx in range(len(cols)):
            expected = (row_totals[r_idx] * col_totals[c_idx]) / grand_total
            if expected > 0:
                chi2_stat += ((observed[r_idx][c_idx] - expected) ** 2) / expected
                
    df = (len(rows) - 1) * (len(cols) - 1)
    p_val = chi2_p_value(chi2_stat, df) if df > 0 else 1.0
    
    return {
        "type": "tabulate_chi2",
        "label": step.get("label", f"Tabulate: {row_field} x {col_field}"),
        "row_field": row_field,
        "col_field": col_field,
        "columns": cols,
        "rows": rows,
        "chi2": {
            "statistic": round(chi2_stat, 4),
            "df": df,
            "p_value": round(p_val, 6)
        }
    }


def _run_regress(collection: Collection, match: dict, step: dict) -> dict:
    """Stata-style regress y x1 x2 ... Support simple and multiple linear regression OLS."""
    field_y = step["field_y"]
    
    # Identify independent variables
    field_x = step.get("field_x")
    fields_x = step.get("fields_x")
    
    if fields_x is not None:
        if isinstance(fields_x, list):
            x_fields = fields_x
        else:
            x_fields = [fields_x]
    elif field_x is not None:
        if isinstance(field_x, list):
            x_fields = field_x
        else:
            x_fields = [field_x]
    else:
        raise ValueError("Regression step requires 'field_x' or 'fields_x'")
        
    run_hettest = step.get("hettest", False)
    
    # 1. Fetch data
    pipeline = []
    if match:
        pipeline.append({"$match": match})
        
    # Build match condition to filter out documents with missing values
    match_not_null = {field_y: {"$ne": None}}
    for f in x_fields:
        match_not_null[f] = {"$ne": None}
    pipeline.append({"$match": match_not_null})
    
    project = {field_y: 1}
    for f in x_fields:
        project[f] = 1
    project["_id"] = 0
    pipeline.append({"$project": project})
    
    raw = list(collection.aggregate(pipeline))
    
    def get_val(doc, path):
        parts = path.split(".")
        val = doc
        for p in parts:
            if isinstance(val, dict) and p in val:
                val = val[p]
            else:
                return None
        return val

    # Extract clean vectors
    y_vals = []
    x_matrix = [] # rows of independent variable values
    for doc in raw:
        vy = get_val(doc, field_y)
        if not isinstance(vy, (int, float)):
            continue
        
        row_x = []
        valid_row = True
        for f in x_fields:
            vx = get_val(doc, f)
            if isinstance(vx, (int, float)):
                row_x.append(float(vx))
            else:
                valid_row = False
                break
                
        if valid_row:
            y_vals.append(float(vy))
            x_matrix.append(row_x)
            
    n = len(y_vals)
    k = len(x_fields)
    
    if n <= k + 1:
        return {
            "type": "regress",
            "field_y": field_y,
            "fields_x": x_fields,
            "label": step.get("label", f"Regression: {field_y} on {', '.join(x_fields)}"),
            "error": f"Insufficient data (needs at least {k + 2} matching numeric records)"
        }
        
    # Build the design matrix X with intercept column
    # X has size N x (k+1)
    X = []
    for row in x_matrix:
        X.append([1.0] + row)
        
    # Calculate X^T X (size (k+1) x (k+1))
    M = k + 1
    XTX = [[0.0 for _ in range(M)] for _ in range(M)]
    for r in range(M):
        for c in range(M):
            val = 0.0
            for i in range(n):
                val += X[i][r] * X[i][c]
            XTX[r][c] = val
            
    # Calculate X^T Y (size (k+1) x 1)
    XTY = [0.0 for _ in range(M)]
    for r in range(M):
        val = 0.0
        for i in range(n):
            val += X[i][r] * y_vals[i]
        XTY[r] = val
        
    # Solve (XTX) Beta = XTY and get (XTX)^-1 using Gauss-Jordan elimination
    Aug = []
    for r in range(M):
        row_A = [XTX[r][c] for c in range(M)]
        row_B = [XTY[r]]
        row_I = [1.0 if c == r else 0.0 for c in range(M)]
        Aug.append(row_A + row_B + row_I)

    for i in range(M):
        # Pivot
        pivot_row = i
        for r in range(i + 1, M):
            if abs(Aug[r][i]) > abs(Aug[pivot_row][i]):
                pivot_row = r
                
        if abs(Aug[pivot_row][i]) < 1e-12:
            return {
                "type": "regress",
                "field_y": field_y,
                "fields_x": x_fields,
                "label": step.get("label", f"Regression: {field_y} on {', '.join(x_fields)}"),
                "error": "Collinear independent variables (singular matrix)"
            }
            
        if pivot_row != i:
            Aug[i], Aug[pivot_row] = Aug[pivot_row], Aug[i]
            
        pivot_val = Aug[i][i]
        for j in range(len(Aug[i])):
            Aug[i][j] /= pivot_val
            
        for r in range(M):
            if r != i:
                factor = Aug[r][i]
                for j in range(len(Aug[r])):
                    Aug[r][j] -= factor * Aug[i][j]
                    
    # Coefficients
    beta = [Aug[r][M] for r in range(M)]
    
    # Covariance/Inverse matrix
    XTX_inv = [Aug[r][M+1:] for r in range(M)]
    
    # Calculate predicted Y, residuals, RSS, TSS
    mean_y = sum(y_vals) / n
    predicted_y = []
    residuals = []
    for i in range(n):
        pred = beta[0] + sum(beta[j] * x_matrix[i][j-1] for j in range(1, M))
        predicted_y.append(pred)
        residuals.append(y_vals[i] - pred)
        
    rss = sum(r**2 for r in residuals)
    tss = sum((y - mean_y)**2 for y in y_vals)
    ess = tss - rss
    
    df_model = k
    df_residual = n - k - 1
    df_total = n - 1
    
    r2 = 1.0 - (rss / tss) if tss > 0 else 0.0
    r2_adj = 1.0 - ((rss / df_residual) / (tss / df_total)) if tss > 0 and df_residual > 0 else 0.0
    
    msm = ess / df_model
    msr = rss / df_residual
    
    # Standard errors of coefficients
    coefficients = {}
    
    # Intercept (index 0)
    se_int = math.sqrt(max(0.0, msr * XTX_inv[0][0]))
    t_int = beta[0] / se_int if se_int > 0 else 0.0
    p_int = student_t_p_value(t_int, df_residual)
    
    coefficients["intercept"] = {
        "coef": round(beta[0], 4),
        "std_err": round(se_int, 4),
        "t_stat": round(t_int, 4),
        "p_value": round(p_int, 6)
    }
    
    # Independent variables coefficients
    for j in range(1, M):
        var_name = x_fields[j-1]
        se_coef = math.sqrt(max(0.0, msr * XTX_inv[j][j]))
        t_coef = beta[j] / se_coef if se_coef > 0 else 0.0
        p_coef = student_t_p_value(t_coef, df_residual)
        
        coefficients[var_name] = {
            "coef": round(beta[j], 4),
            "std_err": round(se_coef, 4),
            "t_stat": round(t_coef, 4),
            "p_value": round(p_coef, 6)
        }
        
    # For backward-compatibility with simple regression tests expecting "slope"
    if k == 1 and fields_x is None:
        coefficients["slope"] = coefficients[x_fields[0]]
        
    f_stat = msm / msr if msr > 0 else 0.0
    f_p_val = f_p_value(f_stat, df_model, df_residual)
    
    res = {
        "type": "regress",
        "label": step.get("label", f"Linear Regression: {field_y} on {', '.join(x_fields)}"),
        "field_y": field_y,
        "fields_x": x_fields,
        "field_x": x_fields[0] if k == 1 and fields_x is None else None,
        "observations": n,
        "r_squared": round(r2, 4),
        "adj_r_squared": round(r2_adj, 4),
        "f_statistic": round(f_stat, 4),
        "f_p_value": round(f_p_val, 6),
        "coefficients": coefficients
    }
    
    # 4. Breusch-Pagan test for heteroskedasticity (hettest)
    if run_hettest:
        # Dependent variable for auxiliary regression: squared residuals
        E2 = [r**2 for r in residuals]
        
        # Calculate X^T E2
        XTE2 = [0.0 for _ in range(M)]
        for r in range(M):
            val = 0.0
            for i in range(n):
                val += X[i][r] * E2[i]
            XTE2[r] = val
            
        # Solve for gamma = (X^T X)^-1 * (X^T E2)
        gamma = [0.0 for _ in range(M)]
        for r in range(M):
            gamma[r] = sum(XTX_inv[r][c] * XTE2[c] for c in range(M))
            
        # Predicted E2
        pred_E2 = []
        for i in range(n):
            pred = gamma[0] + sum(gamma[j] * x_matrix[i][j-1] for j in range(1, M))
            pred_E2.append(pred)
            
        mean_E2 = sum(E2) / n
        tss_aux = sum((e2 - mean_E2)**2 for e2 in E2)
        rss_aux = sum((E2[i] - pred_E2[i])**2 for i in range(n))
        
        r2_aux = 1.0 - (rss_aux / tss_aux) if tss_aux > 0 else 0.0
        
        lm_stat = n * r2_aux
        hettest_p = chi2_p_value(lm_stat, k)
        
        res["hettest"] = {
            "lm_statistic": round(lm_stat, 4),
            "df": k,
            "p_value": round(hettest_p, 6)
        }
        
    return res


def _run_ttest(collection: Collection, match: dict, step: dict) -> dict:
    """Stata-style ttest comparing means of numeric field grouped by group_field."""
    field = step["field"]
    group_field = step["group_field"]
    
    pipeline = []
    if match:
        pipeline.append({"$match": match})
    pipeline += [
        {"$match": {field: {"$ne": None}, group_field: {"$ne": None}}},
        {"$project": {field: 1, group_field: 1, "_id": 0}}
    ]
    raw = list(collection.aggregate(pipeline))
    
    def get_val(doc, path):
        parts = path.split(".")
        val = doc
        for p in parts:
            if isinstance(val, dict) and p in val:
                val = val[p]
            else:
                return None
        return val

    groups = {}
    for doc in raw:
        v = get_val(doc, field)
        g_val = get_val(doc, group_field)
        if isinstance(v, (int, float)) and g_val is not None:
            groups.setdefault(str(g_val), []).append(float(v))
            
    group_names = sorted(groups.keys())
    if len(group_names) < 2:
        return {
            "type": "ttest",
            "field": field,
            "group_field": group_field,
            "label": step.get("label", f"t-test: {field} by {group_field}"),
            "error": "Insufficient groups found (needs exactly two distinct groups)"
        }
        
    g1_name = group_names[0]
    g2_name = group_names[1]
    g1_vals = groups[g1_name]
    g2_vals = groups[g2_name]
    
    n1 = len(g1_vals)
    n2 = len(g2_vals)
    
    if n1 < 2 or n2 < 2:
        return {
            "type": "ttest",
            "field": field,
            "group_field": group_field,
            "label": step.get("label", f"t-test: {field} by {group_field}"),
            "error": "Insufficient observations in groups (each group needs at least 2 observations)"
        }
        
    mean1 = sum(g1_vals) / n1
    mean2 = sum(g2_vals) / n2
    
    var1 = sum((x - mean1) ** 2 for x in g1_vals) / (n1 - 1)
    var2 = sum((x - mean2) ** 2 for x in g2_vals) / (n2 - 1)
    
    se1_sq = var1 / n1
    se2_sq = var2 / n2
    
    denom = math.sqrt(se1_sq + se2_sq)
    if denom == 0:
        return {
            "type": "ttest",
            "field": field,
            "group_field": group_field,
            "label": step.get("label", f"t-test: {field} by {group_field}"),
            "error": "Division by zero (both groups have zero variance)"
        }
        
    t_stat = (mean1 - mean2) / denom
    
    df_numerator = (se1_sq + se2_sq) ** 2
    df_denominator = ((se1_sq ** 2) / (n1 - 1)) + ((se2_sq ** 2) / (n2 - 1))
    df = df_numerator / df_denominator
    
    p_val = student_t_p_value(t_stat, df)
    
    return {
        "type": "ttest",
        "label": step.get("label", f"Welch's t-test: {field} by {group_field}"),
        "field": field,
        "group_field": group_field,
        "groups": {
            g1_name: {
                "obs": n1,
                "mean": round(mean1, 4),
                "std_dev": round(math.sqrt(var1), 4),
                "std_err": round(math.sqrt(se1_sq), 4)
            },
            g2_name: {
                "obs": n2,
                "mean": round(mean2, 4),
                "std_dev": round(math.sqrt(var2), 4),
                "std_err": round(math.sqrt(se2_sq), 4)
            }
        },
        "welch_ttest": {
            "statistic": round(t_stat, 4),
            "df": round(df, 2),
            "p_value": round(p_val, 6)
        }
    }


def _run_pwcorr(collection: Collection, match: dict, step: dict) -> dict:
    """Stata-style pwcorr: pairwise correlation matrix with significance."""
    fields = step.get("fields", [])
    show_sig = step.get("sig", True)
    
    # 1. Fetch data
    pipeline = []
    if match:
        pipeline.append({"$match": match})
    
    project = {f: 1 for f in fields}
    project["_id"] = 0
    pipeline.append({"$project": project})
    
    raw = list(collection.aggregate(pipeline))
    
    def get_val(doc, path):
        parts = path.split(".")
        val = doc
        for p in parts:
            if isinstance(val, dict) and p in val:
                val = val[p]
            else:
                return None
        return val

    # 2. Extract values per document for each field
    parsed_docs = []
    for doc in raw:
        parsed_doc = {}
        for f in fields:
            val = get_val(doc, f)
            if isinstance(val, (int, float)):
                parsed_doc[f] = float(val)
        parsed_docs.append(parsed_doc)
        
    # 3. Calculate pairwise correlations
    matrix = {}
    for f1 in fields:
        matrix[f1] = {}
        for f2 in fields:
            # Gather valid pairs
            pairs = []
            for pd in parsed_docs:
                if f1 in pd and f2 in pd:
                    pairs.append((pd[f1], pd[f2]))
            
            n = len(pairs)
            if n < 3:
                matrix[f1][f2] = {
                    "coef": None,
                    "p_value": None,
                    "obs": n
                }
                continue
                
            x_vals = [p[0] for p in pairs]
            y_vals = [p[1] for p in pairs]
            
            mean_x = sum(x_vals) / n
            mean_y = sum(y_vals) / n
            
            var_x = sum((x - mean_x) ** 2 for x in x_vals)
            var_y = sum((y - mean_y) ** 2 for y in y_vals)
            
            if var_x == 0 or var_y == 0:
                matrix[f1][f2] = {
                    "coef": None,
                    "p_value": None,
                    "obs": n
                }
                continue
                
            cov_xy = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
            
            r = cov_xy / math.sqrt(var_x * var_y)
            r = max(-1.0, min(1.0, r))
            
            if abs(r) == 1.0:
                p_val = 0.0
            else:
                t_stat = r * math.sqrt((n - 2) / (1.0 - r**2))
                p_val = student_t_p_value(t_stat, n - 2)
                
            res = {
                "coef": round(r, 4),
                "obs": n
            }
            if show_sig:
                res["p_value"] = round(p_val, 6)
                
            matrix[f1][f2] = res
            
    return {
        "type": "pwcorr",
        "label": step.get("label", "Pairwise correlation matrix"),
        "fields": fields,
        "matrix": matrix
    }


def _run_tabstat(collection: Collection, match: dict, step: dict) -> dict:
    """Stata-style tabstat: grouped summary table."""
    fields = step.get("fields", [])
    by_field = step.get("by")
    stats = step.get("statistics", ["mean", "count", "sd", "min", "max"])
    
    # 1. Fetch data
    pipeline = []
    if match:
        pipeline.append({"$match": match})
        
    project = {f: 1 for f in fields}
    if by_field:
        project[by_field] = 1
    project["_id"] = 0
    pipeline.append({"$project": project})
    
    raw = list(collection.aggregate(pipeline))
    
    def get_val(doc, path):
        parts = path.split(".")
        val = doc
        for p in parts:
            if isinstance(val, dict) and p in val:
                val = val[p]
            else:
                return None
        return val

    # Group the observations
    groups = {}
    for doc in raw:
        if by_field:
            by_val = get_val(doc, by_field)
            if by_val is None:
                continue
            by_val_str = str(by_val)
        else:
            by_val_str = "overall"
            
        groups.setdefault(by_val_str, {})
        for f in fields:
            groups[by_val_str].setdefault(f, [])
            val = get_val(doc, f)
            if isinstance(val, (int, float)):
                groups[by_val_str][f].append(float(val))
                
    sorted_group_names = sorted(groups.keys())
    
    def get_percentile(vals, p):
        n = len(vals)
        if n == 0:
            return None
        sorted_vals = sorted(vals)
        idx = (p / 100.0) * (n - 1)
        low = math.floor(idx)
        high = math.ceil(idx)
        if low == high:
            return sorted_vals[low]
        return sorted_vals[low] + (idx - low) * (sorted_vals[high] - sorted_vals[low])

    results = {}
    for group_name in sorted_group_names:
        results[group_name] = {}
        for f in fields:
            vals = groups[group_name].get(f, [])
            n = len(vals)
            
            group_stats = {}
            for stat in stats:
                if stat == "count":
                    group_stats["count"] = n
                elif stat == "mean":
                    group_stats["mean"] = round(sum(vals) / n, 4) if n > 0 else None
                elif stat == "sum":
                    group_stats["sum"] = round(sum(vals), 4) if n > 0 else 0.0
                elif stat == "min":
                    group_stats["min"] = min(vals) if n > 0 else None
                elif stat == "max":
                    group_stats["max"] = max(vals) if n > 0 else None
                elif stat in ("sd", "std_dev"):
                    if n < 2:
                        group_stats[stat] = None
                    else:
                        m = sum(vals) / n
                        var = sum((x - m)**2 for x in vals) / (n - 1)
                        group_stats[stat] = round(math.sqrt(var), 4)
                elif stat in ("var", "variance"):
                    if n < 2:
                        group_stats[stat] = None
                    else:
                        m = sum(vals) / n
                        var = sum((x - m)**2 for x in vals) / (n - 1)
                        group_stats[stat] = round(var, 4)
                elif stat in ("median", "p50"):
                    group_stats[stat] = round(get_percentile(vals, 50), 4) if n > 0 else None
                elif stat == "p25":
                    group_stats["p25"] = round(get_percentile(vals, 25), 4) if n > 0 else None
                elif stat == "p75":
                    group_stats["p75"] = round(get_percentile(vals, 75), 4) if n > 0 else None
                    
            results[group_name][f] = group_stats
            
    return {
        "type": "tabstat",
        "label": step.get("label", "Grouped Summary Table"),
        "fields": fields,
        "by": by_field,
        "results": results
    }


def _run_codebook(collection: Collection, match: dict, step: dict) -> dict:
    """Stata-style codebook: data diagnostic profile."""
    fields = step.get("fields", [])
    
    # 1. Fetch data
    pipeline = []
    if match:
        pipeline.append({"$match": match})
        
    project = {f: 1 for f in fields}
    project["_id"] = 0
    pipeline.append({"$project": project})
    
    raw = list(collection.aggregate(pipeline))
    
    def get_val(doc, path):
        parts = path.split(".")
        val = doc
        for p in parts:
            if isinstance(val, dict) and p in val:
                val = val[p]
            else:
                return None
        return val

    fields_result = {}
    for f in fields:
        all_vals = []
        missing_count = 0
        
        for doc in raw:
            val = get_val(doc, f)
            if val is None:
                missing_count += 1
            else:
                all_vals.append(val)
                
        obs_count = len(all_vals)
        if obs_count == 0:
            fields_result[f] = {
                "data_type": "unknown",
                "obs": 0,
                "missing": missing_count,
                "unique": 0
            }
            continue
            
        def make_hashable(v):
            if isinstance(v, list):
                return tuple(v)
            if isinstance(v, dict):
                return str(v)
            return v
            
        unique_vals = set(make_hashable(v) for v in all_vals)
        unique_count = len(unique_vals)
        
        numeric_vals = [float(v) for v in all_vals if isinstance(v, (int, float))]
        is_numeric = len(numeric_vals) > 0.5 * obs_count
        
        field_info = {
            "data_type": "numeric" if is_numeric else "string",
            "obs": obs_count,
            "missing": missing_count,
            "unique": unique_count
        }
        
        if is_numeric and len(numeric_vals) > 0:
            numeric_vals.sort()
            n_num = len(numeric_vals)
            mean_val = sum(numeric_vals) / n_num
            min_val = numeric_vals[0]
            max_val = numeric_vals[-1]
            
            std_dev = 0.0
            if n_num > 1:
                var = sum((x - mean_val)**2 for x in numeric_vals) / (n_num - 1)
                std_dev = math.sqrt(var)
                
            def get_pct(p):
                idx = (p / 100.0) * (n_num - 1)
                low = math.floor(idx)
                high = math.ceil(idx)
                if low == high:
                    return numeric_vals[low]
                return numeric_vals[low] + (idx - low) * (numeric_vals[high] - numeric_vals[low])
                
            field_info["numeric_stats"] = {
                "mean": round(mean_val, 4),
                "std_dev": round(std_dev, 4),
                "min": min_val,
                "max": max_val,
                "percentiles": {
                    "10": round(get_pct(10), 4),
                    "25": round(get_pct(25), 4),
                    "50": round(get_pct(50), 4),
                    "75": round(get_pct(75), 4),
                    "90": round(get_pct(90), 4)
                }
            }
            
        if not is_numeric or unique_count <= 10:
            freqs = {}
            for v in all_vals:
                v_str = str(v)
                freqs[v_str] = freqs.get(v_str, 0) + 1
                
            sorted_freqs = sorted(freqs.items(), key=lambda item: (-item[1], item[0]))
            top_freqs = sorted_freqs[:10]
            field_info["frequencies"] = [
                {
                    "value": val,
                    "count": cnt,
                    "percent": round((cnt / obs_count) * 100.0, 2)
                }
                for val, cnt in top_freqs
            ]
            
        fields_result[f] = field_info
        
    return {
        "type": "codebook",
        "label": step.get("label", "Codebook Data Diagnostic Profile"),
        "fields": fields_result
    }


def _run_oneway_anova(collection: Collection, match: dict, step: dict) -> dict:
    """Stata-style oneway: one-way Analysis of Variance."""
    field = step["field"]
    group_field = step["group_field"]
    
    # 1. Fetch data
    pipeline = []
    if match:
        pipeline.append({"$match": match})
        
    pipeline += [
        {"$match": {field: {"$ne": None}, group_field: {"$ne": None}}},
        {"$project": {field: 1, group_field: 1, "_id": 0}}
    ]
    raw = list(collection.aggregate(pipeline))
    
    def get_val(doc, path):
        parts = path.split(".")
        val = doc
        for p in parts:
            if isinstance(val, dict) and p in val:
                val = val[p]
            else:
                return None
        return val

    groups = {}
    for doc in raw:
        v = get_val(doc, field)
        g_val = get_val(doc, group_field)
        if isinstance(v, (int, float)) and g_val is not None:
            groups.setdefault(str(g_val), []).append(float(v))
            
    groups = {g: vals for g, vals in groups.items() if len(vals) > 0}
    
    k = len(groups)
    all_values = []
    for vals in groups.values():
        all_values.extend(vals)
    N = len(all_values)
    
    if k < 2 or N < k + 1:
        return {
            "type": "oneway_anova",
            "field": field,
            "group_field": group_field,
            "label": step.get("label", f"One-way ANOVA: {field} by {group_field}"),
            "error": "Insufficient groups or observations to run ANOVA"
        }
        
    mean_overall = sum(all_values) / N
    
    ssb = 0.0
    ssw = 0.0
    for g, vals in groups.items():
        n_j = len(vals)
        mean_j = sum(vals) / n_j
        ssb += n_j * (mean_j - mean_overall)**2
        ssw += sum((x - mean_j)**2 for x in vals)
        
    sst = ssb + ssw
    
    df_between = k - 1
    df_within = N - k
    df_total = N - 1
    
    msb = ssb / df_between if df_between > 0 else 0.0
    msw = ssw / df_within if df_within > 0 else 0.0
    
    if msw == 0:
        return {
            "type": "oneway_anova",
            "field": field,
            "group_field": group_field,
            "label": step.get("label", f"One-way ANOVA: {field} by {group_field}"),
            "error": "Division by zero: Within-group variance is zero"
        }
        
    f_stat = msb / msw
    p_val = f_p_value(f_stat, df_between, df_within)
    
    return {
        "type": "oneway_anova",
        "field": field,
        "group_field": group_field,
        "label": step.get("label", f"One-way ANOVA: {field} by {group_field}"),
        "anova_table": {
            "between": {
                "ss": round(ssb, 4),
                "df": df_between,
                "ms": round(msb, 4)
            },
            "within": {
                "ss": round(ssw, 4),
                "df": df_within,
                "ms": round(msw, 4)
            },
            "total": {
                "ss": round(sst, 4),
                "df": df_total
            }
        },
        "f_statistic": round(f_stat, 4),
        "p_value": round(p_val, 6)
    }
def _run_transform(collection: Collection, match: dict, step: dict) -> dict:
    """Stata-style transform step: reports active variable transformations."""
    transformations = step.get("transformations", [])
    return {
        "type": "transform",
        "label": step.get("label", "Data Transformations"),
        "status": "applied",
        "count": len(transformations),
        "transformations": [
            {"field": t.get("field"), "operation": t.get("operation"), "source_field": t.get("source_field")}
            for t in transformations
        ]
    }


# ---------------------------------------------------------------------------
# Step dispatcher
# ---------------------------------------------------------------------------

_STEP_RUNNERS = {
    # Original
    "frequency":             _run_frequency,
    "array_frequency":       _run_array_frequency,
    "aggregate":             _run_aggregate,
    "crosstab":              _run_crosstab,
    "top_n":                 _run_top_n,
    "missing":               _run_missing,
    "segment":               _run_segment,
    # Advanced
    "time_series":           _run_time_series,
    "nps":                   _run_nps,
    "percentile":            _run_percentile,
    "pivot_aggregate":       _run_pivot_aggregate,
    "boolean_summary":       _run_boolean_summary,
    "conditional_frequency": _run_conditional_frequency,
    "correlation":           _run_correlation,
    "funnel":                _run_funnel,
    "rank":                  _run_rank,
    # Stata-style
    "summarize":             _run_summarize,
    "tabulate_chi2":         _run_tabulate_chi2,
    "regress":               _run_regress,
    "ttest":                 _run_ttest,
    "pwcorr":                _run_pwcorr,
    "tabstat":               _run_tabstat,
    "codebook":              _run_codebook,
    "oneway_anova":          _run_oneway_anova,
    "transform":             _run_transform,
}


class TransformedCollection:
    """Proxy wrapper for pymongo Collection to intercept aggregate pipelines and insert transformations."""
    def __init__(self, original_collection: Collection, transformation_stages: list):
        self.coll = original_collection
        self.stages = transformation_stages
        
    def aggregate(self, pipeline, *args, **kwargs):
        new_pipeline = []
        inserted = False
        
        for stage in pipeline:
            new_pipeline.append(stage)
            if "$match" in stage and not inserted:
                new_pipeline.extend(self.stages)
                inserted = True
                
        if not inserted:
            new_pipeline = self.stages + new_pipeline
            
        return self.coll.aggregate(new_pipeline, *args, **kwargs)
        
    def __getattr__(self, name):
        return getattr(self.coll, name)


def _build_transformation_stages(collection: Collection, match: dict, transformations: list) -> list:
    stages = []
    for t in transformations:
        field = t.get("field")
        op = t.get("operation")
        src = t.get("source_field")
        
        if not field or not op or not src:
            continue
            
        expr = None
        if op == "log":
            expr = {"$cond": [{"$gt": ["$" + src, 0]}, {"$ln": "$" + src}, None]}
        elif op == "sqrt":
            expr = {"$cond": [{"$gte": ["$" + src, 0]}, {"$sqrt": "$" + src}, None]}
        elif op == "center":
            mean_val = 0.0
            try:
                mean_res = list(collection.aggregate([
                    *([{"$match": match}] if match else []),
                    {"$match": {src: {"$ne": None}}},
                    {"$group": {"_id": None, "avg_val": {"$avg": "$" + src}}}
                ]))
                if mean_res and mean_res[0]["avg_val"] is not None:
                    mean_val = float(mean_res[0]["avg_val"])
            except Exception:
                pass
            expr = {"$subtract": ["$" + src, mean_val]}
        elif op == "zscore":
            mean_val = 0.0
            std_val = 1.0
            try:
                stats_res = list(collection.aggregate([
                    *([{"$match": match}] if match else []),
                    {"$match": {src: {"$ne": None}}},
                    {"$group": {
                        "_id": None, 
                        "avg_val": {"$avg": "$" + src},
                        "std_val": {"$stdDevSamp": "$" + src}
                    }}
                ]))
                if stats_res and stats_res[0]:
                    if stats_res[0]["avg_val"] is not None:
                        mean_val = float(stats_res[0]["avg_val"])
                    if stats_res[0]["std_val"] is not None:
                        std_val = float(stats_res[0]["std_val"])
            except Exception:
                pass
            expr = {"$cond": [{"$eq": [std_val, 0.0]}, 0.0, {"$divide": [{"$subtract": ["$" + src, mean_val]}, std_val]}]}
        elif op == "recode":
            recode_map = t.get("map", {})
            default_val = t.get("default", None)
            branches = []
            for key, val in recode_map.items():
                branches.append({
                    "case": {"$eq": ["$" + src, key]},
                    "then": val
                })
            if branches:
                expr = {
                    "$switch": {
                        "branches": branches,
                        "default": default_val
                    }
                }
            else:
                expr = "$" + src
                
        if expr is not None:
            stages.append({"$addFields": {field: expr}})
            
    return stages


def _run_step(collection: Collection, match: dict, step: dict) -> dict:
    step_type = step.get("type")
    runner = _STEP_RUNNERS.get(step_type)
    if not runner:
        raise ValueError(f"Unknown step type: '{step_type}'")
    return runner(collection, match, step)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_analysis(db, analysis_def: dict) -> dict:
    """
    Execute an analysis definition against MongoDB.

    Parameters
    ----------
    db              : pymongo Database object
    analysis_def    : the analysis definition dict (parsed from stored JSON)

    Returns
    -------
    dict with keys:
        name, description, total_responses, filters_applied, results
    """
    source_collection_name = analysis_def.get(
        "source_collection", "form_responses"
    )
    collection: Collection = db[source_collection_name]

    # Build the top-level match filter
    filters = analysis_def.get("filters", [])
    match = _build_mongo_filter(filters)

    # Collect transformations
    transformations = list(analysis_def.get("transformations", []))
    for step in analysis_def.get("steps", []):
        if step.get("type") == "transform":
            transformations.extend(step.get("transformations", []))
            
    # Build transformation stages and wrap collection
    trans_stages = _build_transformation_stages(collection, match, transformations)
    if trans_stages:
        collection = TransformedCollection(collection, trans_stages)

    # Total matching docs
    count_pipeline = [*([ {"$match": match}] if match else []), {"$count": "total"}]
    count_raw = list(collection.aggregate(count_pipeline))
    total = count_raw[0]["total"] if count_raw else 0

    # Run each step
    results = {}
    for step in analysis_def.get("steps", []):
        step_id = step.get("id", step.get("type"))
        results[step_id] = _run_step(collection, match, step)

    return {
        "name": analysis_def.get("name", "Unnamed Analysis"),
        "description": analysis_def.get("description", ""),
        "source_collection": source_collection_name,
        "filters_applied": filters,
        "total_matching_responses": total,
        "results": results,
    }
