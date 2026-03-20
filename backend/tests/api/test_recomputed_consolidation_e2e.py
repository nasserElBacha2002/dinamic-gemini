"""
v3.2.3.E3 — End-to-end validation: list_aisle_positions, get_position_detail,
and consistency between FinalCountRepository, ProductRecord, and API.
"""

from __future__ import annotations

from datetime import datetime, timezone
from fastapi.testclient import TestClient

from src.api.dependencies import (
    get_aisle_repo,
    get_evidence_repo,
    get_inventory_repo,
    get_position_repo,
    get_product_record_repo,
    get_review_action_repo,
)
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from src.api.server import app
from src.application.ports.repositories import (
    FinalCountRepository,
    PositionRepository,
    ProductRecordRepository,
    RawLabelRepository,
)
from src.application.services.final_count_builder import FinalCountBuilder
from src.application.services.label_normalization import LabelNormalizationService
from src.application.use_cases.recompute_consolidated_counts import (
    RecomputeConsolidatedCountsCommand,
    RecomputeConsolidatedCountsUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.labels.entities import RawLabel
from src.domain.labels.merge import MergeRuleEngine
from src.domain.positions.entities import Position, PositionStatus
from src.domain.products.entities import ProductRecord
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_evidence_repository import MemoryEvidenceRepository
from src.infrastructure.repositories.memory_final_count_repository import MemoryFinalCountRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_normalized_label_repository import MemoryNormalizedLabelRepository
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.repositories.memory_product_record_repository import MemoryProductRecordRepository
from src.infrastructure.repositories.memory_raw_label_repository import MemoryRawLabelRepository
from src.infrastructure.repositories.memory_review_action_repository import MemoryReviewActionRepository


def _raw(
    id_: str,
    position_id: str,
    group_key: str,
    evidence_id: str,
    sku_raw: str,
    inventory_id: str = "inv-e2e",
    aisle_id: str = "aisle-e2e",
) -> RawLabel:
    return RawLabel(
        id=id_,
        inventory_id=inventory_id,
        aisle_id=aisle_id,
        position_id=position_id,
        evidence_id=evidence_id,
        group_key=group_key,
        provider="pipeline",
        source_type="hybrid",
        source_reference=None,
        sku_raw=sku_raw,
        sku_candidate=sku_raw,
        product_name_raw=None,
        detected_text=None,
        confidence=0.9,
        metadata={},
        created_at=datetime.now(timezone.utc),
    )


def _seed_repos_duplicate_aisle() -> dict:
    """Seed: 3 duplicate raw labels (same SKU, same group) → 1 normalized → 1 final. API must show qty=1."""
    now = datetime.now(timezone.utc)
    inv = Inventory("inv-e2e", "E2E Warehouse", InventoryStatus.DRAFT, now, now)
    aisle = Aisle("aisle-e2e", "inv-e2e", "E2E-01", AisleStatus.CREATED, now, now)
    pos = Position(
        id="pos-e2e-1",
        aisle_id="aisle-e2e",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id="ev-1",
        created_at=now,
        updated_at=now,
        detected_summary_json={"internal_code": "SKU-DUP", "final_quantity": 99},
        corrected_summary_json=None,
    )
    # Stale product record (would be 3 if from raw count)
    prod = ProductRecord(
        id="prod-e2e-1",
        position_id="pos-e2e-1",
        sku="SKU-DUP",
        description="",
        detected_quantity=3,
        confidence=0.9,
        created_at=now,
        updated_at=now,
    )

    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    position_repo = MemoryPositionRepository()
    product_repo = MemoryProductRecordRepository()
    evidence_repo = MemoryEvidenceRepository()
    review_repo = MemoryReviewActionRepository()
    raw_repo = MemoryRawLabelRepository()
    norm_repo = MemoryNormalizedLabelRepository()
    final_repo = MemoryFinalCountRepository()

    inv_repo.save(inv)
    aisle_repo.save(aisle)
    position_repo.save(pos)
    product_repo.save(prod)

    raw_repo.save_many([
        _raw("r1", "pos-e2e-1", "g1", "ev1", "SKU-DUP"),
        _raw("r2", "pos-e2e-1", "g1", "ev1", "SKU-DUP"),
        _raw("r3", "pos-e2e-1", "g1", "ev1", "SKU-DUP"),
    ])

    uc = RecomputeConsolidatedCountsUseCase(
        raw_label_repo=raw_repo,
        normalized_label_repo=norm_repo,
        final_count_repo=final_repo,
        product_record_repo=product_repo,
        position_repo=position_repo,
        normalization_service=LabelNormalizationService(merge_rule_engine=MergeRuleEngine()),
        final_count_builder=FinalCountBuilder(),
    )
    uc.execute(
        RecomputeConsolidatedCountsCommand(
            inventory_id="inv-e2e",
            aisle_id="aisle-e2e",
            apply_to_product_records=True,
        )
    )

    return {
        "inv_repo": inv_repo,
        "aisle_repo": aisle_repo,
        "position_repo": position_repo,
        "product_repo": product_repo,
        "evidence_repo": evidence_repo,
        "review_repo": review_repo,
        "final_repo": final_repo,
    }


def _fake_admin() -> AuthUser:
    """Bypass auth for E2E tests."""
    return AuthUser(id="admin", username="admin", role="administrator")


def test_list_aisle_positions_duplicate_raw_labels_shows_consolidated_quantity() -> None:
    """
    E3 Scenario A: Duplicate raw labels (same SKU, same group) → merged → final qty=1.
    list_aisle_positions must return qty=1, not inflated raw count (3).
    """
    repos = _seed_repos_duplicate_aisle()
    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_inventory_repo] = lambda: repos["inv_repo"]
    app.dependency_overrides[get_aisle_repo] = lambda: repos["aisle_repo"]
    app.dependency_overrides[get_position_repo] = lambda: repos["position_repo"]
    app.dependency_overrides[get_product_record_repo] = lambda: repos["product_repo"]
    try:
        client = TestClient(app)
        resp = client.get(
            "/api/v3/inventories/inv-e2e/aisles/aisle-e2e/positions"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "positions" in data
        assert len(data["positions"]) == 1
        pos_summary = data["positions"][0]
        assert pos_summary["qty"] == 1
        assert pos_summary["detected_quantity"] == 1
        assert pos_summary["qtySource"] in ("consolidated", "merge_inferred")
    finally:
        app.dependency_overrides.clear()


def test_get_position_detail_recomputed_shows_consolidated_quantity() -> None:
    """
    E3 Scenario B: get_position_detail for recomputed position.
    ProductRecord.detected_quantity must match consolidated output; no stale quantities.
    """
    repos = _seed_repos_duplicate_aisle()
    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_inventory_repo] = lambda: repos["inv_repo"]
    app.dependency_overrides[get_aisle_repo] = lambda: repos["aisle_repo"]
    app.dependency_overrides[get_position_repo] = lambda: repos["position_repo"]
    app.dependency_overrides[get_product_record_repo] = lambda: repos["product_repo"]
    app.dependency_overrides[get_evidence_repo] = lambda: repos["evidence_repo"]
    app.dependency_overrides[get_review_action_repo] = lambda: repos["review_repo"]
    try:
        client = TestClient(app)
        resp = client.get(
            "/api/v3/inventories/inv-e2e/aisles/aisle-e2e/positions/pos-e2e-1"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "position" in data
        pos = data["position"]
        assert pos["qty"] == 1
        assert pos["detected_quantity"] == 1
        assert pos["qtySource"] in ("consolidated", "merge_inferred")
    finally:
        app.dependency_overrides.clear()


def _seed_repos_normal_aisle() -> dict:
    """Seed: 1 raw → 1 normalized → 1 final. No duplicates. API must show qty=1."""
    now = datetime.now(timezone.utc)
    inv = Inventory("inv-normal", "Normal WH", InventoryStatus.DRAFT, now, now)
    aisle = Aisle("aisle-normal", "inv-normal", "N-01", AisleStatus.CREATED, now, now)
    pos = Position(
        id="pos-normal-1",
        aisle_id="aisle-normal",
        status=PositionStatus.DETECTED,
        confidence=0.95,
        needs_review=False,
        primary_evidence_id="ev-n1",
        created_at=now,
        updated_at=now,
        detected_summary_json={"internal_code": "SKU-SINGLE", "final_quantity": 1},
        corrected_summary_json=None,
    )
    prod = ProductRecord(
        id="prod-normal-1",
        position_id="pos-normal-1",
        sku="SKU-SINGLE",
        description="",
        detected_quantity=1,
        confidence=0.95,
        created_at=now,
        updated_at=now,
    )

    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    position_repo = MemoryPositionRepository()
    product_repo = MemoryProductRecordRepository()
    evidence_repo = MemoryEvidenceRepository()
    review_repo = MemoryReviewActionRepository()
    raw_repo = MemoryRawLabelRepository()
    norm_repo = MemoryNormalizedLabelRepository()
    final_repo = MemoryFinalCountRepository()

    inv_repo.save(inv)
    aisle_repo.save(aisle)
    position_repo.save(pos)
    product_repo.save(prod)
    raw_repo.save_many([_raw("r1", "pos-normal-1", "g1", "ev-n1", "SKU-SINGLE", "inv-normal", "aisle-normal")])

    uc = RecomputeConsolidatedCountsUseCase(
        raw_label_repo=raw_repo,
        normalized_label_repo=norm_repo,
        final_count_repo=final_repo,
        product_record_repo=product_repo,
        position_repo=position_repo,
        normalization_service=LabelNormalizationService(merge_rule_engine=MergeRuleEngine()),
        final_count_builder=FinalCountBuilder(),
    )
    uc.execute(
        RecomputeConsolidatedCountsCommand(
            inventory_id="inv-normal",
            aisle_id="aisle-normal",
            apply_to_product_records=True,
        )
    )

    return {
        "inv_repo": inv_repo,
        "aisle_repo": aisle_repo,
        "position_repo": position_repo,
        "product_repo": product_repo,
        "evidence_repo": evidence_repo,
        "review_repo": review_repo,
        "final_repo": final_repo,
    }


def test_list_aisle_positions_normal_non_duplicate_aisle_no_regression() -> None:
    """
    E3 Scenario G: Normal aisle with 1 raw → 1 normalized → 1 final.
    API-visible quantity remains correct; no regressions from 3.2.3.
    """
    repos = _seed_repos_normal_aisle()
    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_inventory_repo] = lambda: repos["inv_repo"]
    app.dependency_overrides[get_aisle_repo] = lambda: repos["aisle_repo"]
    app.dependency_overrides[get_position_repo] = lambda: repos["position_repo"]
    app.dependency_overrides[get_product_record_repo] = lambda: repos["product_repo"]
    try:
        client = TestClient(app)
        resp = client.get(
            "/api/v3/inventories/inv-normal/aisles/aisle-normal/positions"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["positions"]) == 1
        assert data["positions"][0]["qty"] == 1
        assert data["positions"][0]["sku"] == "SKU-SINGLE"
    finally:
        app.dependency_overrides.clear()


def test_consistency_final_count_product_record_api_aligned() -> None:
    """
    E3 Consistency: For a recomputed scope, FinalCountRepository quantity,
    ProductRecord.detected_quantity, and API summary/detail quantity must be aligned.
    """
    repos = _seed_repos_duplicate_aisle()
    final_repo: FinalCountRepository = repos["final_repo"]
    product_repo: ProductRecordRepository = repos["product_repo"]

    finals = list(final_repo.list_for_scope("inv-e2e", "aisle-e2e"))
    assert len(finals) == 1
    final_qty = finals[0].quantity
    assert final_qty == 1

    prod = product_repo.get_by_id("prod-e2e-1")
    assert prod is not None
    assert prod.detected_quantity == final_qty

    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_inventory_repo] = lambda: repos["inv_repo"]
    app.dependency_overrides[get_aisle_repo] = lambda: repos["aisle_repo"]
    app.dependency_overrides[get_position_repo] = lambda: repos["position_repo"]
    app.dependency_overrides[get_product_record_repo] = lambda: repos["product_repo"]
    app.dependency_overrides[get_evidence_repo] = lambda: repos["evidence_repo"]
    app.dependency_overrides[get_review_action_repo] = lambda: repos["review_repo"]
    try:
        client = TestClient(app)
        list_resp = client.get(
            "/api/v3/inventories/inv-e2e/aisles/aisle-e2e/positions"
        )
        assert list_resp.status_code == 200
        list_qty = list_resp.json()["positions"][0]["qty"]
        assert list_qty == final_qty

        detail_resp = client.get(
            "/api/v3/inventories/inv-e2e/aisles/aisle-e2e/positions/pos-e2e-1"
        )
        assert detail_resp.status_code == 200
        detail_qty = detail_resp.json()["position"]["qty"]
        assert detail_qty == final_qty
    finally:
        app.dependency_overrides.clear()
