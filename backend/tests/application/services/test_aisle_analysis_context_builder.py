"""Tests for AisleAnalysisContextBuilder — Phase C7 (supplier references)."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.services.aisle_analysis_context_builder import (
    SUPPLIER_REFERENCES_INSTRUCTION,
    AisleAnalysisContextBuilder,
)
from src.application.services.supplier_reference_image_resolver import (
    SupplierReferenceImageResolver,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.client_supplier.reference_image import SupplierReferenceImage
from src.pipeline.contracts.analysis_context import (
    AnalysisContext,
    AnalysisImage,
    VisualReferenceContext,
)
from tests.application.services.test_supplier_reference_image_resolver import _MemSupplierRepo


def _aisle(*, supplier_id: str | None = None) -> Aisle:
    now = datetime(2025, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
    return Aisle(
        id="aisle-1",
        inventory_id="inv-1",
        code="A01",
        status=AisleStatus.CREATED,
        created_at=now,
        updated_at=now,
        client_supplier_id=supplier_id,
    )


def test_builder_with_no_visual_references_produces_empty_lists() -> None:
    resolver = SupplierReferenceImageResolver(_MemSupplierRepo([]))
    builder = AisleAnalysisContextBuilder(resolver)
    primary = [
        AnalysisImage(
            id="p1",
            source_path="frames/frame_0001.jpg",
            mime_type="image/jpeg",
        )
    ]

    ctx: AnalysisContext = builder.build(
        aisle=_aisle(supplier_id="sup-1"),
        primary_evidence=primary,
        metadata={"k": "v"},
    )

    assert ctx.primary_evidence == primary
    assert ctx.visual_references == []
    assert ctx.instructions == []
    assert ctx.metadata == {"k": "v"}


def test_builder_with_no_supplier_skips_resolution() -> None:
    resolver = SupplierReferenceImageResolver(_MemSupplierRepo([]))
    builder = AisleAnalysisContextBuilder(resolver)
    ctx = builder.build(aisle=_aisle(supplier_id=None), primary_evidence=[], metadata=None)
    assert ctx.visual_references == []
    assert ctx.instructions == []


def test_builder_with_visual_references_adds_instruction_and_roles() -> None:
    now = datetime(2025, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
    row = SupplierReferenceImage(
        id="r1",
        client_supplier_id="sup-1",
        filename="r.jpg",
        storage_path="clients/suppliers/sup-1/refs/r1.jpg",
        mime_type="image/jpeg",
        file_size=10,
        created_at=now,
        updated_at=now,
    )
    resolver = SupplierReferenceImageResolver(_MemSupplierRepo([row]))
    builder = AisleAnalysisContextBuilder(resolver)

    ctx = builder.build(aisle=_aisle(supplier_id="sup-1"), primary_evidence=[], metadata=None)

    assert len(ctx.visual_references) == 1
    assert ctx.visual_references[0] == VisualReferenceContext(
        reference_id="r1",
        source_path="clients/suppliers/sup-1/refs/r1.jpg",
        mime_type="image/jpeg",
        role="supplier_reference",
        created_at=now,
    )
    assert SUPPLIER_REFERENCES_INSTRUCTION in ctx.instructions
