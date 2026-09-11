"""In-memory PositionFlexibleCapabilityReader for unit tests."""

from __future__ import annotations

from src.application.ports.position_flexible_capability_reader import (
    PositionFlexibleCapability,
    PositionFlexibleCapabilityMode,
    PositionFlexibleCapabilityReader,
)


class MemoryPositionFlexibleCapabilityReader:
    def __init__(self, rows: list[PositionFlexibleCapability] | None = None) -> None:
        self._rows = list(rows or [])

    def add(self, row: PositionFlexibleCapability) -> None:
        self._rows.append(row)

    def find_enabled(
        self,
        *,
        client_id: str,
        channel: str,
        client_supplier_id: str | None = None,
        profile_id: str | None = None,
    ) -> PositionFlexibleCapability | None:
        client = (client_id or "").strip()
        ch = (channel or "").strip().upper()
        supplier = (client_supplier_id or "").strip() or None
        profile = (profile_id or "").strip() or None
        matches = [
            row
            for row in self._rows
            if row.enabled
            and (row.client_id or "").strip() == client
            and (row.channel or "").strip().upper() == ch
            and ((row.client_supplier_id or "").strip() or None) == supplier
            and ((row.profile_id or "").strip() or None) == profile
        ]
        if matches:
            return matches[0]
        # Fall back to client+channel with null supplier/profile.
        if supplier is not None or profile is not None:
            return self.find_enabled(
                client_id=client,
                channel=ch,
                client_supplier_id=None,
                profile_id=None,
            )
        return None


def capability_enforced(
    reader: PositionFlexibleCapabilityReader | None,
    *,
    client_id: str,
    channel: str,
    client_supplier_id: str | None = None,
    profile_id: str | None = None,
) -> bool:
    """True when an enabled ENFORCED capability exists for the scope."""
    if reader is None:
        return False
    row = reader.find_enabled(
        client_id=client_id,
        channel=channel,
        client_supplier_id=client_supplier_id,
        profile_id=profile_id,
    )
    return row is not None and row.mode is PositionFlexibleCapabilityMode.ENFORCED


__all__ = [
    "MemoryPositionFlexibleCapabilityReader",
    "capability_enforced",
]
