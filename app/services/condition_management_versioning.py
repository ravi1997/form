from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

from mongoengine.errors import NotUniqueError, ValidationError

from app.models.condition_management import ConditionVersion
from app.models.form import Condition
from app.services.condition_management_core import (
    ConditionManagementError,
    diff_dict,
    serialize_condition,
)


def record_condition_version(
    condition: Condition,
    actor_user_uuid: Optional[str] = None,
    action: str = "update",
    changelog: str = "",
) -> ConditionVersion:
    latest = (
        ConditionVersion.objects(condition_uuid=condition.uuid)
        .order_by("-version")
        .first()
    )
    new_version = (latest.version + 1) if latest else 1
    snapshot = serialize_condition(condition)
    prev_snapshot = latest.snapshot if latest else {}
    entry = ConditionVersion(
        condition_uuid=condition.uuid,
        version=new_version,
        snapshot=snapshot,
        diff=diff_dict(prev_snapshot, snapshot),
        changelog=changelog,
        action=action,
        actor_user_uuid=actor_user_uuid,
    )
    entry.save()
    return entry


def list_condition_versions(condition_uuid: str) -> List[ConditionVersion]:
    return list(
        ConditionVersion.objects(condition_uuid=condition_uuid).order_by("version")
    )


def restore_condition_version(
    condition_uuid: str, version: int, actor_user_uuid: Optional[str] = None
) -> Condition:
    item = Condition.objects(uuid=condition_uuid).first()
    if not item:
        raise ConditionManagementError("Condition not found")
    version_entry = ConditionVersion.objects(
        condition_uuid=condition_uuid, version=version
    ).first()
    if not version_entry:
        raise ConditionManagementError("Version not found")

    data = copy.deepcopy(version_entry.snapshot)
    for key in ["uuid", "updated_at"]:
        data.pop(key, None)

    for key, value in data.items():
        setattr(item, key, value)

    item.save()
    record_condition_version(
        item,
        actor_user_uuid=actor_user_uuid,
        action="restore",
        changelog=f"restored to version {version}",
    )
    return item


def create_condition_version_snapshot(
    condition: Condition,
    actor_user_uuid: Optional[str] = None,
    reason: str = "update",
) -> Dict[str, Any]:
    version = record_condition_version(
        condition,
        actor_user_uuid=actor_user_uuid,
        action="update",
        changelog=reason,
    )
    return {
        "condition_uuid": version.condition_uuid,
        "version": version.version,
        "changelog": version.changelog,
        "created_at": version.created_at.isoformat() if version.created_at else None,
    }


def get_condition_versions(condition: Condition) -> List[Dict[str, Any]]:
    return [
        {
            "version": v.version,
            "snapshot": v.snapshot,
            "diff": v.diff,
            "changelog": v.changelog,
            "action": v.action,
            "actor_user_uuid": v.actor_user_uuid,
            "created_at": v.created_at.isoformat() if v.created_at else None,
        }
        for v in list_condition_versions(condition.uuid)
    ]


def rollback_condition_to_version(
    condition: Condition,
    version_id: str,
    actor_user_uuid: Optional[str] = None,
) -> Condition:
    try:
        version_number = int(str(version_id).lstrip("v"))
    except ValueError as exc:
        raise ConditionManagementError("Invalid version id") from exc
    return restore_condition_version(
        condition.uuid,
        version_number,
        actor_user_uuid=actor_user_uuid,
    )


def diff_condition_versions(
    condition: Condition, left_version: str, right_version: str
) -> Dict[str, Any]:
    try:
        left = int(str(left_version).lstrip("v"))
        right = int(str(right_version).lstrip("v"))
    except ValueError as exc:
        raise ConditionManagementError("Invalid version id") from exc

    left_entry = ConditionVersion.objects(
        condition_uuid=condition.uuid, version=left
    ).first()
    right_entry = ConditionVersion.objects(
        condition_uuid=condition.uuid, version=right
    ).first()
    if not left_entry or not right_entry:
        raise ConditionManagementError("Version not found")
    return {
        "condition_uuid": condition.uuid,
        "from_version": left_version,
        "to_version": right_version,
        "diff": diff_dict(left_entry.snapshot, right_entry.snapshot),
    }


def import_conditions(
    items: List[Dict[str, Any]], overwrite: bool = False
) -> Dict[str, Any]:
    created = 0
    updated = 0
    skipped = 0
    errors: List[Dict[str, Any]] = []
    for raw in items:
        try:
            condition_uuid = raw["uuid"]
            existing = Condition.objects(uuid=condition_uuid).first()
            if existing and not overwrite:
                skipped += 1
                continue
            target = existing or Condition(uuid=condition_uuid)
            for field in (
                "conditionType",
                "expression",
                "targetField",
                "sourceSectionUuid",
                "operator",
                "operands",
                "isNegated",
                "logicalJoinType",
                "isActive",
                "errorMessage",
                "description",
                "priority",
                "stopEvaluationIfTrue",
                "metadata",
                "status",
            ):
                if field in raw:
                    setattr(target, field, raw[field])
            if "subConditions" in raw:
                refs = []
                for sub_uuid in raw["subConditions"] or []:
                    sub_condition = Condition.objects(uuid=sub_uuid).first()
                    if sub_condition:
                        refs.append(sub_condition)
                target.subConditions = refs
            target.save()
            if existing:
                updated += 1
            else:
                created += 1
        except (ValidationError, NotUniqueError, ValueError, TypeError) as exc:
            errors.append({"uuid": raw.get("uuid"), "error": str(exc)})
    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
    }


def export_conditions() -> List[Dict[str, Any]]:
    return [serialize_condition(c) for c in Condition.objects]
