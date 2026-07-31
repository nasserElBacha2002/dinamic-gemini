"""Port for client-scoped positioning labels."""

from __future__ import annotations

from typing import Protocol

from src.domain.client_position_label.entities import (
    ClientPositionLabel,
    ClientPositionLabelArtifact,
)


class ClientPositionLabelRepository(Protocol):
    def get_by_id(self, label_id: str) -> ClientPositionLabel | None: ...

    def get_by_public_identifier(self, public_identifier: str) -> ClientPositionLabel | None: ...

    def get_by_idempotency_key(
        self, client_id: str, idempotency_key: str
    ) -> ClientPositionLabel | None: ...

    def get_active_by_normalized_name(
        self, client_id: str, normalized_name: str
    ) -> ClientPositionLabel | None: ...

    def list_by_client(
        self,
        client_id: str,
        *,
        status: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ClientPositionLabel]: ...

    def count_by_client(
        self,
        client_id: str,
        *,
        status: str | None = None,
        search: str | None = None,
    ) -> int: ...

    def save(self, label: ClientPositionLabel) -> ClientPositionLabel: ...

    def get_artifact(
        self,
        label_id: str,
        *,
        format: str,
        preset: str,
        template_version: int,
        marker_version: int,
    ) -> ClientPositionLabelArtifact | None: ...

    def save_artifact(self, artifact: ClientPositionLabelArtifact) -> ClientPositionLabelArtifact: ...
