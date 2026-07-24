"""Typed current-position snapshots for server reprocess (no JSON key guessing)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from src.domain.positions.entities import Position
from src.domain.server_reprocess.entities import CurrentPositionSnapshot


class _PositionRepo(Protocol):
    def list_by_aisle(self, aisle_id: str) -> Sequence[Position]: ...


def _asset_id_from_position(position: Position) -> str | None:
    """Prefer explicit coverage linkage fields when present on summary contracts."""
    for blob in (position.corrected_summary_json, position.detected_summary_json):
        if not isinstance(blob, dict):
            continue
        # Canonical keys only — no alternate heuristics.
        for key in ("source_asset_id",):
            value = blob.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _code_qty_from_position(position: Position) -> tuple[str | None, float | None]:
    blob = position.corrected_summary_json or position.detected_summary_json
    if not isinstance(blob, dict):
        return None, None
    code_raw = blob.get("internal_code")
    qty_raw = blob.get("quantity")
    code = str(code_raw).strip() if code_raw is not None else None
    try:
        qty = float(qty_raw) if qty_raw is not None else None
    except (TypeError, ValueError):
        qty = None
    return (code or None), qty


def _active_result_id(position: Position) -> str | None:
    blob = position.corrected_summary_json or position.detected_summary_json
    if not isinstance(blob, dict):
        return None
    value = blob.get("authoritative_result_id") or blob.get("active_result_id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


class ServerReprocessPositionSnapshotQuery:
    def __init__(self, *, position_repo: _PositionRepo | None) -> None:
        self._position_repo = position_repo

    def list_for_aisle(self, aisle_id: str) -> list[CurrentPositionSnapshot]:
        if self._position_repo is None:
            return []
        out: list[CurrentPositionSnapshot] = []
        for position in self._position_repo.list_by_aisle(aisle_id):
            asset_id = _asset_id_from_position(position)
            if not asset_id:
                continue
            code, qty = _code_qty_from_position(position)
            status = getattr(position.status, "value", str(position.status))
            out.append(
                CurrentPositionSnapshot(
                    position_id=position.id,
                    asset_id=asset_id,
                    active_result_id=_active_result_id(position),
                    internal_code=code,
                    quantity=qty,
                    row_version=1,
                    needs_review=bool(position.needs_review),
                    status=str(status),
                )
            )
        return out

    def map_by_asset(self, aisle_id: str) -> dict[str, CurrentPositionSnapshot]:
        return {snap.asset_id: snap for snap in self.list_for_aisle(aisle_id)}
