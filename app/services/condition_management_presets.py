from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from mongoengine.errors import NotUniqueError, ValidationError

from app.models.condition_management import ConditionPreset, ConditionPresetVersion
from app.models.form import Condition
from app.services.condition_management_core import ConditionManagementError, serialize_condition


def create_or_update_preset(
    *,
    preset_uuid: str,
    name: str,
    condition_uuid: str,
    description: Optional[str] = None,
    tags: Optional[List[str]] = None,
    references: Optional[List[str]] = None,
    auto_update: bool = False,
    actor_user_uuid: Optional[str] = None,
    changelog: str = "manual update",
) -> ConditionPreset:
    condition = Condition.objects(uuid=condition_uuid).first()
    if not condition:
        raise ConditionManagementError("Condition not found")

    snapshot = serialize_condition(condition)
    preset = ConditionPreset.objects(uuid=preset_uuid).first()
    if not preset:
        preset = ConditionPreset(
            uuid=preset_uuid,
            name=name,
            condition_uuid=condition_uuid,
            condition_snapshot=snapshot,
            description=description,
            tags=tags or [],
            references=references or [],
            auto_update=auto_update,
            created_by=actor_user_uuid,
            updated_by=actor_user_uuid,
        )
    else:
        preset.name = name
        preset.description = description or preset.description
        preset.tags = tags or preset.tags
        preset.references = references or preset.references
        preset.auto_update = auto_update
        preset.condition_uuid = condition_uuid
        preset.condition_snapshot = snapshot
        preset.updated_by = actor_user_uuid
        preset.current_version += 1
        preset.versions.append(
            ConditionPresetVersion(
                version=preset.current_version,
                condition_snapshot=snapshot,
                changelog=changelog,
            )
        )

    preset.save()
    return preset


def export_presets() -> Dict[str, Any]:
    presets = []
    for preset in ConditionPreset.objects:
        presets.append(
            {
                "uuid": preset.uuid,
                "name": preset.name,
                "description": preset.description,
                "condition_uuid": preset.condition_uuid,
                "condition_snapshot": preset.condition_snapshot,
                "current_version": preset.current_version,
                "versions": [
                    {
                        "version": v.version,
                        "condition_snapshot": v.condition_snapshot,
                        "changelog": v.changelog,
                        "created_at": v.created_at.isoformat() if v.created_at else None,
                    }
                    for v in (preset.versions or [])
                ],
                "references": list(preset.references or []),
                "auto_update": bool(preset.auto_update),
                "status": preset.status,
            }
        )
    return {"presets": presets, "exported_at": datetime.now(timezone.utc).isoformat() + "Z"}


def import_presets(
    payload: Dict[str, Any], actor_user_uuid: Optional[str] = None
) -> Dict[str, Any]:
    created = 0
    updated = 0
    failed: List[str] = []

    for preset in payload.get("presets", []):
        try:
            preset_uuid = preset["uuid"]
            name = preset["name"]
            condition_uuid = preset["condition_uuid"]
            existed = ConditionPreset.objects(uuid=preset_uuid).first() is not None
            create_or_update_preset(
                preset_uuid=preset_uuid,
                name=name,
                condition_uuid=condition_uuid,
                description=preset.get("description"),
                tags=preset.get("tags") or [],
                references=preset.get("references") or [],
                auto_update=bool(preset.get("auto_update", False)),
                actor_user_uuid=actor_user_uuid,
                changelog="import",
            )
            if existed:
                updated += 1
            else:
                created += 1
        except (
            ConditionManagementError,
            KeyError,
            ValidationError,
            NotUniqueError,
            ValueError,
            TypeError,
        ) as exc:
            failed.append(str(exc))

    return {
        "created": created,
        "updated": updated,
        "failed": failed,
    }


def sync_auto_update_presets(condition: Condition) -> int:
    count = 0
    for preset in ConditionPreset.objects(condition_uuid=condition.uuid, auto_update=True):
        preset.current_version += 1
        snapshot = serialize_condition(condition)
        preset.condition_snapshot = snapshot
        preset.versions.append(
            ConditionPresetVersion(
                version=preset.current_version,
                condition_snapshot=snapshot,
                changelog="auto update",
            )
        )
        preset.save()
        count += 1
    return count


def condition_presets() -> List[Dict[str, Any]]:
    return [
        {
            "uuid": preset.uuid,
            "name": preset.name,
            "description": preset.description,
            "condition_uuid": preset.condition_uuid,
            "current_version": preset.current_version,
            "status": preset.status,
            "tags": list(preset.tags or []),
        }
        for preset in ConditionPreset.objects
    ]
