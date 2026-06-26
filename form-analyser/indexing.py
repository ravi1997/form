"""
indexing.py
-----------
Utility to parse analysis definitions and automatically ensure indexes exist on
referenced fields in MongoDB.
"""

from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

def ensure_analysis_indexes(db, analysis_def: dict) -> list[str]:
    """
    Parse the analysis definition for all query fields and ensure
    MongoDB indexes exist on the target collection.
    
    Returns a list of fields for which indexes were ensured.
    """
    source_col_name = analysis_def.get("source_collection", "form_responses")
    collection = db[source_col_name]
    
    fields_to_index = set()
    
    # 1. Filters
    for f in analysis_def.get("filters", []):
        if "field" in f and f["field"]:
            fields_to_index.add(f["field"])
            
    # 2. Steps
    for step in analysis_def.get("steps", []):
        stype = step.get("type")
        if not stype:
            continue
            
        # Simple field step types
        if stype in ("frequency", "array_frequency", "aggregate", "top_n", "missing", "nps", "percentile", "boolean_summary"):
            if "field" in step and step["field"]:
                fields_to_index.add(step["field"])
                
        # Crosstab
        elif stype == "crosstab":
            if "row_field" in step and step["row_field"]:
                fields_to_index.add(step["row_field"])
            if "col_field" in step and step["col_field"]:
                fields_to_index.add(step["col_field"])
                
        # Segment
        elif stype == "segment":
            if "filter" in step and isinstance(step["filter"], dict) and "field" in step["filter"] and step["filter"]["field"]:
                fields_to_index.add(step["filter"]["field"])
            # Sub-steps in segment
            for sub_step in step.get("sub_steps", []):
                if "field" in sub_step and sub_step["field"]:
                    fields_to_index.add(sub_step["field"])
                    
        # Time Series
        elif stype == "time_series":
            fields_to_index.add(step.get("date_field", "submitted_at"))
            if "value_field" in step and step["value_field"]:
                fields_to_index.add(step["value_field"])
                
        # Pivot Aggregate / Rank
        elif stype in ("pivot_aggregate", "rank"):
            if "group_field" in step and step["group_field"]:
                fields_to_index.add(step["group_field"])
            if "value_field" in step and step["value_field"]:
                fields_to_index.add(step["value_field"])
                
        # Conditional Frequency
        elif stype == "conditional_frequency":
            if "field" in step and step["field"]:
                fields_to_index.add(step["field"])
            if "condition_field" in step and step["condition_field"]:
                fields_to_index.add(step["condition_field"])
                
        # Correlation
        elif stype == "correlation":
            if "field_a" in step and step["field_a"]:
                fields_to_index.add(step["field_a"])
            if "field_b" in step and step["field_b"]:
                fields_to_index.add(step["field_b"])
                
        # Funnel
        elif stype == "funnel":
            for stage in step.get("stages", []):
                f = stage.get("filter", {})
                if isinstance(f, dict) and "field" in f and f["field"]:
                    fields_to_index.add(f["field"])
                    
    # Clean and filter out Mongo internal/default fields
    fields_to_index = {f for f in fields_to_index if f and f != "_id"}
    
    created_indexes = []
    for field in sorted(fields_to_index):
        try:
            # We can create a simple single-field ascending index
            collection.create_index(field)
            created_indexes.append(field)
            logger.info(f"Ensured index for field '{field}' on collection '{source_col_name}'")
        except Exception as e:
            logger.error(f"Failed to create index for field '{field}' on '{source_col_name}': {e}")
            
    return created_indexes
