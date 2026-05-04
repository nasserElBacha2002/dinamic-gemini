"""Tests for AisleAnalysisContextBuilder — v3.2.4."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.services.aisle_analysis_context_builder import (
    INVENTORY_REFERENCES_INSTRUCTION,
    AisleAnalysisContextBuilder,
)
from src.application.services.inventory_visual_reference_resolver import (
    InventoryVisualReferenceResolver,
)
from src.pipeline.contracts.analysis_context import (
    AnalysisContext,
    AnalysisImage,
    VisualReferenceContext,
)


class StubResolver(InventoryVisualReferenceResolver):
    def __init__(self, refs: list[VisualReferenceContext]) -> None:
        # Bypass base init; we won't use the repos in tests.
        self._refs = refs  # type: ignore[assignment]

    def resolve_for_inventory(self, inventory_id: str) -> list[VisualReferenceContext]:  # type: ignore[override]
        return list(self._refs)


def test_builder_with_no_visual_references_produces_empty_lists() -> None:
    resolver = StubResolver(refs=[])
    builder = AisleAnalysisContextBuilder(resolver)
    primary = [
        AnalysisImage(
            id="p1",
            source_path="frames/frame_0001.jpg",
            mime_type="image/jpeg",
        )
    ]

    ctx: AnalysisContext = builder.build(
        inventory_id="inv-1", primary_evidence=primary, metadata={"k": "v"}
    )

    assert ctx.primary_evidence == primary
    assert ctx.visual_references == []
    assert ctx.instructions == []
    assert ctx.metadata == {"k": "v"}


def test_builder_with_visual_references_adds_instruction_and_refs() -> None:
    now = datetime(2025, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
    refs = [
        VisualReferenceContext(
            reference_id="r1",
            source_path="inventories/inv-1/visual_references/r1.jpg",
            mime_type="image/jpeg",
            created_at=now,
        )
    ]
    resolver = StubResolver(refs=refs)
    builder = AisleAnalysisContextBuilder(resolver)

    ctx = builder.build(inventory_id="inv-1", primary_evidence=[], metadata=None)

    assert ctx.visual_references == refs
    assert INVENTORY_REFERENCES_INSTRUCTION in ctx.instructions
