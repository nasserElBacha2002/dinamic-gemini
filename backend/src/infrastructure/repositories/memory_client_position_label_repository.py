"""In-memory client-scoped positioning label repository."""

from __future__ import annotations

from src.application.errors import IdempotencyKeyReusedError
from src.domain.client_position_label.entities import (
    ClientPositionLabel,
    ClientPositionLabelArtifact,
    ClientPositionLabelStatus,
)


class MemoryClientPositionLabelRepository:
    def __init__(self) -> None:
        self._labels: dict[str, ClientPositionLabel] = {}
        self._artifacts: dict[str, ClientPositionLabelArtifact] = {}

    def get_by_id(self, label_id: str) -> ClientPositionLabel | None:
        return self._labels.get(label_id)

    def get_by_public_identifier(self, public_identifier: str) -> ClientPositionLabel | None:
        pub = (public_identifier or "").strip()
        if not pub:
            return None
        for label in self._labels.values():
            if label.public_identifier == pub:
                return label
        return None

    def get_by_idempotency_key(
        self, client_id: str, idempotency_key: str
    ) -> ClientPositionLabel | None:
        key = (idempotency_key or "").strip()
        if not key:
            return None
        for label in self._labels.values():
            if label.client_id == client_id and (label.idempotency_key or "").strip() == key:
                return label
        return None

    def get_active_by_normalized_name(
        self, client_id: str, normalized_name: str
    ) -> ClientPositionLabel | None:
        name = (normalized_name or "").strip().upper()
        for label in self._labels.values():
            if (
                label.client_id == client_id
                and label.normalized_name == name
                and label.status == ClientPositionLabelStatus.ACTIVE
            ):
                return label
        return None

    def list_by_client(
        self,
        client_id: str,
        *,
        status: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ClientPositionLabel]:
        rows = [lab for lab in self._labels.values() if lab.client_id == client_id]
        if status:
            rows = [lab for lab in rows if lab.status.value == status.upper()]
        if search:
            q = search.strip().lower()
            rows = [
                lab
                for lab in rows
                if q in lab.name.lower()
                or q in (lab.description or "").lower()
                or q in lab.public_identifier.lower()
            ]
        rows.sort(key=lambda lab: (lab.created_at, lab.id), reverse=True)
        return rows[offset : offset + limit]

    def count_by_client(
        self,
        client_id: str,
        *,
        status: str | None = None,
        search: str | None = None,
    ) -> int:
        return len(
            self.list_by_client(
                client_id, status=status, search=search, limit=10_000_000, offset=0
            )
        )

    def save(self, label: ClientPositionLabel) -> ClientPositionLabel:
        key = (label.idempotency_key or "").strip()
        if key:
            for existing in self._labels.values():
                if existing.id == label.id:
                    continue
                if (
                    existing.client_id == label.client_id
                    and (existing.idempotency_key or "").strip() == key
                ):
                    raise IdempotencyKeyReusedError(
                        "IDEMPOTENCY_KEY_REUSED: key already registered"
                    )
        self._labels[label.id] = label
        return label

    def get_artifact(
        self,
        label_id: str,
        *,
        format: str,
        preset: str,
        template_version: int,
        marker_version: int,
    ) -> ClientPositionLabelArtifact | None:
        fmt = (format or "").upper()
        for art in self._artifacts.values():
            if (
                art.label_id == label_id
                and art.format == fmt
                and art.preset == preset
                and art.template_version == template_version
                and art.marker_version == marker_version
            ):
                return art
        return None

    def save_artifact(self, artifact: ClientPositionLabelArtifact) -> ClientPositionLabelArtifact:
        existing = self.get_artifact(
            artifact.label_id,
            format=artifact.format,
            preset=artifact.preset,
            template_version=artifact.template_version,
            marker_version=artifact.marker_version,
        )
        if existing is not None and existing.id != artifact.id:
            del self._artifacts[existing.id]
        self._artifacts[artifact.id] = artifact
        return artifact
