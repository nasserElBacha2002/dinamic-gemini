"""Trusted read boundary for detection-to-materialized-location identity."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TrustedMaterializedPositionIdentity:
    detection_id: str
    request_id: str
    aisle_location_id: str


class MaterializedPositionIdentityReader(Protocol):
    def read_by_detection_ids(
        self,
        detection_ids: Sequence[str],
        *,
        client_id: str,
        inventory_id: str,
        aisle_id: str,
    ) -> dict[str, TrustedMaterializedPositionIdentity]: ...
