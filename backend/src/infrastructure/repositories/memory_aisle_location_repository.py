"""In-memory aisle location + positioning label repositories."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from src.application.errors import IdempotencyKeyReusedError
from src.application.ports.aisle_location_repository import (
    AisleLocationLabelRepository,
    AisleLocationRepository,
)
from src.domain.aisle_location.artifact_entities import (
    AisleLocationLabelArtifact,
    AisleLocationLabelArtifactStatus,
)
from src.domain.aisle_location.entities import AisleLocation, AisleLocationStatus
from src.domain.aisle_location.label_entities import (
    AisleLocationLabel,
    AisleLocationLabelStatus,
)


class MemoryAisleLocationRepository(AisleLocationRepository):
    def __init__(self) -> None:
        self._store: dict[str, AisleLocation] = {}

    def save(self, location: AisleLocation) -> None:
        self._store[location.id] = location

    def get_by_id(self, location_id: str) -> AisleLocation | None:
        return self._store.get(location_id)

    def get_by_public_identifier(self, public_identifier: str) -> AisleLocation | None:
        pub = (public_identifier or "").strip()
        if not pub:
            return None
        for loc in self._store.values():
            if loc.public_identifier == pub:
                return loc
        return None

    def get_active_by_normalized_code(
        self,
        *,
        client_id: str,
        aisle_id: str,
        normalized_code: str,
    ) -> AisleLocation | None:
        code = (normalized_code or "").strip().upper()
        for loc in self._store.values():
            if (
                loc.client_id == client_id
                and loc.aisle_id == aisle_id
                and loc.normalized_code == code
                and loc.status == AisleLocationStatus.ACTIVE
            ):
                return loc
        return None

    def list_by_aisle(
        self,
        aisle_id: str,
        *,
        status: str | None = None,
        search: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AisleLocation]:
        rows = [loc for loc in self._store.values() if loc.aisle_id == aisle_id]
        if status:
            rows = [loc for loc in rows if loc.status.value == status.upper()]
        if search:
            q = search.strip().lower()
            rows = [
                loc
                for loc in rows
                if q in loc.code.lower()
                or q in (loc.display_name or "").lower()
                or q in (loc.description or "").lower()
            ]
        rows.sort(key=lambda loc: (loc.normalized_code, loc.id))
        return rows[offset : offset + limit]

    def count_by_aisle(
        self,
        aisle_id: str,
        *,
        status: str | None = None,
        search: str | None = None,
    ) -> int:
        return len(
            self.list_by_aisle(
                aisle_id, status=status, search=search, limit=10_000_000, offset=0
            )
        )


class MemoryAisleLocationLabelRepository(AisleLocationLabelRepository):
    def __init__(self) -> None:
        self._store: dict[str, AisleLocationLabel] = {}

    def save(self, label: AisleLocationLabel) -> None:
        key = (label.idempotency_key or "").strip()
        if key:
            for existing in self._store.values():
                if existing.id == label.id:
                    continue
                if (
                    existing.client_id == label.client_id
                    and (existing.idempotency_key or "").strip() == key
                ):
                    raise IdempotencyKeyReusedError(
                        "IDEMPOTENCY_KEY_REUSED: key already registered"
                    )
        self._store[label.id] = label

    def get_by_id(self, label_id: str) -> AisleLocationLabel | None:
        return self._store.get(label_id)

    def get_by_public_identifier(self, public_identifier: str) -> AisleLocationLabel | None:
        pub = (public_identifier or "").strip()
        for label in self._store.values():
            if label.public_identifier == pub:
                return label
        return None

    def get_by_client_idempotency_key(
        self, client_id: str, idempotency_key: str
    ) -> AisleLocationLabel | None:
        cid = (client_id or "").strip()
        key = (idempotency_key or "").strip()
        if not cid or not key:
            return None
        for label in self._store.values():
            if label.client_id == cid and (label.idempotency_key or "").strip() == key:
                return label
        return None

    def list_by_location(
        self,
        location_id: str,
        *,
        status: str | None = None,
    ) -> Sequence[AisleLocationLabel]:
        rows = [lab for lab in self._store.values() if lab.location_id == location_id]
        if status:
            rows = [lab for lab in rows if lab.status.value == status.upper()]
        return sorted(rows, key=lambda lab: lab.generated_at, reverse=True)

    def list_active_labels_by_location_ids(
        self, location_ids: Sequence[str]
    ) -> dict[str, AisleLocationLabel]:
        wanted = {(lid or "").strip() for lid in location_ids if (lid or "").strip()}
        if not wanted:
            return {}
        result: dict[str, AisleLocationLabel] = {}
        for label in self._store.values():
            if label.location_id not in wanted:
                continue
            if label.status != AisleLocationLabelStatus.ACTIVE:
                continue
            current = result.get(label.location_id)
            if current is None or label.generated_at > current.generated_at:
                result[label.location_id] = label
        return result


class MemoryAisleLocationLabelArtifactRepository:
    def __init__(self) -> None:
        self._store: dict[str, AisleLocationLabelArtifact] = {}

    def save(self, artifact: AisleLocationLabelArtifact) -> None:
        existing = self.get_by_identity(
            label_id=artifact.label_id,
            format=artifact.format,
            preset=artifact.preset,
            template_version=artifact.template_version,
            marker_version=artifact.marker_version,
        )
        if existing is not None and existing.id != artifact.id:
            # Idempotent overwrite of same logical identity is allowed only same id.
            raise ValueError("artifact identity already exists")
        self._store[artifact.id] = artifact

    def get_by_id(self, artifact_id: str) -> AisleLocationLabelArtifact | None:
        return self._store.get(artifact_id)

    def get_by_identity(
        self,
        *,
        label_id: str,
        format: str,
        preset: str,
        template_version: int,
        marker_version: int,
    ) -> AisleLocationLabelArtifact | None:
        for art in self._store.values():
            if (
                art.label_id == label_id
                and art.format.upper() == format.upper()
                and art.preset == preset
                and int(art.template_version) == int(template_version)
                and int(art.marker_version) == int(marker_version)
            ):
                return art
        return None

    def list_by_label(self, label_id: str) -> Sequence[AisleLocationLabelArtifact]:
        rows = [a for a in self._store.values() if a.label_id == label_id]
        return sorted(rows, key=lambda a: a.created_at, reverse=True)

    def reserve_or_get(
        self,
        *,
        artifact: AisleLocationLabelArtifact,
    ) -> tuple[AisleLocationLabelArtifact, bool]:
        existing = self.get_by_identity(
            label_id=artifact.label_id,
            format=artifact.format,
            preset=artifact.preset,
            template_version=artifact.template_version,
            marker_version=artifact.marker_version,
        )
        if existing is not None:
            return existing, False
        self._store[artifact.id] = artifact
        return artifact, True

    def claim_for_render(
        self,
        *,
        artifact_id: str,
        render_owner: str,
        now: datetime,
    ) -> AisleLocationLabelArtifact | None:
        artifact = self._store.get(artifact_id)
        if artifact is None:
            return None
        if artifact.status not in (
            AisleLocationLabelArtifactStatus.PENDING,
            AisleLocationLabelArtifactStatus.FAILED,
        ):
            return None
        claimed = AisleLocationLabelArtifact(
            id=artifact.id,
            label_id=artifact.label_id,
            format=artifact.format,
            preset=artifact.preset,
            template_version=artifact.template_version,
            marker_version=artifact.marker_version,
            storage_provider=artifact.storage_provider,
            storage_bucket=artifact.storage_bucket,
            storage_key=artifact.storage_key,
            content_type=artifact.content_type,
            file_size_bytes=artifact.file_size_bytes,
            artifact_hash=artifact.artifact_hash,
            created_at=artifact.created_at,
            status=AisleLocationLabelArtifactStatus.RENDERING,
            failure_code=artifact.failure_code,
            failure_detail=artifact.failure_detail,
            updated_at=now,
            render_owner=render_owner,
        )
        self._store[artifact_id] = claimed
        return claimed
