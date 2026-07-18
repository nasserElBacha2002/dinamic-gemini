"""Central query for hierarchical aisle identification configuration (Phase 1).

Single source of truth for configured / effective / source fields on API responses.
Does not handle request overrides (those apply only at job creation).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from src.application.ports.repositories import (
    AisleRepository,
    ClientRepository,
    InventoryRepository,
)
from src.domain.aisle.entities import Aisle
from src.domain.aisle_identification.modes import (
    AisleIdentificationMode,
    AisleIdentificationModeSource,
)
from src.domain.aisle_identification.resolver import resolve_aisle_identification_mode
from src.domain.client.entities import Client
from src.domain.inventory.entities import Inventory

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IdentificationModeConfiguration:
    configured_mode: AisleIdentificationMode | None
    effective_mode: AisleIdentificationMode
    source: AisleIdentificationModeSource


class AisleIdentificationConfigurationQuery:
    def __init__(
        self,
        aisle_repo: AisleRepository,
        inventory_repo: InventoryRepository,
        client_repo: ClientRepository,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._inventory_repo = inventory_repo
        self._client_repo = client_repo

    def for_aisle(
        self,
        aisle: Aisle,
        *,
        inventory: Inventory | None = None,
        client: Client | None = None,
    ) -> IdentificationModeConfiguration:
        inv = inventory if inventory is not None else self._inventory_repo.get_by_id(aisle.inventory_id)
        cl = client if client is not None else self._client_for_inventory(inv)
        resolution = resolve_aisle_identification_mode(
            aisle_mode=aisle.identification_mode,
            inventory_mode=inv.identification_mode if inv else None,
            client_mode=cl.default_identification_mode if cl else None,
        )
        return IdentificationModeConfiguration(
            configured_mode=aisle.identification_mode,
            effective_mode=resolution.effective_mode,
            source=resolution.source,
        )

    def for_aisles(
        self,
        aisles: Sequence[Aisle],
        *,
        inventory: Inventory | None = None,
        client: Client | None = None,
    ) -> dict[str, IdentificationModeConfiguration]:
        """Batch variant of :meth:`for_aisle` — one inventory/client fetch, not N.

        Assumes ``aisles`` share a single inventory (the common ``list_aisles``-route case).
        ``inventory``/``client`` are resolved once from the first aisle's ``inventory_id`` when
        not provided. Any aisle whose ``inventory_id`` differs from the resolved inventory is
        handled defensively via a per-aisle fallback (correct but no longer O(1) for that one).
        """
        if not aisles:
            return {}
        inv = inventory
        if inv is None:
            inv = self._inventory_repo.get_by_id(aisles[0].inventory_id)
        cl = client if client is not None else self._client_for_inventory(inv)

        out: dict[str, IdentificationModeConfiguration] = {}
        for aisle in aisles:
            if inv is not None and aisle.inventory_id != inv.id:
                logger.warning(
                    "aisle_identification_config.for_aisles_mixed_inventory aisle_id=%s "
                    "expected_inventory_id=%s actual_inventory_id=%s",
                    aisle.id,
                    inv.id,
                    aisle.inventory_id,
                )
                out[aisle.id] = self.for_aisle(aisle)
                continue
            out[aisle.id] = self.for_aisle(aisle, inventory=inv, client=cl)
        return out

    def for_aisle_id(self, aisle_id: str) -> IdentificationModeConfiguration | None:
        aisle = self._aisle_repo.get_by_id(aisle_id)
        if aisle is None:
            return None
        return self.for_aisle(aisle)

    def for_inventory(self, inventory: Inventory) -> IdentificationModeConfiguration:
        client = self._client_for_inventory(inventory)
        resolution = resolve_aisle_identification_mode(
            inventory_mode=inventory.identification_mode,
            client_mode=client.default_identification_mode if client else None,
        )
        return IdentificationModeConfiguration(
            configured_mode=inventory.identification_mode,
            effective_mode=resolution.effective_mode,
            source=resolution.source,
        )

    def for_client(self, client: Client) -> IdentificationModeConfiguration:
        resolution = resolve_aisle_identification_mode(
            client_mode=client.default_identification_mode
        )
        return IdentificationModeConfiguration(
            configured_mode=client.default_identification_mode,
            effective_mode=resolution.effective_mode,
            source=resolution.source,
        )

    def _client_for_inventory(self, inventory: Inventory | None) -> Client | None:
        if inventory is None or not inventory.client_id:
            return None
        return self._client_repo.get_by_id(inventory.client_id)
