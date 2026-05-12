"""Resolve supplier reference images into analysis VisualReferenceContext — Phase C7."""

from __future__ import annotations

from src.application.ports.repositories import SupplierReferenceImageRepository
from src.pipeline.contracts.analysis_context import VisualReferenceContext

ROLE_SUPPLIER_REFERENCE = "supplier_reference"


class SupplierReferenceImageResolver:
    """Load ``supplier_reference_images`` for a supplier and map to pipeline visual reference contexts."""

    def __init__(self, supplier_reference_image_repo: SupplierReferenceImageRepository) -> None:
        self._repo = supplier_reference_image_repo

    def resolve_for_supplier(self, client_supplier_id: str | None) -> list[VisualReferenceContext]:
        cid = (client_supplier_id or "").strip()
        if not cid:
            return []
        refs = self._repo.list_by_supplier(cid)
        return [
            VisualReferenceContext(
                reference_id=r.id,
                source_path=r.storage_path,
                mime_type=r.mime_type,
                role=ROLE_SUPPLIER_REFERENCE,
                created_at=r.created_at,
            )
            for r in refs
        ]
