"""v3.2.3: SKU-level consolidation in list_aisle_positions (sum quantities, one entry per SKU)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from src.api.dependencies import (
    get_aisle_repo,
    get_inventory_repo,
    get_position_repo,
    get_product_record_repo,
)
from src.api.server import app
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.positions.entities import Position, PositionStatus
from src.domain.products.entities import ProductRecord
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.repositories.memory_product_record_repository import (
    MemoryProductRecordRepository,
)


def _fake_admin() -> AuthUser:
    return AuthUser(id="admin", username="admin", role="administrator")


def _seed_basic_repos():
    now = datetime.now(timezone.utc)

    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    position_repo = MemoryPositionRepository()
    product_repo = MemoryProductRecordRepository()

    inv = Inventory("inv-pos", "WH", InventoryStatus.DRAFT, now, now)
    inv_repo.save(inv)

    aisle = Aisle("aisle-pos", "inv-pos", "A1", AisleStatus.CREATED, now, now)
    aisle_repo.save(aisle)

    return now, inv_repo, aisle_repo, position_repo, product_repo, inv, aisle


def test_list_aisle_positions_consolidates_same_sku_same_image_positions() -> None:
    """
    Same aisle, same SKU, same image: multiple positions (e.g. duplicate detections or multiple units)
    are consolidated into one entry with qty = sum of quantities.
    """
    now, inv_repo, aisle_repo, position_repo, product_repo, inv, aisle = _seed_basic_repos()

    # Two positions that represent duplicate detections from the same source image.
    p1 = Position(
        id="pos-1",
        aisle_id=aisle.id,
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id="ev-1",
        created_at=now,
        updated_at=now,
        detected_summary_json={
            "internal_code": "SKU-DEDUP",
            "final_quantity": 1,
            "source_image_id": "img-123",
            "source_image_original_filename": "photo.jpg",
        },
    )
    p2 = Position(
        id="pos-2",
        aisle_id=aisle.id,
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id="ev-1",
        created_at=now,
        updated_at=now,
        detected_summary_json={
            "internal_code": "SKU-DEDUP",
            "final_quantity": 1,
            "source_image_id": "img-123",
            "source_image_original_filename": "photo.jpg",
        },
    )
    position_repo.save(p1)
    position_repo.save(p2)

    # One product per position, same SKU and quantity 1 (post-consolidation projection).
    product_repo.save(
        ProductRecord(
            id="prod-1",
            position_id="pos-1",
            sku="SKU-DEDUP",
            description="",
            detected_quantity=1,
            confidence=0.9,
            created_at=now,
            updated_at=now,
        )
    )
    product_repo.save(
        ProductRecord(
            id="prod-2",
            position_id="pos-2",
            sku="SKU-DEDUP",
            description="",
            detected_quantity=1,
            confidence=0.9,
            created_at=now,
            updated_at=now,
        )
    )

    # Wire in-memory repos and bypass auth.
    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_inventory_repo] = lambda: inv_repo
    app.dependency_overrides[get_aisle_repo] = lambda: aisle_repo
    app.dependency_overrides[get_position_repo] = lambda: position_repo
    app.dependency_overrides[get_product_record_repo] = lambda: product_repo

    try:
        client = TestClient(app)
        resp = client.get("/api/v3/inventories/inv-pos/aisles/aisle-pos/positions")
        assert resp.status_code == 200
        data = resp.json()
        positions = data["positions"]
        assert len(positions) == 1
        assert positions[0]["sku"] == "SKU-DEDUP"
        assert positions[0]["qty"] == 2  # two positions with qty=1 each → consolidated sum
    finally:
        app.dependency_overrides.clear()


def test_list_aisle_positions_nine_real_units_same_sku_one_consolidated_entry() -> None:
    """
    Nine valid detections/units of the same SKU in the same image → one consolidated entry with qty=9.
    """
    now, inv_repo, aisle_repo, position_repo, product_repo, inv, aisle = _seed_basic_repos()

    for i in range(9):
        pid = f"pos-9-{i}"
        position_repo.save(
            Position(
                id=pid,
                aisle_id=aisle.id,
                status=PositionStatus.DETECTED,
                confidence=0.9,
                needs_review=False,
                primary_evidence_id="ev-1",
                created_at=now,
                updated_at=now,
                detected_summary_json={
                    "internal_code": "1165582",
                    "final_quantity": 1,
                    "source_image_id": "img-single",
                    "source_image_original_filename": "photo.jpg",
                },
            )
        )
        product_repo.save(
            ProductRecord(
                id=f"prod-9-{i}",
                position_id=pid,
                sku="1165582",
                description="",
                detected_quantity=1,
                confidence=0.9,
                created_at=now,
                updated_at=now,
            )
        )

    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_inventory_repo] = lambda: inv_repo
    app.dependency_overrides[get_aisle_repo] = lambda: aisle_repo
    app.dependency_overrides[get_position_repo] = lambda: position_repo
    app.dependency_overrides[get_product_record_repo] = lambda: product_repo

    try:
        client = TestClient(app)
        resp = client.get("/api/v3/inventories/inv-pos/aisles/aisle-pos/positions")
        assert resp.status_code == 200
        data = resp.json()
        positions = data["positions"]
        assert len(positions) == 1
        assert positions[0]["sku"] == "1165582"
        assert positions[0]["qty"] == 9
    finally:
        app.dependency_overrides.clear()


def test_list_aisle_positions_consolidates_same_sku_different_images_into_one_entry() -> None:
    """
    Same SKU in different images: still one consolidated entry per SKU per aisle with qty = sum.
    """
    now, inv_repo, aisle_repo, position_repo, product_repo, inv, aisle = _seed_basic_repos()

    p1 = Position(
        id="pos-img-1",
        aisle_id=aisle.id,
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id="ev-1",
        created_at=now,
        updated_at=now,
        detected_summary_json={
            "internal_code": "SKU-SAME",
            "final_quantity": 1,
            "source_image_id": "img-1",
            "source_image_original_filename": "photo1.jpg",
        },
    )
    p2 = Position(
        id="pos-img-2",
        aisle_id=aisle.id,
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id="ev-2",
        created_at=now,
        updated_at=now,
        detected_summary_json={
            "internal_code": "SKU-SAME",
            "final_quantity": 1,
            "source_image_id": "img-2",
            "source_image_original_filename": "photo2.jpg",
        },
    )
    position_repo.save(p1)
    position_repo.save(p2)

    product_repo.save(
        ProductRecord(
            id="prod-img-1",
            position_id="pos-img-1",
            sku="SKU-SAME",
            description="",
            detected_quantity=1,
            confidence=0.9,
            created_at=now,
            updated_at=now,
        )
    )
    product_repo.save(
        ProductRecord(
            id="prod-img-2",
            position_id="pos-img-2",
            sku="SKU-SAME",
            description="",
            detected_quantity=1,
            confidence=0.9,
            created_at=now,
            updated_at=now,
        )
    )

    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_inventory_repo] = lambda: inv_repo
    app.dependency_overrides[get_aisle_repo] = lambda: aisle_repo
    app.dependency_overrides[get_position_repo] = lambda: position_repo
    app.dependency_overrides[get_product_record_repo] = lambda: product_repo

    try:
        client = TestClient(app)
        resp = client.get("/api/v3/inventories/inv-pos/aisles/aisle-pos/positions")
        assert resp.status_code == 200
        data = resp.json()
        positions = data["positions"]
        assert len(positions) == 1
        assert positions[0]["sku"] == "SKU-SAME"
        assert positions[0]["qty"] == 2  # one per image, summed
    finally:
        app.dependency_overrides.clear()


def test_list_aisle_positions_normal_non_duplicate_positions_unchanged() -> None:
    """
    Different SKUs: one entry per SKU with correct quantity (no regression).
    """
    now, inv_repo, aisle_repo, position_repo, product_repo, inv, aisle = _seed_basic_repos()

    p1 = Position(
        id="pos-a",
        aisle_id=aisle.id,
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id="ev-1",
        created_at=now,
        updated_at=now,
        detected_summary_json={
            "internal_code": "SKU-A",
            "final_quantity": 2,
            "source_image_id": "img-a",
            "source_image_original_filename": "a.jpg",
        },
    )
    p2 = Position(
        id="pos-b",
        aisle_id=aisle.id,
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id="ev-2",
        created_at=now,
        updated_at=now,
        detected_summary_json={
            "internal_code": "SKU-B",
            "final_quantity": 3,
            "source_image_id": "img-b",
            "source_image_original_filename": "b.jpg",
        },
    )
    position_repo.save(p1)
    position_repo.save(p2)

    product_repo.save(
        ProductRecord(
            id="prod-a",
            position_id="pos-a",
            sku="SKU-A",
            description="",
            detected_quantity=2,
            confidence=0.9,
            created_at=now,
            updated_at=now,
        )
    )
    product_repo.save(
        ProductRecord(
            id="prod-b",
            position_id="pos-b",
            sku="SKU-B",
            description="",
            detected_quantity=3,
            confidence=0.9,
            created_at=now,
            updated_at=now,
        )
    )

    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_inventory_repo] = lambda: inv_repo
    app.dependency_overrides[get_aisle_repo] = lambda: aisle_repo
    app.dependency_overrides[get_position_repo] = lambda: position_repo
    app.dependency_overrides[get_product_record_repo] = lambda: product_repo

    try:
        client = TestClient(app)
        resp = client.get("/api/v3/inventories/inv-pos/aisles/aisle-pos/positions")
        assert resp.status_code == 200
        data = resp.json()
        positions = data["positions"]
        assert len(positions) == 2
        by_sku = {p["sku"]: p["qty"] for p in positions}
        assert by_sku["SKU-A"] == 2
        assert by_sku["SKU-B"] == 3
    finally:
        app.dependency_overrides.clear()
