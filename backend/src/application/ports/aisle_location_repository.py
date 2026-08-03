"""Ports for physical aisle locations and positioning labels."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from src.domain.aisle_location.artifact_entities import AisleLocationLabelArtifact
from src.domain.aisle_location.entities import AisleLocation
from src.domain.aisle_location.label_entities import AisleLocationLabel


class AisleLocationRepository(Protocol):
    def save(self, location: AisleLocation) -> None: ...

    def get_by_id(self, location_id: str) -> AisleLocation | None: ...

    def get_active_by_normalized_code(
        self,
        *,
        client_id: str,
        aisle_id: str,
        normalized_code: str,
    ) -> AisleLocation | None: ...

    def get_by_public_identifier(self, public_identifier: str) -> AisleLocation | None: ...

    def list_by_aisle(
        self,
        aisle_id: str,
        *,
        status: str | None = None,
        search: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AisleLocation]: ...

    def count_by_aisle(
        self,
        aisle_id: str,
        *,
        status: str | None = None,
        search: str | None = None,
    ) -> int: ...


class AisleLocationLabelRepository(Protocol):
    def save(self, label: AisleLocationLabel) -> None: ...

    def get_by_id(self, label_id: str) -> AisleLocationLabel | None: ...

    def get_by_public_identifier(self, public_identifier: str) -> AisleLocationLabel | None: ...

    def get_by_client_idempotency_key(
        self, client_id: str, idempotency_key: str
    ) -> AisleLocationLabel | None: ...

    def list_by_location(
        self,
        location_id: str,
        *,
        status: str | None = None,
    ) -> Sequence[AisleLocationLabel]: ...

    def list_active_labels_by_location_ids(
        self, location_ids: Sequence[str]
    ) -> dict[str, AisleLocationLabel]: ...


class AisleLocationLabelArtifactRepository(Protocol):
    def save(self, artifact: AisleLocationLabelArtifact) -> None: ...

    def get_by_id(self, artifact_id: str) -> AisleLocationLabelArtifact | None: ...

    def get_by_identity(
        self,
        *,
        label_id: str,
        format: str,
        preset: str,
        template_version: int,
        marker_version: int,
    ) -> AisleLocationLabelArtifact | None: ...

    def list_by_label(self, label_id: str) -> Sequence[AisleLocationLabelArtifact]: ...

    def reserve_or_get(
        self,
        *,
        artifact: AisleLocationLabelArtifact,
    ) -> tuple[AisleLocationLabelArtifact, bool]:
        """Atomically insert PENDING artifact or return existing identity.

        Returns ``(artifact, created)`` where ``created`` is True if this caller owns the
        fresh reservation.
        """
        ...

    def claim_for_render(
        self,
        *,
        artifact_id: str,
        render_owner: str,
        now: datetime,
    ) -> AisleLocationLabelArtifact | None:
        """CAS PENDING/FAILED → RENDERING for ``render_owner``. None if not claimed."""
        ...


class AisleLocationLabelReplaceUnitOfWork(Protocol):
    """Single SQL transaction: lock old label, insert replacement, mark REPLACED."""

    def replace_atomically(
        self,
        *,
        old_label_id: str,
        new_label: AisleLocationLabel,
        now: datetime,
        request_hash: str | None,
        idempotency_key: str | None,
    ) -> AisleLocationLabel: ...
