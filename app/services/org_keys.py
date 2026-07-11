from __future__ import annotations


def resolve_org_role_key(org) -> str:
    org_uuid = getattr(org, "uuid", None)
    if org_uuid:
        return str(org_uuid)
    org_id = getattr(org, "id", None)
    if org_id is None:
        raise ValueError("Organization identifier is missing")
    return str(org_id)


def resolve_org_role_keys(org) -> tuple[str, ...]:
    keys = []
    org_uuid = getattr(org, "uuid", None)
    if org_uuid:
        keys.append(str(org_uuid))
    org_id = getattr(org, "id", None)
    if org_id is not None:
        legacy_key = str(org_id)
        if legacy_key not in keys:
            keys.append(legacy_key)
    return tuple(keys)
