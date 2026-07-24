"""Resolve aisle revision capabilities for a concrete inventory/aisle (Phase 8 corrections).

The route used to ignore the path parameters and answer from feature flags alone, which leaked
capability information for inventories and aisles the caller may not address. This use case
validates the scope first, then reports what is actually possible for that aisle.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.errors import InventoryNotFoundError
from src.application.ports.aisle_revision_repository import AisleRevisionRepository
from src.application.ports.authoritative_aisle_finalization_repository import (
    AuthoritativeAisleFinalizationRepository,
)
from src.application.ports.repositories import AisleRepository, InventoryRepository
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.domain.authoritative_aisle_finalization.entities import (
    AuthoritativeFinalizationStatus,
)


@dataclass(frozen=True)
class AisleRevisionCapabilities:
    aisle_revisions_enabled: bool
    aisle_rollback_enabled: bool
    aisle_history_enabled: bool


class GetAisleRevisionCapabilities:
    def __init__(
        self,
        *,
        revisions_enabled: bool,
        rollback_enabled: bool,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        finalization_repo: AuthoritativeAisleFinalizationRepository,
        revision_repo: AisleRevisionRepository,
    ) -> None:
        self._revisions_enabled = revisions_enabled
        self._rollback_enabled = rollback_enabled
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._finalization_repo = finalization_repo
        self._revision_repo = revision_repo

    def execute(self, *, inventory_id: str, aisle_id: str) -> AisleRevisionCapabilities:
        if self._inventory_repo.get_by_id(inventory_id) is None:
            raise InventoryNotFoundError(f"Inventory not found: {inventory_id}")
        require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            detail_style="strict",
        )
        if not self._revisions_enabled:
            return AisleRevisionCapabilities(False, False, False)

        current = self._finalization_repo.get_current_for_aisle(aisle_id)
        finalized = current is not None and current.status == (
            AuthoritativeFinalizationStatus.COMPLETED_BY_LOCAL_AUTHORITY.value
        )
        # Rollback needs a superseded finalization to travel back to, and would be rejected
        # while another revision is still open on the aisle.
        has_history = self._finalization_repo.max_version_for_aisle(aisle_id) >= 2
        open_revision = self._revision_repo.get_open_revision_for_aisle(aisle_id)
        return AisleRevisionCapabilities(
            aisle_revisions_enabled=finalized,
            aisle_rollback_enabled=(
                self._rollback_enabled and finalized and has_history and open_revision is None
            ),
            aisle_history_enabled=True,
        )
