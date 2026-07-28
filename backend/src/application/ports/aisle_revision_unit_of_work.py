"""Unit of Work for atomic aisle revision apply (Phase 8 corrections).

Every write of an apply (result versions, position versions, exclusions, the new finalization and
the revision row itself) must land in a single transaction so a mid-flight failure can never
publish a partial correction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.application.ports.aisle_revision_repository import AisleRevisionRepository
from src.application.ports.authoritative_aisle_finalization_repository import (
    AuthoritativeAisleFinalizationRepository,
)
from src.application.ports.authoritative_local_code_scan_repository import (
    AuthoritativeLocalCodeScanRepository,
)
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    PositionRepository,
)


@dataclass
class AisleRevisionRepositories:
    revision_repo: AisleRevisionRepository
    authoritative_repo: AuthoritativeLocalCodeScanRepository
    position_repo: PositionRepository
    finalization_repo: AuthoritativeAisleFinalizationRepository
    aisle_repo: AisleRepository
    inventory_repo: InventoryRepository


class AisleRevisionUnitOfWork(Protocol):
    repositories: AisleRevisionRepositories
    timing_ms: dict[str, float]

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def __enter__(self) -> AisleRevisionUnitOfWork: ...

    def __exit__(self, exc_type, exc, tb) -> None: ...
