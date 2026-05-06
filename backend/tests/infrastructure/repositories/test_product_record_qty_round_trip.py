"""v3.2.2: ProductRecord persistence round-trip for qty provenance fields."""

from datetime import datetime, timezone

from src.domain.products.entities import ProductRecord
from src.infrastructure.repositories.memory_product_record_repository import (
    MemoryProductRecordRepository,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def test_product_record_qty_provenance_round_trip_detected() -> None:
    """Save and load ProductRecord with qty_source=detected; all qty fields round-trip."""
    repo = MemoryProductRecordRepository()
    now = _now()
    product = ProductRecord(
        id="p1",
        position_id="pos1",
        sku="SKU-A",
        description="",
        detected_quantity=5,
        confidence=0.9,
        created_at=now,
        updated_at=now,
        corrected_quantity=None,
        qty_source="detected",
        qty_inference_reason=None,
        raw_qty=5,
        qty_parse_status="valid_positive",
    )
    repo.save(product)
    loaded = repo.get_by_id("p1")
    assert loaded is not None
    assert loaded.detected_quantity == 5
    assert loaded.qty_source == "detected"
    assert loaded.qty_inference_reason is None
    assert loaded.raw_qty == 5
    assert loaded.qty_parse_status == "valid_positive"


def test_product_record_qty_provenance_round_trip_inferred() -> None:
    """Save and load ProductRecord with qty_source=inferred and qty_inference_reason."""
    repo = MemoryProductRecordRepository()
    now = _now()
    product = ProductRecord(
        id="p2",
        position_id="pos2",
        sku="SKU-B",
        description="",
        detected_quantity=1,
        confidence=0.85,
        created_at=now,
        updated_at=now,
        corrected_quantity=None,
        qty_source="inferred",
        qty_inference_reason="valid_evidence_without_explicit_quantity",
        raw_qty=None,
        qty_parse_status="missing",
    )
    repo.save(product)
    loaded = repo.get_by_id("p2")
    assert loaded is not None
    assert loaded.detected_quantity == 1
    assert loaded.qty_source == "inferred"
    assert loaded.qty_inference_reason == "valid_evidence_without_explicit_quantity"
    assert loaded.raw_qty is None
    assert loaded.qty_parse_status == "missing"


def test_product_record_qty_provenance_round_trip_unresolved() -> None:
    """Save and load ProductRecord with qty_source=unresolved."""
    repo = MemoryProductRecordRepository()
    now = _now()
    product = ProductRecord(
        id="p3",
        position_id="pos3",
        sku="SKU-C",
        description="",
        detected_quantity=0,
        confidence=0.5,
        created_at=now,
        updated_at=now,
        corrected_quantity=None,
        qty_source="unresolved",
        qty_inference_reason=None,
        raw_qty=None,
        qty_parse_status="missing",
    )
    repo.save(product)
    loaded = repo.get_by_id("p3")
    assert loaded is not None
    assert loaded.detected_quantity == 0
    assert loaded.qty_source == "unresolved"
    assert loaded.qty_parse_status == "missing"


def test_product_record_list_by_position_returns_saved_with_qty_fields() -> None:
    """list_by_position returns records with qty provenance intact."""
    repo = MemoryProductRecordRepository()
    now = _now()
    product = ProductRecord(
        id="p4",
        position_id="pos4",
        sku="SKU-D",
        description="desc",
        detected_quantity=2,
        confidence=0.9,
        created_at=now,
        updated_at=now,
        corrected_quantity=None,
        qty_source="inferred",
        qty_inference_reason="valid_evidence_without_explicit_quantity",
        raw_qty=0,
        qty_parse_status="zero",
    )
    repo.save(product)
    by_position = repo.list_by_position("pos4")
    assert len(by_position) == 1
    assert by_position[0].qty_source == "inferred"
    assert by_position[0].qty_parse_status == "zero"
    assert by_position[0].raw_qty == 0


def test_memory_list_by_position_ids_matches_union_of_list_by_position() -> None:
    """Batch port returns the same multiset as per-position reads (Phase 3)."""
    repo = MemoryProductRecordRepository()
    now = _now()
    for pid, sku in (("pos-a", "S-A"), ("pos-b", "S-B"), ("pos-a", "S-A2")):
        repo.save(
            ProductRecord(
                id=f"prod-{pid}-{sku}",
                position_id=pid,
                sku=sku,
                description="",
                detected_quantity=1,
                confidence=0.9,
                created_at=now,
                updated_at=now,
            )
        )
    batch = list(repo.list_by_position_ids(["pos-a", "pos-b"]))
    union = list(repo.list_by_position("pos-a")) + list(repo.list_by_position("pos-b"))
    assert {p.id for p in batch} == {p.id for p in union}
    assert repo.list_by_position_ids(()) == []


def test_memory_list_by_position_ids_empty_ids_returns_empty() -> None:
    assert MemoryProductRecordRepository().list_by_position_ids([]) == []
