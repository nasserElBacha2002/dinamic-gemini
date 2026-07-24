"""Typed reader for historical aisle finalization snapshots (Phase 8 rollback).

Rollback needs what a *previous* finalization published. Reading it through this service keeps
callers on public repository contracts instead of reaching into another use case's private
collaborators, and returns explicit DTOs instead of loosely typed rows.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.ports.authoritative_aisle_finalization_repository import (
    AuthoritativeAisleFinalizationRepository,
)
from src.application.ports.authoritative_local_code_scan_repository import (
    AuthoritativeLocalCodeScanRepository,
)
from src.application.ports.repositories import PositionRepository
from src.domain.authoritative_aisle_finalization.entities import (
    AuthoritativeFinalizationItemStatus,
)
from src.domain.positions.entities import PositionStatus


class HistoricalFinalizationScopeError(Exception):
    """The requested finalization does not belong to the requested aisle."""

    error_code = "AISLE_REVISION_INVALID_TARGET"


@dataclass(frozen=True)
class HistoricalFinalizationEntry:
    """What one asset looked like in a historical finalization."""

    asset_id: str
    excluded: bool
    authoritative_result_id: str | None
    position_id: str | None
    internal_code: str | None
    quantity: int | None
    #: False when the historical position row is gone, soft-deleted or moved to another aisle.
    position_active: bool


@dataclass(frozen=True)
class HistoricalFinalizationSnapshot:
    finalization_id: str
    aisle_id: str
    entries: tuple[HistoricalFinalizationEntry, ...]


class HistoricalFinalizationSnapshotReader:
    def __init__(
        self,
        *,
        finalization_repo: AuthoritativeAisleFinalizationRepository,
        authoritative_repo: AuthoritativeLocalCodeScanRepository,
        position_repo: PositionRepository | None = None,
    ) -> None:
        self._finalization_repo = finalization_repo
        self._authoritative_repo = authoritative_repo
        self._position_repo = position_repo

    def read(self, *, finalization_id: str, aisle_id: str) -> HistoricalFinalizationSnapshot:
        finalization = self._finalization_repo.get_by_id(finalization_id)
        if finalization is None or finalization.aisle_id != aisle_id:
            raise HistoricalFinalizationScopeError(
                f"Finalization {finalization_id} does not belong to aisle {aisle_id}"
            )

        entries: list[HistoricalFinalizationEntry] = []
        for item in self._finalization_repo.list_items(finalization_id):
            excluded = item.item_status == AuthoritativeFinalizationItemStatus.EXCLUDED.value
            code: str | None = None
            quantity: int | None = None
            if not excluded and item.authoritative_result_id:
                result = self._authoritative_repo.get_by_id(item.authoritative_result_id)
                if result is not None:
                    code = result.internal_code
                    quantity = int(result.quantity) if result.quantity is not None else None
            entries.append(
                HistoricalFinalizationEntry(
                    asset_id=item.asset_id,
                    excluded=excluded,
                    authoritative_result_id=item.authoritative_result_id,
                    position_id=item.position_id,
                    internal_code=code,
                    quantity=quantity,
                    position_active=self._position_active(item.position_id, aisle_id),
                )
            )
        return HistoricalFinalizationSnapshot(
            finalization_id=finalization_id,
            aisle_id=aisle_id,
            entries=tuple(entries),
        )

    def _position_active(self, position_id: str | None, aisle_id: str) -> bool:
        if not position_id or self._position_repo is None:
            return False
        position = self._position_repo.get_by_id(position_id)
        if position is None or position.aisle_id != aisle_id:
            return False
        return position.status != PositionStatus.DELETED
