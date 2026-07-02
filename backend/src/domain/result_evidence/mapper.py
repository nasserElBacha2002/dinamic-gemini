"""Map hybrid report entities to structural result evidence records (Phase 4.6)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from src.domain.execution_image_manifest import (
    ExecutionImageManifest,
    ExecutionImageManifestError,
    ExecutionImageRole,
    composition_has_execution_image_manifest,
    require_manifest_from_composition,
)
from src.domain.result_evidence.entities import (
    RESULT_EVIDENCE_KIND_ENTITY_TRACEABILITY,
    ResultEvidenceRecord,
    ResultEvidenceRole,
)
from src.domain.traceability import TraceabilityStatus, normalize_traceability_status


@dataclass(frozen=True)
class ResultEvidenceMapContext:
    job_id: str
    inventory_id: str
    aisle_id: str
    now: datetime
    position_id: str | None = None
    provider: str | None = None
    model_name: str | None = None
    prompt_composition: dict[str, Any] | None = None
    schema_version: str | None = None
    manifest_required: bool = True


def _load_manifest(composition: dict[str, Any] | None) -> ExecutionImageManifest | None:
    if not composition_has_execution_image_manifest(composition):
        return None
    try:
        return require_manifest_from_composition(composition)
    except ExecutionImageManifestError:
        return None


def _manifest_entry_for_source(
    manifest: ExecutionImageManifest | None,
    source_image_id: str | None,
) -> tuple[str | None, ResultEvidenceRole | None]:
    if manifest is None or not source_image_id:
        return None, None
    key = source_image_id.strip()
    for entry in manifest.ordered_entries():
        if entry.source_image_id == key:
            if entry.role == ExecutionImageRole.REFERENCE_IMAGE:
                return entry.source_asset_id, ResultEvidenceRole.REFERENCE_IMAGE
            return entry.source_asset_id, ResultEvidenceRole.PRIMARY_EVIDENCE
    return None, None


def _manifest_entry_for_mid(
    manifest: ExecutionImageManifest | None,
    manifest_entry_id: str | None,
) -> tuple[str | None, str | None, ResultEvidenceRole | None]:
    if manifest is None or not manifest_entry_id:
        return None, None, None
    entry = manifest.entry_by_manifest_id().get(manifest_entry_id.strip())
    if entry is None:
        return None, None, None
    role = (
        ResultEvidenceRole.REFERENCE_IMAGE
        if entry.role == ExecutionImageRole.REFERENCE_IMAGE
        else ResultEvidenceRole.PRIMARY_EVIDENCE
    )
    return entry.source_image_id, entry.source_asset_id, role


def _resolve_role(
    entity: dict[str, Any],
    manifest: ExecutionImageManifest | None,
) -> ResultEvidenceRole | None:
    status = normalize_traceability_status(entity.get("traceability_status"))
    resolved_mid = entity.get("resolved_manifest_entry_id")
    raw_mid = entity.get("manifest_entry_id")
    sid = entity.get("source_image_id")

    if status == TraceabilityStatus.INVALID.value:
        mid = resolved_mid or raw_mid
        if isinstance(mid, str) and mid.strip().upper().startswith("REF_"):
            return ResultEvidenceRole.REFERENCE_IMAGE
        _, _, role = _manifest_entry_for_mid(manifest, mid if isinstance(mid, str) else None)
        if role == ResultEvidenceRole.REFERENCE_IMAGE:
            return ResultEvidenceRole.REFERENCE_IMAGE
        raw_legacy = entity.get("raw_source_image_id")
        if isinstance(raw_legacy, str) and raw_legacy.strip():
            _, legacy_role = _manifest_entry_for_source(manifest, raw_legacy.strip())
            if legacy_role == ResultEvidenceRole.REFERENCE_IMAGE:
                return ResultEvidenceRole.REFERENCE_IMAGE
        return ResultEvidenceRole.UNKNOWN

    if status == TraceabilityStatus.VALID.value:
        _, _, role = _manifest_entry_for_mid(
            manifest, resolved_mid if isinstance(resolved_mid, str) else None
        )
        if role is not None:
            return role
        _, role = _manifest_entry_for_source(manifest, sid if isinstance(sid, str) else None)
        if role is not None:
            return role
        return ResultEvidenceRole.PRIMARY_EVIDENCE

    return ResultEvidenceRole.UNKNOWN


def compute_structural_has_valid_evidence(
    *,
    traceability_status: str | None,
    source_image_id: str | None,
    role: ResultEvidenceRole | None,
    manifest: ExecutionImageManifest | None,
    manifest_required: bool = True,
) -> bool:
    """Fail-closed display eligibility for structural evidence rows."""
    status = normalize_traceability_status(traceability_status)
    sid = (source_image_id or "").strip() if source_image_id else ""
    if status != TraceabilityStatus.VALID.value or not sid:
        return False
    if role != ResultEvidenceRole.PRIMARY_EVIDENCE:
        return False
    if manifest_required and manifest is None:
        return False
    if manifest is not None:
        for entry in manifest.ordered_entries():
            if entry.source_image_id == sid:
                if entry.role != ExecutionImageRole.PRIMARY_EVIDENCE:
                    return False
                break
        else:
            return False
    elif manifest_required:
        return False
    return True


def map_entity_to_result_evidence(
    entity: dict[str, Any],
    ctx: ResultEvidenceMapContext,
) -> ResultEvidenceRecord:
    """Map one hybrid report entity dict to a structural evidence record."""
    manifest = _load_manifest(ctx.prompt_composition)
    manifest_version = None
    if manifest is not None:
        manifest_version = getattr(manifest, "version", None)

    status = normalize_traceability_status(entity.get("traceability_status"))
    raw_mid = entity.get("manifest_entry_id")
    raw_sid = entity.get("raw_source_image_id")
    resolved_mid = entity.get("resolved_manifest_entry_id")
    sid = entity.get("source_image_id")

    role = _resolve_role(entity, manifest)

    detection_outcome = (
        str(entity.get("detection_outcome")).strip()
        if entity.get("detection_outcome") is not None
        else ""
    )
    source_asset_id: str | None = None
    if detection_outcome == "no_readable_label":
        primary = manifest.primary_entries() if manifest is not None else ()
        if primary:
            source_asset_id = primary[0].source_asset_id
            if not sid:
                sid = primary[0].source_image_id
    elif status == TraceabilityStatus.VALID.value and sid:
        source_asset_id, _ = _manifest_entry_for_source(manifest, str(sid))
    elif role == ResultEvidenceRole.REFERENCE_IMAGE:
        _, ref_asset, _ = _manifest_entry_for_mid(
            manifest,
            str(resolved_mid or raw_mid) if (resolved_mid or raw_mid) else None,
        )
        source_asset_id = ref_asset

    has_valid = compute_structural_has_valid_evidence(
        traceability_status=status,
        source_image_id=str(sid) if sid else None,
        role=role,
        manifest=manifest,
        manifest_required=ctx.manifest_required,
    )

    stable_sid = str(sid).strip() if sid and str(sid).strip() else None
    if status != TraceabilityStatus.VALID.value and detection_outcome != "no_readable_label":
        stable_sid = None

    return ResultEvidenceRecord(
        id=str(uuid4()),
        job_id=ctx.job_id,
        inventory_id=ctx.inventory_id,
        aisle_id=ctx.aisle_id,
        position_id=ctx.position_id,
        entity_uid=(
            str(entity.get("entity_uid")).strip()
            if entity.get("entity_uid") is not None
            else None
        ),
        model_entity_id=(
            str(entity.get("model_entity_id")).strip()
            if entity.get("model_entity_id") is not None
            else None
        ),
        raw_manifest_entry_id=str(raw_mid).strip() if raw_mid else None,
        manifest_entry_id=str(raw_mid).strip() if raw_mid else None,  # mirrors raw_manifest_entry_id
        raw_source_image_id=str(raw_sid).strip() if raw_sid else None,
        resolved_manifest_entry_id=str(resolved_mid).strip() if resolved_mid else None,
        source_image_id=stable_sid,
        source_asset_id=source_asset_id,
        traceability_status=status,
        traceability_warning=(
            str(entity.get("traceability_warning")).strip()
            if entity.get("traceability_warning")
            else None
        ),
        role=role,
        provider=ctx.provider,
        model_name=ctx.model_name,
        schema_version=ctx.schema_version,
        manifest_version=manifest_version if isinstance(manifest_version, int) else None,
        has_valid_evidence=has_valid,
        evidence_kind=RESULT_EVIDENCE_KIND_ENTITY_TRACEABILITY,
        created_at=ctx.now,
        updated_at=ctx.now,
    )


def map_report_entities_to_result_evidence(
    entities: list[dict[str, Any]],
    *,
    base_ctx: ResultEvidenceMapContext,
    position_id_by_entity_uid: dict[str, str] | None = None,
) -> list[ResultEvidenceRecord]:
    """Map all report entities; optionally attach persisted position IDs."""
    uid_map = position_id_by_entity_uid or {}
    records: list[ResultEvidenceRecord] = []
    for entity in entities:
        uid = entity.get("entity_uid")
        pos_id = uid_map.get(str(uid)) if uid is not None else None
        ctx = ResultEvidenceMapContext(
            job_id=base_ctx.job_id,
            inventory_id=base_ctx.inventory_id,
            aisle_id=base_ctx.aisle_id,
            now=base_ctx.now,
            position_id=pos_id,
            provider=base_ctx.provider,
            model_name=base_ctx.model_name,
            prompt_composition=base_ctx.prompt_composition,
            schema_version=base_ctx.schema_version,
            manifest_required=base_ctx.manifest_required,
        )
        records.append(map_entity_to_result_evidence(entity, ctx))
    return records
