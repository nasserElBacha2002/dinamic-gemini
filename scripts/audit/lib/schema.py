"""audit-status.json schema policy (Phase 0).

Policy:
- schema_version == 2: accepted as-is (after structural checks).
- legacy (missing schema_version or version 1): migrated via an explicit path
  when the document has the minimum required areas/tools; otherwise rejected.
- unknown / future schema_version: rejected.
- invalid schema_version type: rejected.
- missing required areas or required tools: rejected.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .gate_policy import REQUIRED_AREAS, REQUIRED_TOOL_RULES
from .statuses import SCHEMA_VERSION

LEGACY_SCHEMA_VERSION = 1
SUPPORTED_SCHEMA_VERSIONS = frozenset({SCHEMA_VERSION})
MIGRATABLE_LEGACY_VERSIONS = frozenset({LEGACY_SCHEMA_VERSION})


class SchemaValidationError(ValueError):
    """Raised when audit-status.json cannot be accepted."""


def _as_int_version(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _has_min_legacy_shape(doc: Dict[str, Any]) -> bool:
    areas = doc.get("areas")
    if not isinstance(areas, dict):
        return False
    for area in REQUIRED_AREAS:
        block = areas.get(area)
        if not isinstance(block, dict):
            return False
        tools = block.get("tools")
        if not isinstance(tools, dict) or not tools:
            return False
    return True


def migrate_legacy_to_v2(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Explicit legacy → v2 migration. Does not invent missing tools."""
    if not _has_min_legacy_shape(doc):
        raise SchemaValidationError(
            "legacy audit-status incomplete: missing required areas/tools for migration"
        )
    out = dict(doc)
    out["schema_version"] = SCHEMA_VERSION
    out.setdefault("parser_version", "legacy-migrated")
    out.setdefault("migration", {"from": doc.get("schema_version", "missing"), "to": SCHEMA_VERSION})
    return out


def validate_required_structure(doc: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    areas = doc.get("areas")
    if not isinstance(areas, dict):
        return ["areas missing or not an object"]

    for area in sorted(REQUIRED_AREAS):
        if area not in areas or not isinstance(areas.get(area), dict):
            errors.append(f"required area missing: {area}")
            continue
        tools = areas[area].get("tools")
        if not isinstance(tools, dict):
            errors.append(f"required area tools missing: {area}")
            continue
        for rule in REQUIRED_TOOL_RULES:
            if rule.area != area or not rule.required:
                continue
            if rule.tool not in tools:
                errors.append(f"required tool missing: {area}.{rule.tool}")
    return errors


def normalize_status_document(doc: Any) -> Tuple[Dict[str, Any], List[str]]:
    """Validate / migrate a status document.

    Returns (normalized_doc, notes). Raises SchemaValidationError on reject.
    """
    notes: List[str] = []
    if not isinstance(doc, dict):
        raise SchemaValidationError("audit-status root must be an object")

    raw_version = doc.get("schema_version", None)
    if "schema_version" not in doc:
        notes.append("schema_version missing; attempting legacy migration")
        normalized = migrate_legacy_to_v2(doc)
    else:
        version = _as_int_version(raw_version)
        if version is None:
            raise SchemaValidationError(
                f"invalid schema_version type/value: {raw_version!r}"
            )
        if version in SUPPORTED_SCHEMA_VERSIONS:
            normalized = dict(doc)
            notes.append(f"schema_version {version} accepted")
        elif version in MIGRATABLE_LEGACY_VERSIONS:
            notes.append(f"schema_version {version} legacy; migrating to {SCHEMA_VERSION}")
            normalized = migrate_legacy_to_v2(doc)
        else:
            raise SchemaValidationError(
                f"unknown/unsupported schema_version: {version} "
                f"(supported={sorted(SUPPORTED_SCHEMA_VERSIONS)})"
            )

    struct_errors = validate_required_structure(normalized)
    if struct_errors:
        raise SchemaValidationError("; ".join(struct_errors))

    return normalized, notes
