"""Ports for physical aisle locations and positioning labels."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

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
