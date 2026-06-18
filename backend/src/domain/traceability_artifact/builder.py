"""Phase 4.7 — deterministic traceability_manifest.json builder."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.domain.execution_image_manifest import (
    ExecutionImageManifest,
    ExecutionImageRole,
    composition_has_execution_image_manifest,
    require_manifest_from_composition,
)
from src.domain.result_evidence.entities import ResultEvidenceRecord, ResultEvidenceRole
from src.domain.result_evidence.mapper import compute_structural_has_valid_evidence
from src.domain.traceability import TraceabilityStatus, normalize_traceability_status
from src.domain.traceability_artifact.canonical_json import sha256_canonical_json
from src.pipeline.services.provider_execution_request import PROVIDER_IMAGE_MANIFEST_ORDER_KEY

TRACEABILITY_MANIFEST_SCHEMA_VERSION = "phase-4.7.traceability_manifest.v1"


@dataclass(frozen=True)
class TraceabilityManifestBuildInput:
    job_id: str
    inventory_id: str
    aisle_id: str
    run_id: str
    provider: str | None
    model_name: str | None
    created_at: datetime
    prompt_composition: dict[str, Any] | None
    run_metadata: dict[str, Any] | None
    result_evidence_rows: tuple[ResultEvidenceRecord, ...]
    manifest_required: bool = True


def _load_manifest(composition: dict[str, Any] | None) -> ExecutionImageManifest | None:
    if not composition_has_execution_image_manifest(composition):
        return None
    try:
        return require_manifest_from_composition(composition)
    except Exception:
        return None


def _manifest_section(manifest: ExecutionImageManifest | None) -> dict[str, Any] | None:
    if manifest is None:
        return None
    return manifest.to_dict()


def _provider_order_section(run_metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(run_metadata, dict):
        return {
            "status": "unavailable",
            "warning": "Provider image manifest order was unavailable.",
            "entries": [],
        }
    raw = run_metadata.get(PROVIDER_IMAGE_MANIFEST_ORDER_KEY)
    if not isinstance(raw, list) or not raw:
        return {
            "status": "unavailable",
            "warning": "Provider image manifest order was unavailable.",
            "entries": [],
        }
    entries: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        entry = {
            "provider_position": item.get("provider_position"),
            "manifest_entry_id": item.get("manifest_entry_id"),
            "source_image_id": item.get("source_image_id"),
            "role": item.get("role"),
        }
        if item.get("source_asset_id") is not None:
            entry["source_asset_id"] = item.get("source_asset_id")
        if item.get("payload_ordinal") is not None:
            entry["payload_ordinal"] = item.get("payload_ordinal")
        entries.append(entry)
    if not entries:
        return {
            "status": "unavailable",
            "warning": "Provider image manifest order was unavailable.",
            "entries": [],
        }
    return {"status": "available", "entries": entries}


def _artifact_displayable(
    row: ResultEvidenceRecord,
    *,
    manifest: ExecutionImageManifest | None,
    manifest_required: bool,
) -> bool:
    return compute_structural_has_valid_evidence(
        traceability_status=row.traceability_status,
        source_image_id=row.source_image_id,
        role=row.role,
        manifest=manifest,
        manifest_required=manifest_required,
    )


def _result_evidence_row_dict(
    row: ResultEvidenceRecord,
    *,
    manifest: ExecutionImageManifest | None,
    manifest_required: bool,
) -> dict[str, Any]:
    displayable = _artifact_displayable(
        row, manifest=manifest, manifest_required=manifest_required
    )
    return {
        "id": row.id,
        "job_id": row.job_id,
        "inventory_id": row.inventory_id,
        "aisle_id": row.aisle_id,
        "position_id": row.position_id,
        "entity_uid": row.entity_uid,
        "model_entity_id": row.model_entity_id,
        "raw_manifest_entry_id": row.raw_manifest_entry_id,
        "raw_source_image_id": row.raw_source_image_id,
        "resolved_manifest_entry_id": row.resolved_manifest_entry_id,
        "source_image_id": row.source_image_id,
        "source_asset_id": row.source_asset_id,
        "traceability_status": row.traceability_status,
        "traceability_warning": row.traceability_warning,
        "role": row.role.value if row.role is not None else None,
        "provider": row.provider,
        "model_name": row.model_name,
        "schema_version": row.schema_version,
        "manifest_version": row.manifest_version,
        "has_valid_evidence": row.has_valid_evidence,
        "evidence_kind": row.evidence_kind,
        "displayable": displayable,
    }


def _summary_counts(
    rows: list[dict[str, Any]],
) -> dict[str, int]:
    summary = {
        "total_evidence_rows": len(rows),
        "valid": 0,
        "invalid": 0,
        "missing": 0,
        "unvalidated": 0,
        "displayable": 0,
        "not_displayable": 0,
        "reference_rejected": 0,
        "unknown_identifier": 0,
        "conflicting_identifier": 0,
        "manifest_unavailable": 0,
        "manifest_invalid": 0,
    }
    for row in rows:
        status = normalize_traceability_status(row.get("traceability_status"))
        if status == TraceabilityStatus.VALID.value:
            summary["valid"] += 1
        elif status == TraceabilityStatus.INVALID.value:
            summary["invalid"] += 1
        elif status == TraceabilityStatus.MISSING.value:
            summary["missing"] += 1
        elif status == TraceabilityStatus.UNVALIDATED.value:
            summary["unvalidated"] += 1
            summary["manifest_unavailable"] += 1

        if row.get("displayable") is True:
            summary["displayable"] += 1
        else:
            summary["not_displayable"] += 1

        role = row.get("role")
        if role == ResultEvidenceRole.REFERENCE_IMAGE.value:
            summary["reference_rejected"] += 1

        warning = (row.get("traceability_warning") or "").lower()
        if "conflicting" in warning:
            summary["conflicting_identifier"] += 1
        if status == TraceabilityStatus.INVALID.value and role != ResultEvidenceRole.REFERENCE_IMAGE.value:
            mid = row.get("resolved_manifest_entry_id") or row.get("raw_manifest_entry_id")
            if isinstance(mid, str) and mid.strip().upper().startswith("IMG_"):
                summary["unknown_identifier"] += 1

    return summary


def build_traceability_manifest(payload: TraceabilityManifestBuildInput) -> dict[str, Any]:
    """Build deterministic traceability_manifest.json content."""
    manifest = _load_manifest(payload.prompt_composition)
    sorted_rows = sorted(
        payload.result_evidence_rows,
        key=lambda r: (
            r.entity_uid or "",
            r.model_entity_id or "",
            r.id,
        ),
    )
    evidence_dicts = [
        _result_evidence_row_dict(
            row,
            manifest=manifest,
            manifest_required=payload.manifest_required,
        )
        for row in sorted_rows
    ]
    manifest_section = _manifest_section(manifest)
    provider_order = _provider_order_section(payload.run_metadata)
    summary = _summary_counts(evidence_dicts)

    execution_image_manifest_hash = (
        sha256_canonical_json(manifest_section) if manifest_section is not None else None
    )
    result_evidence_hash = sha256_canonical_json(evidence_dicts)

    body_without_top_hash = {
        "schema_version": TRACEABILITY_MANIFEST_SCHEMA_VERSION,
        "job_id": payload.job_id,
        "inventory_id": payload.inventory_id,
        "aisle_id": payload.aisle_id,
        "run_id": payload.run_id,
        "provider": payload.provider,
        "model_name": payload.model_name,
        "created_at": payload.created_at.isoformat(),
        "execution_image_manifest": manifest_section,
        "provider_image_manifest_order": provider_order,
        "result_evidence": evidence_dicts,
        "summary": summary,
        "integrity": {
            "source": "structural_result_evidence",
            "execution_image_manifest_hash": execution_image_manifest_hash,
            "result_evidence_hash": result_evidence_hash,
            "artifact_hash_algorithm": "sha256",
        },
    }
    traceability_manifest_hash = sha256_canonical_json(body_without_top_hash)
    body_without_top_hash["integrity"]["traceability_manifest_hash"] = traceability_manifest_hash
    return body_without_top_hash


def traceability_manifest_is_json_safe(obj: Any) -> bool:
    """Return True when value is JSON-serializable without runtime objects."""
    forbidden = (bytes, bytearray)
    try:
        import numpy as np

        forbidden = forbidden + (np.ndarray,)
    except ImportError:
        pass
    try:
        from PIL import Image

        forbidden = forbidden + (Image.Image,)
    except ImportError:
        pass

    if isinstance(obj, forbidden):
        return False
    if isinstance(obj, dict):
        return all(
            isinstance(k, str) and traceability_manifest_is_json_safe(v) for k, v in obj.items()
        )
    if isinstance(obj, (list, tuple)):
        return all(traceability_manifest_is_json_safe(v) for v in obj)
    return obj is None or isinstance(obj, (str, int, float, bool))
