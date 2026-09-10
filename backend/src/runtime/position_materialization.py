"""Runtime composition for the shared position materialization service."""

from __future__ import annotations

from typing import Protocol

from src.application.services.position_materialization import MaterializePositionService


class PositionMaterializationContainer(Protocol):
    def get_position_materialization_service(self) -> MaterializePositionService: ...


def build_position_materialization_service(
    *, container: PositionMaterializationContainer
) -> MaterializePositionService:
    """Compatibility seam delegating ownership to the application container."""
    return container.get_position_materialization_service()


__all__ = [
    "PositionMaterializationContainer",
    "build_position_materialization_service",
]
