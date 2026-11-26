"""Resolve inventory + aisle code to a stable MediaMTX channel path."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.ports.repositories import AisleRepository, InventoryRepository
from src.domain.live_stream.channel_identity import (
    canonical_aisle_code_for_channel,
    channel_slug,
    mediamtx_path,
    normalize_inventory_id,
)


@dataclass(frozen=True)
class ResolvedLiveChannel:
    inventory_id: str
    aisle_code_input: str
    canonical_aisle_code: str
    channel_slug: str
    mediamtx_path: str
    aisle_id: str | None


class LiveStreamAisleChannelResolver:
    def __init__(
        self,
        *,
        aisle_repo: AisleRepository | None,
        inventory_repo: InventoryRepository | None = None,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._inventory_repo = inventory_repo

    def resolve(self, *, inventory_id: str, aisle_code: str) -> ResolvedLiveChannel:
        inv = normalize_inventory_id(inventory_id)
        code_stripped = (aisle_code or "").strip()
        canonical = canonical_aisle_code_for_channel(code_stripped)
        slug = channel_slug(inv, code_stripped)
        inventory_name = ""
        if self._inventory_repo is not None:
            inventory = self._inventory_repo.get_by_id(inv)
            if inventory is not None:
                inventory_name = inventory.name
        path = mediamtx_path(inv, code_stripped, inventory_name=inventory_name)
        aisle_id: str | None = None
        if self._aisle_repo is not None:
            existing = self._aisle_repo.get_by_inventory_and_code(inv, code_stripped)
            if existing is not None:
                aisle_id = existing.id
        return ResolvedLiveChannel(
            inventory_id=inv,
            aisle_code_input=code_stripped,
            canonical_aisle_code=canonical,
            channel_slug=slug,
            mediamtx_path=path,
            aisle_id=aisle_id,
        )
