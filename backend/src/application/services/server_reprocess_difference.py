"""Classify server reprocess proposal differences by asset_id identity only."""

from __future__ import annotations

from src.domain.server_reprocess.entities import (
    RemoteProposalInput,
    ServerReprocessDifferenceType,
    ServerReprocessRunAsset,
)


def _norm_code(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _norm_qty(value: float | None) -> float | None:
    if value is None:
        return None
    return float(value)


def classify_server_reprocess_difference(
    *,
    snapshot_asset: ServerReprocessRunAsset,
    remote: RemoteProposalInput,
) -> ServerReprocessDifferenceType:
    """Informational classification only — never mutates authority."""

    if remote.global_batch_unmapped or not remote.comparable:
        if remote.global_batch_unmapped:
            return ServerReprocessDifferenceType.NOT_COMPARABLE_GLOBAL_BATCH
        return ServerReprocessDifferenceType.NOT_COMPARABLE

    if remote.ambiguous:
        return ServerReprocessDifferenceType.REMOTE_AMBIGUOUS

    prev_resolved = bool(snapshot_asset.previous_resolved)
    remote_resolved = bool(remote.resolved) and _norm_code(remote.internal_code) is not None

    if not prev_resolved and not snapshot_asset.previous_result_id:
        if remote_resolved:
            return ServerReprocessDifferenceType.NO_PREVIOUS_RESULT
        return ServerReprocessDifferenceType.NO_PREVIOUS_RESULT

    if not prev_resolved and remote_resolved:
        return ServerReprocessDifferenceType.PREVIOUS_UNRESOLVED_REMOTE_RESOLVED

    if prev_resolved and not remote_resolved:
        return ServerReprocessDifferenceType.PREVIOUS_RESOLVED_REMOTE_UNRESOLVED

    prev_code = _norm_code(snapshot_asset.previous_internal_code)
    remote_code = _norm_code(remote.internal_code)
    prev_qty = _norm_qty(snapshot_asset.previous_quantity)
    remote_qty = _norm_qty(remote.quantity)

    code_changed = prev_code != remote_code
    qty_changed = prev_qty != remote_qty

    if code_changed and qty_changed:
        return ServerReprocessDifferenceType.CODE_AND_QUANTITY_CHANGED
    if code_changed:
        return ServerReprocessDifferenceType.CODE_CHANGED
    if qty_changed:
        return ServerReprocessDifferenceType.QUANTITY_CHANGED
    return ServerReprocessDifferenceType.SAME_RESULT
