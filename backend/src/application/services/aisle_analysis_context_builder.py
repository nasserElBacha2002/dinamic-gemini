"""Build AnalysisContext for aisle analysis — v3.2.4."""

from __future__ import annotations

from collections.abc import Mapping

from src.application.services.inventory_visual_reference_resolver import (
    InventoryVisualReferenceResolver,
)
from src.pipeline.contracts.analysis_context import (
    AnalysisContext,
    AnalysisImage,
    VisualReferenceContext,
)

INVENTORY_REFERENCES_INSTRUCTION = (
    "Inventory visual references represent valid examples of the expected visual "
    "standard for this inventory, such as pallet labels or typical tag formats. "
    "They should be treated as comparative context and not as primary evidence."
)


class AisleAnalysisContextBuilder:
    """Build shared AnalysisContext for aisle analysis, including inventory visual references."""

    def __init__(
        self,
        reference_resolver: InventoryVisualReferenceResolver,
    ) -> None:
        self._reference_resolver = reference_resolver

    def build(
        self,
        *,
        inventory_id: str,
        primary_evidence: list[AnalysisImage],
        metadata: Mapping[str, object] | None = None,
    ) -> AnalysisContext:
        visual_refs: list[VisualReferenceContext] = self._reference_resolver.resolve_for_inventory(
            inventory_id
        )

        instructions: list[str] = []
        if visual_refs:
            instructions.append(INVENTORY_REFERENCES_INSTRUCTION)

        return AnalysisContext(
            primary_evidence=primary_evidence,
            visual_references=visual_refs,
            instructions=instructions,
            metadata=metadata,
        )
