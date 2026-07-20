"""In-memory SupplierExtractionProfileRepository (Phase 6)."""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from datetime import datetime, timezone

from src.application.ports.supplier_extraction_profile_repository import (
    SupplierExtractionProfileRepository,
    SupplierReferenceAnnotationRepository,
)
from src.domain.client_supplier.extraction_profile import (
    ExtractionProfileStatus,
    ReferenceAnnotation,
    SupplierExtractionProfile,
)


class MemorySupplierExtractionProfileRepository(SupplierExtractionProfileRepository):
    def __init__(self) -> None:
        self._rows: dict[str, SupplierExtractionProfile] = {}

    def save(self, profile: SupplierExtractionProfile) -> None:
        self._rows[profile.id] = deepcopy(profile)

    def get_by_id(self, profile_id: str) -> SupplierExtractionProfile | None:
        row = self._rows.get(profile_id)
        return deepcopy(row) if row else None

    def get_by_client_supplier_version(
        self, client_id: str, supplier_id: str, version: int
    ) -> SupplierExtractionProfile | None:
        for row in self._rows.values():
            if (
                row.client_id == client_id
                and row.supplier_id == supplier_id
                and row.version == version
            ):
                return deepcopy(row)
        return None

    def get_active(
        self, client_id: str, supplier_id: str
    ) -> SupplierExtractionProfile | None:
        for row in self._rows.values():
            if (
                row.client_id == client_id
                and row.supplier_id == supplier_id
                and row.status is ExtractionProfileStatus.ACTIVE
            ):
                return deepcopy(row)
        return None

    def list_by_supplier(
        self, client_id: str, supplier_id: str
    ) -> Sequence[SupplierExtractionProfile]:
        rows = [
            deepcopy(r)
            for r in self._rows.values()
            if r.client_id == client_id and r.supplier_id == supplier_id
        ]
        return sorted(rows, key=lambda r: r.version, reverse=True)

    def next_version(self, client_id: str, supplier_id: str) -> int:
        versions = [
            r.version
            for r in self._rows.values()
            if r.client_id == client_id and r.supplier_id == supplier_id
        ]
        return (max(versions) if versions else 0) + 1

    def create_next_version(
        self,
        *,
        client_id: str,
        supplier_id: str,
        profile_key: str,
        configuration: object,
        visual_notes: str | None,
        created_by: str | None,
        created_at: object,
        profile_id: str | None = None,
    ) -> SupplierExtractionProfile:
        from uuid import uuid4

        from src.application.errors import SupplierExtractionProfileVersionConflictError

        version = self.next_version(client_id, supplier_id)
        # Detect race: another insert claimed same version between next_version and save.
        for row in self._rows.values():
            if (
                row.client_id == client_id
                and row.supplier_id == supplier_id
                and row.version == version
            ):
                raise SupplierExtractionProfileVersionConflictError(
                    "version_conflict"
                )
        now = created_at if isinstance(created_at, datetime) else datetime.now(timezone.utc)
        created = SupplierExtractionProfile(
            id=profile_id or str(uuid4()),
            client_id=client_id,
            supplier_id=supplier_id,
            profile_key=profile_key,
            version=version,
            status=ExtractionProfileStatus.DRAFT,
            configuration=configuration,  # type: ignore[arg-type]
            visual_notes=visual_notes,
            created_by=created_by,
            created_at=now,
            updated_at=now,
            row_version=1,
        )
        self.save(created)
        return deepcopy(created)

    def activate_version(
        self,
        *,
        client_id: str,
        supplier_id: str,
        profile_id: str,
        activated_by: str | None,
        expected_row_version: int | None = None,
    ) -> SupplierExtractionProfile:
        target = self._rows.get(profile_id)
        if target is None or target.client_id != client_id or target.supplier_id != supplier_id:
            raise KeyError("profile_not_found")
        if expected_row_version is not None and target.row_version != expected_row_version:
            raise ValueError("row_version_conflict")
        now = datetime.now(timezone.utc)
        for row in self._rows.values():
            if (
                row.client_id == client_id
                and row.supplier_id == supplier_id
                and row.status is ExtractionProfileStatus.ACTIVE
                and row.id != profile_id
            ):
                row.status = ExtractionProfileStatus.SUPERSEDED
                row.superseded_at = now
                row.row_version += 1
        target.status = ExtractionProfileStatus.ACTIVE
        target.activated_at = now
        target.activated_by = activated_by
        target.superseded_at = None
        target.updated_at = now
        target.row_version += 1
        return deepcopy(target)


class MemorySupplierReferenceAnnotationRepository(SupplierReferenceAnnotationRepository):
    def __init__(self) -> None:
        self._by_template: dict[str, list[ReferenceAnnotation]] = {}

    def list_by_template(self, template_image_id: str) -> Sequence[ReferenceAnnotation]:
        return list(self._by_template.get(template_image_id, []))

    def replace_for_template(
        self, template_image_id: str, annotations: Sequence[ReferenceAnnotation]
    ) -> None:
        self._by_template[template_image_id] = list(annotations)


__all__ = [
    "MemorySupplierExtractionProfileRepository",
    "MemorySupplierReferenceAnnotationRepository",
]
