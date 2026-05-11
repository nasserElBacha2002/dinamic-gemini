"""Tests for AisleAnalysisContextBuilder — Phase C7 (supplier references)."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.services.aisle_analysis_context_builder import (
    REFERENCE_SOURCE_SUPPLIER_REFERENCE_IMAGES,
    SUPPLIER_REFERENCE_RESOLUTION_FALLBACK_AISLE_WITHOUT_CLIENT_SUPPLIER,
    SUPPLIER_REFERENCE_RESOLUTION_FALLBACK_INVENTORY_WITHOUT_CLIENT,
    SUPPLIER_REFERENCE_RESOLUTION_FALLBACK_NO_ACTIVE_REFERENCE_IMAGES,
    SUPPLIER_REFERENCE_RESOLUTION_RESOLVED,
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
        inventory_client_id="client-1",
    )

    assert ctx.primary_evidence == primary
    assert ctx.visual_references == []
    assert ctx.instructions == []
    assert ctx.metadata is not None
    assert ctx.metadata.get("k") == "v"
    assert ctx.metadata.get("supplier_reference_resolution_status") == (
        SUPPLIER_REFERENCE_RESOLUTION_FALLBACK_NO_ACTIVE_REFERENCE_IMAGES
    )
    assert ctx.metadata.get("reference_source") == REFERENCE_SOURCE_SUPPLIER_REFERENCE_IMAGES


def test_builder_with_no_supplier_skips_resolution() -> None:
    resolver = SupplierReferenceImageResolver(_MemSupplierRepo([]))
    builder = AisleAnalysisContextBuilder(resolver)
    ctx = builder.build(
        aisle=_aisle(supplier_id=None),
        primary_evidence=[],
        metadata=None,
        inventory_client_id="client-1",
    )
    assert ctx.visual_references == []
    assert ctx.instructions == []
    assert ctx.metadata is not None
    assert ctx.metadata.get("supplier_reference_resolution_status") == (
        SUPPLIER_REFERENCE_RESOLUTION_FALLBACK_AISLE_WITHOUT_CLIENT_SUPPLIER
    )


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

    ctx = builder.build(
        aisle=_aisle(supplier_id="sup-1"),
        primary_evidence=[],
        metadata=None,
        inventory_client_id="client-1",
    )

    assert len(ctx.visual_references) == 1
    assert ctx.visual_references[0] == VisualReferenceContext(
        reference_id="r1",
        source_path="clients/suppliers/sup-1/refs/r1.jpg",
        mime_type="image/jpeg",
        role="supplier_reference",
        created_at=now,
    )
    assert SUPPLIER_REFERENCES_INSTRUCTION in ctx.instructions
    assert ctx.metadata is not None
    assert ctx.metadata.get("supplier_reference_resolution_status") == (
        SUPPLIER_REFERENCE_RESOLUTION_RESOLVED
    )
    assert ctx.metadata.get("supplier_reference_image_count") == 1


def test_builder_keeps_primary_evidence_separate_from_supplier_visual_references() -> None:
    now = datetime(2025, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
    row = SupplierReferenceImage(
        id="r1",
        client_supplier_id="sup-1",
        filename="r.jpg",
        storage_path="path/r.jpg",
        mime_type="image/jpeg",
        file_size=10,
        created_at=now,
        updated_at=now,
    )
    resolver = SupplierReferenceImageResolver(_MemSupplierRepo([row]))
    builder = AisleAnalysisContextBuilder(resolver)
    primary = [
        AnalysisImage(id="frame-1", source_path="frames/a.jpg", mime_type="image/jpeg"),
        AnalysisImage(id="frame-2", source_path="frames/b.jpg", mime_type="image/jpeg"),
    ]
    ctx = builder.build(
        aisle=_aisle(supplier_id="sup-1"),
        primary_evidence=primary,
        metadata=None,
        inventory_client_id="client-1",
    )
    assert len(ctx.primary_evidence) == 2
    assert len(ctx.visual_references) == 1
    assert all(p.role == "primary_evidence" for p in ctx.primary_evidence)
    assert ctx.visual_references[0].role == "supplier_reference"


def test_builder_skips_supplier_refs_when_inventory_has_no_client_even_if_repo_has_rows() -> None:
    now = datetime(2025, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
    row = SupplierReferenceImage(
        id="r1",
        client_supplier_id="sup-1",
        filename="r.jpg",
        storage_path="path/r.jpg",
        mime_type="image/jpeg",
        file_size=10,
        created_at=now,
        updated_at=now,
    )
    resolver = SupplierReferenceImageResolver(_MemSupplierRepo([row]))
    builder = AisleAnalysisContextBuilder(resolver)
    ctx = builder.build(
        aisle=_aisle(supplier_id="sup-1"),
        primary_evidence=[],
        metadata=None,
        inventory_client_id=None,
    )
    assert ctx.visual_references == []
    assert ctx.instructions == []
    assert ctx.metadata is not None
    assert ctx.metadata.get("supplier_reference_resolution_status") == (
        SUPPLIER_REFERENCE_RESOLUTION_FALLBACK_INVENTORY_WITHOUT_CLIENT
    )
    assert ctx.metadata.get("supplier_reference_image_count") == 0
