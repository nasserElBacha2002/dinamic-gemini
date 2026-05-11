"""Build AnalysisContext for aisle analysis — v3.2.4 / Phase C7 (supplier reference images)."""

from __future__ import annotations

from collections.abc import Mapping

from src.application.services.supplier_reference_image_resolver import (
    SupplierReferenceImageResolver,
)
from src.domain.aisle.entities import Aisle
from src.pipeline.contracts.analysis_context import (
    AnalysisContext,
    AnalysisImage,
    VisualReferenceContext,
)

REFERENCE_SOURCE_SUPPLIER_REFERENCE_IMAGES = "supplier_reference_images"

# Resolution status values (stable for logs and tests; do not rename casually).
SUPPLIER_REFERENCE_RESOLUTION_RESOLVED = "resolved"
SUPPLIER_REFERENCE_RESOLUTION_FALLBACK_INVENTORY_WITHOUT_CLIENT = (
    "fallback_inventory_without_client"
)
SUPPLIER_REFERENCE_RESOLUTION_FALLBACK_AISLE_WITHOUT_CLIENT_SUPPLIER = (
    "fallback_aisle_without_client_supplier"
)
SUPPLIER_REFERENCE_RESOLUTION_FALLBACK_NO_ACTIVE_REFERENCE_IMAGES = (
    "fallback_no_active_reference_images"
)

SUPPLIER_REFERENCES_INSTRUCTION = (
    "Supplier reference images illustrate the expected visual standard for products from "
    "the supplier linked to this aisle (for example pallet labels or typical tag formats). "
    "They are comparative context only: not primary evidence, not inventoried product listings, "
    "and must not be used as proof that a product is physically present in the aisle."
)


class AisleAnalysisContextBuilder:
    """Build shared AnalysisContext for aisle analysis, including supplier visual references."""

    def __init__(
        self,
        reference_resolver: SupplierReferenceImageResolver,
    ) -> None:
        self._reference_resolver = reference_resolver

    def build(
        self,
        *,
        aisle: Aisle,
        primary_evidence: list[AnalysisImage],
        metadata: Mapping[str, object] | None = None,
        inventory_client_id: str | None = None,
    ) -> AnalysisContext:
        """Build context for one aisle.

        ``inventory_client_id`` must be the owning inventory's ``client_id`` when known.
        Blank/missing client skips supplier reference images (safe fallback; job continues).
        """
        merged_meta: dict[str, object] = {}
        if metadata:
            merged_meta.update(dict(metadata))

        inv_client = (inventory_client_id or "").strip()
        supplier_id = (aisle.client_supplier_id or "").strip()

        merged_meta["reference_source"] = REFERENCE_SOURCE_SUPPLIER_REFERENCE_IMAGES
        merged_meta["client_supplier_id"] = supplier_id or None

        visual_refs: list[VisualReferenceContext] = []
        if not inv_client:
            merged_meta["supplier_reference_resolution_status"] = (
                SUPPLIER_REFERENCE_RESOLUTION_FALLBACK_INVENTORY_WITHOUT_CLIENT
            )
            merged_meta["supplier_reference_image_count"] = 0
        elif not supplier_id:
            merged_meta["supplier_reference_resolution_status"] = (
                SUPPLIER_REFERENCE_RESOLUTION_FALLBACK_AISLE_WITHOUT_CLIENT_SUPPLIER
            )
            merged_meta["supplier_reference_image_count"] = 0
        else:
            visual_refs = self._reference_resolver.resolve_for_supplier(aisle.client_supplier_id)
            merged_meta["supplier_reference_image_count"] = len(visual_refs)
            if not visual_refs:
                merged_meta["supplier_reference_resolution_status"] = (
                    SUPPLIER_REFERENCE_RESOLUTION_FALLBACK_NO_ACTIVE_REFERENCE_IMAGES
                )
            else:
                merged_meta["supplier_reference_resolution_status"] = (
                    SUPPLIER_REFERENCE_RESOLUTION_RESOLVED
                )

        instructions: list[str] = []
        if visual_refs:
            instructions.append(SUPPLIER_REFERENCES_INSTRUCTION)

        return AnalysisContext(
            primary_evidence=primary_evidence,
            visual_references=visual_refs,
            instructions=instructions,
            metadata=merged_meta,
        )
