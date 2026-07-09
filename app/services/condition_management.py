from __future__ import annotations

from app.services.condition_management_analysis import (
    analyze_condition_impact,
    collect_condition_usage,
    discover_usage,
    impact_analysis,
    validate_safe_delete,
)
from app.services.condition_management_approval import (
    ensure_publishable,
    rollback_approval_state,
    transition_approval_state,
)
from app.services.condition_management_async import (
    enqueue_async_evaluation,
    evaluate_condition_async,
    get_async_job_status,
)
from app.services.condition_management_core import (
    APPROVAL_TRANSITIONS,
    ConditionManagementError,
    diff_dict,
    serialize_condition,
)
from app.services.condition_management_graph import (
    build_dependency_graph,
    calculate_complexity_score,
    detect_circular_references,
    reverse_dependency_graph,
)
from app.services.condition_management_monitoring import (
    get_monitoring_snapshot,
    monitoring_dashboard_snapshot,
    operator_metadata,
    record_evaluation_stat,
)
from app.services.condition_management_presets import (
    condition_presets,
    create_or_update_preset,
    export_presets,
    import_presets,
    sync_auto_update_presets,
)
from app.services.condition_management_versioning import (
    create_condition_version_snapshot,
    diff_condition_versions,
    export_conditions,
    get_condition_versions,
    import_conditions,
    list_condition_versions,
    record_condition_version,
    restore_condition_version,
    rollback_condition_to_version,
)

# Backward-compatible aliases for previously exposed private helpers.
_serialize_condition = serialize_condition
_diff_dict = diff_dict

__all__ = [
    "APPROVAL_TRANSITIONS",
    "ConditionManagementError",
    "_serialize_condition",
    "_diff_dict",
    "record_condition_version",
    "list_condition_versions",
    "restore_condition_version",
    "ensure_publishable",
    "transition_approval_state",
    "rollback_approval_state",
    "create_or_update_preset",
    "export_presets",
    "import_presets",
    "sync_auto_update_presets",
    "discover_usage",
    "impact_analysis",
    "record_evaluation_stat",
    "get_monitoring_snapshot",
    "enqueue_async_evaluation",
    "get_async_job_status",
    "operator_metadata",
    "condition_presets",
    "build_dependency_graph",
    "reverse_dependency_graph",
    "detect_circular_references",
    "calculate_complexity_score",
    "collect_condition_usage",
    "validate_safe_delete",
    "create_condition_version_snapshot",
    "get_condition_versions",
    "rollback_condition_to_version",
    "diff_condition_versions",
    "export_conditions",
    "import_conditions",
    "analyze_condition_impact",
    "evaluate_condition_async",
    "monitoring_dashboard_snapshot",
]
