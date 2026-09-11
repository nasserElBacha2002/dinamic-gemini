"""In-memory trusted materialized identity reader for tests."""

from __future__ import annotations

from collections.abc import Sequence

from src.application.ports.materialized_position_identity_reader import (
    TrustedMaterializedPositionIdentity,
)
from src.infrastructure.persistence.memory_position_materialization_unit_of_work import (
    MemoryPositionMaterializationUnitOfWork,
)


class MemoryMaterializedPositionIdentityReader:
    def __init__(self, unit_of_work: MemoryPositionMaterializationUnitOfWork) -> None:
        self._unit_of_work = unit_of_work

    def read_by_detection_ids(
        self,
        detection_ids: Sequence[str],
        *,
        client_id: str,
        inventory_id: str,
        aisle_id: str,
    ) -> dict[str, TrustedMaterializedPositionIdentity]:
        return self._unit_of_work.read_materialized_identities(
            tuple(detection_ids),
            client_id=client_id,
            inventory_id=inventory_id,
            aisle_id=aisle_id,
        )
