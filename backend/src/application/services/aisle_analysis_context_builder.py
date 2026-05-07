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

SUPPLIER_REFERENCES_INSTRUCTION = (
    "Supplier reference images illustrate the expected visual standard for products from "
    "the supplier linked to this aisle (for example pallet labels or typical tag formats). "
    "They should be treated as comparative context and not as primary evidence."
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
    ) -> AnalysisContext:
        visual_refs: list[VisualReferenceContext] = self._reference_resolver.resolve_for_supplier(
            aisle.client_supplier_id
        )

        instructions: list[str] = []
        if visual_refs:
            instructions.append(SUPPLIER_REFERENCES_INSTRUCTION)

        return AnalysisContext(
            primary_evidence=primary_evidence,
            visual_references=visual_refs,
            instructions=instructions,
            metadata=metadata,
        )
