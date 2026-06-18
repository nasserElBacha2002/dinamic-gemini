"""Phase 4.8 — fail-closed API displayability rules for structural result_evidence."""

from __future__ import annotations

from src.domain.result_evidence.entities import ResultEvidenceRecord, ResultEvidenceRole
from src.domain.traceability import TraceabilityStatus, normalize_traceability_status

STRUCTURAL_EVIDENCE_UNAVAILABLE_WARNING = (
    "Structural evidence is unavailable for this result."
)
EVIDENCE_IMAGE_URL_UNAVAILABLE_WARNING = (
    "Evidence image URL could not be generated."
)


def resolve_source_asset_id(
    record: ResultEvidenceRecord,
    *,
    assets_by_id: dict[str, object],
) -> str | None:
    """Resolve a display asset id from persisted row or aisle assets."""
    persisted = (record.source_asset_id or "").strip()
    if persisted:
        return persisted
    sid = (record.source_image_id or "").strip()
    if sid and sid in assets_by_id:
        return sid
    return None


def compute_structural_api_displayable(
    record: ResultEvidenceRecord,
    *,
    resolved_source_asset_id: str | None,
) -> bool:
    """Displayable only when structural row is VALID primary evidence with resolvable asset."""
    if not record.has_valid_evidence:
        return False
    if record.role != ResultEvidenceRole.PRIMARY_EVIDENCE:
        return False
    status = normalize_traceability_status(record.traceability_status)
    if status != TraceabilityStatus.VALID.value:
        return False
    sid = (record.source_image_id or "").strip()
    if not sid:
        return False
    asset_id = (resolved_source_asset_id or "").strip()
    return bool(asset_id)


def api_traceability_status_for_row(
    record: ResultEvidenceRecord | None,
    *,
    displayable: bool,
    image_access_status: str | None,
) -> str:
    """Map structural row to API traceability status string."""
    if record is None:
        return "legacy_unavailable"
    status = normalize_traceability_status(record.traceability_status)
    if displayable and image_access_status == "url_unavailable":
        return status or TraceabilityStatus.VALID.value
    if status in {
        TraceabilityStatus.VALID.value,
        TraceabilityStatus.INVALID.value,
        TraceabilityStatus.MISSING.value,
        TraceabilityStatus.UNVALIDATED.value,
    }:
        return status
    return "legacy_unavailable"
