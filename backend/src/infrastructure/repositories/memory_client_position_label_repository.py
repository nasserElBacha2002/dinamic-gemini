"""In-memory client-scoped positioning label repository."""

from __future__ import annotations

from src.application.errors import (
    ClientPositionLabelConflictError,
    IdempotencyKeyReusedError,
)
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

    def get_by_ids(self, label_ids: list[str]) -> dict[str, ClientPositionLabel]:
        return {
            label_id: self._labels[label_id]
            for label_id in dict.fromkeys(label_ids)
            if label_id in self._labels
        }

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

    def list_active_by_hierarchy(
        self,
        client_id: str,
        *,
        pallet: str,
        side: str,
        level: int,
        marker_total: int,
    ) -> list[ClientPositionLabel]:
        pallet_n = (pallet or "").strip()
        side_n = (side or "").strip().upper()
        rows = [
            lab
            for lab in self._labels.values()
            if lab.client_id == client_id
            and lab.status == ClientPositionLabelStatus.ACTIVE
            and (lab.pallet or "") == pallet_n
            and (lab.side or "").upper() == side_n
            and lab.level == int(level)
            and lab.marker_total == int(marker_total)
        ]
        rows.sort(key=lambda lab: (lab.marker_index or 0, lab.id))
        return rows

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

    def _assert_active_marker_unique(self, label: ClientPositionLabel) -> None:
        if label.status != ClientPositionLabelStatus.ACTIVE:
            return
        if not (label.pallet or "").strip() or label.marker_index is None:
            return
        for existing in self._labels.values():
            if existing.id == label.id:
                continue
            if existing.status != ClientPositionLabelStatus.ACTIVE:
                continue
            if (
                existing.client_id == label.client_id
                and (existing.pallet or "") == (label.pallet or "")
                and (existing.side or "").upper() == (label.side or "").upper()
                and existing.level == label.level
                and existing.marker_index == label.marker_index
            ):
                raise ClientPositionLabelConflictError(
                    "Active marker already exists for this hierarchy index",
                    code="POSITION_LABEL_MARKER_ACTIVE_EXISTS",
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
        self._assert_active_marker_unique(label)
        self._labels[label.id] = label
        return label

    def save_many(self, labels: list[ClientPositionLabel]) -> list[ClientPositionLabel]:
        inserted: list[str] = []
        try:
            for label in labels:
                key = (label.idempotency_key or "").strip()
                if key:
                    for existing in self._labels.values():
                        if existing.id == label.id or existing.id in inserted:
                            continue
                        if (
                            existing.client_id == label.client_id
                            and (existing.idempotency_key or "").strip() == key
                        ):
                            raise IdempotencyKeyReusedError(
                                "IDEMPOTENCY_KEY_REUSED: key already registered"
                            )
                self._assert_active_marker_unique(label)
                for prior_id in inserted:
                    prior = self._labels[prior_id]
                    if (
                        label.status == ClientPositionLabelStatus.ACTIVE
                        and prior.status == ClientPositionLabelStatus.ACTIVE
                        and (label.pallet or "").strip()
                        and label.marker_index is not None
                        and prior.client_id == label.client_id
                        and (prior.pallet or "") == (label.pallet or "")
                        and (prior.side or "").upper() == (label.side or "").upper()
                        and prior.level == label.level
                        and prior.marker_index == label.marker_index
                    ):
                        raise ClientPositionLabelConflictError(
                            "Active marker already exists for this hierarchy index",
                            code="POSITION_LABEL_MARKER_ACTIVE_EXISTS",
                        )
                self._labels[label.id] = label
                inserted.append(label.id)
            return labels
        except Exception:
            for lid in inserted:
                self._labels.pop(lid, None)
            raise

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
