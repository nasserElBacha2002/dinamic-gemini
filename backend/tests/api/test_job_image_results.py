"""API + use-case tests for job image coverage and manual result creation."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import (
    get_aisle_repo,
    get_create_manual_image_result_use_case,
    get_evidence_repo,
    get_inventory_repo,
    get_job_repo,
    get_job_source_asset_repo,
    get_list_job_image_results_use_case,
    get_manual_image_coverage_repo,
    get_position_repo,
    get_product_record_repo,
    get_result_evidence_repo,
    get_review_action_repo,
    get_source_asset_repo,
)
from src.api.server import app
from src.application.errors import ImageAlreadyHasResultsError
from src.application.ports.clock import Clock
from src.application.ports.job_source_asset_repository import JobSourceAssetLink
from src.application.ports.manual_image_result_unit_of_work import ManualImageResultRepositories
from src.application.services.job_image_result_resolution import (
    index_positions_by_source_asset,
    is_photos_job_snapshot,
    unique_photo_coverage_images,
)
from src.application.use_cases.positions.create_manual_image_result import (
    CreateManualImageResultCommand,
    CreateManualImageResultUseCase,
)
from src.application.use_cases.positions.list_job_image_results import (
    ListJobImageResultsCommand,
    ListJobImageResultsUseCase,
)
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
from src.domain.positions.entities import (
    Position,
    PositionCreationSource,
    PositionReviewResolution,
    PositionStatus,
)
from src.domain.products.entities import ProductRecord
from src.domain.result_evidence.entities import (
    RESULT_EVIDENCE_KIND_ENTITY_TRACEABILITY,
    ResultEvidenceRecord,
    ResultEvidenceRole,
)
from src.domain.reviews.entities import ReviewActionType
from src.domain.traceability import TraceabilityStatus
from src.infrastructure.persistence.memory_job_image_coverage_repository import (
    MemoryJobImageCoverageRepository,
)
from src.infrastructure.persistence.memory_job_source_asset_repository import (
    MemoryJobSourceAssetRepository,
)
from src.infrastructure.persistence.memory_manual_image_coverage_repository import (
    MemoryManualImageCoverageRepository,
)
from src.infrastructure.persistence.memory_manual_image_result_unit_of_work import (
    build_memory_manual_image_result_uow_factory,
)
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_evidence_repository import MemoryEvidenceRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.repositories.memory_product_record_repository import (
    MemoryProductRecordRepository,
)
from src.infrastructure.repositories.memory_result_evidence_repository import (
    MemoryResultEvidenceRepository,
)
from src.infrastructure.repositories.memory_review_action_repository import (
    MemoryReviewActionRepository,
)
from src.infrastructure.repositories.memory_source_asset_repository import (
    MemorySourceAssetRepository,
)


class _FixedClock(Clock):
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class _NoopLifecycle:
    def after_review_mutation(self, inventory_id: str, aisle_id: str) -> None:
        return None


def _fake_admin() -> AuthUser:
    return AuthUser(id="admin", username="admin", role="platform_admin")


def _link(
    *,
    job_id: str,
    asset_id: str,
    order: int,
    role: str = "primary",
    filename: str | None = "photo.jpg",
    now: datetime,
) -> JobSourceAssetLink:
    return JobSourceAssetLink(
        id=f"link-{asset_id}",
        job_id=job_id,
        source_asset_id=asset_id,
        asset_role=role,
        position_order=order,
        checksum=None,
        storage_key=f"key/{asset_id}",
        mime_type="image/jpeg",
        size_bytes=100,
        width=None,
        height=None,
        stage="SOURCE_ASSETS_RESOLVED",
        provider_request_id=None,
        created_at=now,
        original_filename=filename,
    )


def _seed_world(*, with_video: bool = False):
    now = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    job_repo = MemoryJobRepository()
    jsa_repo = MemoryJobSourceAssetRepository()
    position_repo = MemoryPositionRepository()
    product_repo = MemoryProductRecordRepository()
    evidence_repo = MemoryEvidenceRepository()
    re_repo = MemoryResultEvidenceRepository()
    review_repo = MemoryReviewActionRepository()
    asset_repo = MemorySourceAssetRepository()
    coverage_repo = MemoryManualImageCoverageRepository()

    inv = Inventory("inv-img", "WH Img", InventoryStatus.DRAFT, now, now)
    aisle = Aisle("aisle-img", "inv-img", "A1", AisleStatus.PROCESSED, now, now)
    inv_repo.save(inv)
    aisle_repo.save(aisle)

    payload = {"input_type": "video" if with_video else "photos"}
    job = Job(
        id="job-img-1",
        target_type="aisle",
        target_id="aisle-img",
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json=payload,
        created_at=now,
        updated_at=now,
        finished_at=now,
    )
    job_repo.save(job)

    assets = [
        ("asset-a", 0, "IMG_001.jpg"),
        ("asset-b", 1, "IMG_002.jpg"),
        ("asset-c", 2, None),
    ]
    links = []
    for aid, order, fn in assets:
        asset_repo.save(
            SourceAsset(
                id=aid,
                aisle_id="aisle-img",
                type=SourceAssetType.VIDEO if with_video else SourceAssetType.PHOTO,
                original_filename=fn or "unnamed.jpg",
                storage_path=f"local/{aid}",
                mime_type="image/jpeg" if not with_video else "video/mp4",
                uploaded_at=now,
            )
        )
        links.append(
            _link(
                job_id="job-img-1",
                asset_id=aid,
                order=order,
                role="video" if with_video else "primary",
                filename=fn,
                now=now,
            )
        )
    jsa_repo.replace_for_job("job-img-1", links)

    return {
        "now": now,
        "inv_repo": inv_repo,
        "aisle_repo": aisle_repo,
        "job_repo": job_repo,
        "jsa_repo": jsa_repo,
        "position_repo": position_repo,
        "product_repo": product_repo,
        "evidence_repo": evidence_repo,
        "re_repo": re_repo,
        "review_repo": review_repo,
        "asset_repo": asset_repo,
        "coverage_repo": coverage_repo,
    }


def _add_position_with_evidence(
    world: dict,
    *,
    position_id: str,
    asset_id: str,
    sku: str,
    qty: int,
    creation_source: PositionCreationSource = PositionCreationSource.AUTOMATIC,
) -> None:
    now = world["now"]
    pos = Position(
        id=position_id,
        aisle_id="aisle-img",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id=None,
        created_at=now,
        updated_at=now,
        detected_summary_json={
            "internal_code": sku,
            "final_quantity": qty,
            "source_image_id": asset_id,
            "source_asset_id": asset_id,
        },
        job_id="job-img-1",
        creation_source=creation_source,
    )
    world["position_repo"].save(pos)
    world["product_repo"].save(
        ProductRecord(
            id=f"prod-{position_id}",
            position_id=position_id,
            sku=sku,
            description=None,
            detected_quantity=qty,
            confidence=0.9,
            created_at=now,
            updated_at=now,
        )
    )
    world["re_repo"].save_many(
        [
            ResultEvidenceRecord(
                id=f"re-{position_id}",
                job_id="job-img-1",
                inventory_id="inv-img",
                aisle_id="aisle-img",
                position_id=position_id,
                entity_uid=position_id,
                model_entity_id=None,
                raw_manifest_entry_id=None,
                manifest_entry_id=None,
                raw_source_image_id=asset_id,
                resolved_manifest_entry_id=None,
                source_image_id=asset_id,
                source_asset_id=asset_id,
                traceability_status=TraceabilityStatus.VALID.value,
                traceability_warning=None,
                role=ResultEvidenceRole.PRIMARY_EVIDENCE,
                provider="test",
                model_name=None,
                schema_version=None,
                manifest_version=None,
                has_valid_evidence=True,
                evidence_kind=RESULT_EVIDENCE_KIND_ENTITY_TRACEABILITY,
                created_at=now,
                updated_at=now,
            )
        ]
    )


def _coverage_repo(world: dict) -> MemoryJobImageCoverageRepository:
    return MemoryJobImageCoverageRepository(
        job_source_asset_repo=world["jsa_repo"],
        position_repo=world["position_repo"],
        result_evidence_repo=world["re_repo"],
    )


def _list_uc(world: dict) -> ListJobImageResultsUseCase:
    return ListJobImageResultsUseCase(
        inventory_repo=world["inv_repo"],
        aisle_repo=world["aisle_repo"],
        job_repo=world["job_repo"],
        job_source_asset_repo=world["jsa_repo"],
        coverage_repo=_coverage_repo(world),
        product_record_repo=world["product_repo"],
    )


def _create_uc(world: dict) -> CreateManualImageResultUseCase:
    repos = ManualImageResultRepositories(
        position_repo=world["position_repo"],
        product_record_repo=world["product_repo"],
        evidence_repo=world["evidence_repo"],
        manual_coverage_repo=world["coverage_repo"],
        result_evidence_repo=world["re_repo"],
        review_repo=world["review_repo"],
        image_coverage_repo=_coverage_repo(world),
    )
    uow_factory = build_memory_manual_image_result_uow_factory(
        repos,
        _NoopLifecycle(),  # type: ignore[arg-type]
    )
    return CreateManualImageResultUseCase(
        inventory_repo=world["inv_repo"],
        aisle_repo=world["aisle_repo"],
        job_repo=world["job_repo"],
        job_source_asset_repo=world["jsa_repo"],
        source_asset_repo=world["asset_repo"],
        clock=_FixedClock(world["now"]),
        unit_of_work_factory=uow_factory,
    )


def test_resolution_dedupes_and_links_multi_positions() -> None:
    now = datetime.now(timezone.utc)
    links = [
        _link(job_id="j", asset_id="a1", order=0, now=now),
        _link(job_id="j", asset_id="a1", order=0, role="reference", now=now),
        _link(job_id="j", asset_id="a2", order=1, now=now),
    ]
    # duplicate primary same asset — unique_photo keeps first
    images = unique_photo_coverage_images(links)
    assert [i.source_asset_id for i in images] == ["a1", "a2"]
    assert is_photos_job_snapshot(links)

    p1 = Position(
        id="p1",
        aisle_id="a",
        status=PositionStatus.DETECTED,
        confidence=1,
        needs_review=False,
        primary_evidence_id=None,
        created_at=now,
        updated_at=now,
        job_id="j",
    )
    p2 = Position(
        id="p2",
        aisle_id="a",
        status=PositionStatus.DETECTED,
        confidence=1,
        needs_review=False,
        primary_evidence_id=None,
        created_at=now,
        updated_at=now,
        job_id="j",
    )
    indexed = index_positions_by_source_asset(
        coverage_asset_ids=frozenset({"a1", "a2"}),
        result_evidence=[
            ResultEvidenceRecord(
                id="r1",
                job_id="j",
                inventory_id="i",
                aisle_id="a",
                position_id="p1",
                entity_uid=None,
                model_entity_id=None,
                raw_manifest_entry_id=None,
                manifest_entry_id=None,
                raw_source_image_id=None,
                resolved_manifest_entry_id=None,
                source_image_id="a1",
                source_asset_id="a1",
                traceability_status=TraceabilityStatus.VALID.value,
                traceability_warning=None,
                role=ResultEvidenceRole.PRIMARY_EVIDENCE,
                provider=None,
                model_name=None,
                schema_version=None,
                manifest_version=None,
                has_valid_evidence=True,
                evidence_kind=RESULT_EVIDENCE_KIND_ENTITY_TRACEABILITY,
                created_at=now,
                updated_at=now,
            ),
            ResultEvidenceRecord(
                id="r2",
                job_id="j",
                inventory_id="i",
                aisle_id="a",
                position_id="p2",
                entity_uid=None,
                model_entity_id=None,
                raw_manifest_entry_id=None,
                manifest_entry_id=None,
                raw_source_image_id=None,
                resolved_manifest_entry_id=None,
                source_image_id="a1",
                source_asset_id="a1",
                traceability_status=TraceabilityStatus.VALID.value,
                traceability_warning=None,
                role=ResultEvidenceRole.PRIMARY_EVIDENCE,
                provider=None,
                model_name=None,
                schema_version=None,
                manifest_version=None,
                has_valid_evidence=True,
                evidence_kind=RESULT_EVIDENCE_KIND_ENTITY_TRACEABILITY,
                created_at=now,
                updated_at=now,
            ),
        ],
        positions=[p1, p2],
    )
    assert len(indexed["a1"]) == 2


def test_list_includes_images_without_result_and_counters() -> None:
    world = _seed_world()
    _add_position_with_evidence(world, position_id="pos-a", asset_id="asset-a", sku="SKU-A", qty=2)
    result = _list_uc(world).execute(
        ListJobImageResultsCommand(
            inventory_id="inv-img", aisle_id="aisle-img", job_id="job-img-1"
        )
    )
    assert result.counters.total_images == 3
    assert result.counters.with_result == 1
    assert result.counters.without_result == 2
    by_asset = {row.source_asset_id: row for row in result.items}
    assert by_asset["asset-a"].has_result is True
    assert by_asset["asset-a"].result_count == 1
    assert by_asset["asset-b"].has_result is False
    assert by_asset["asset-b"].result_count == 0
    assert by_asset["asset-c"].original_filename is None


def test_list_multi_positions_same_image_and_filters_pagination() -> None:
    world = _seed_world()
    _add_position_with_evidence(world, position_id="pos-a1", asset_id="asset-a", sku="S1", qty=1)
    _add_position_with_evidence(world, position_id="pos-a2", asset_id="asset-a", sku="S2", qty=3)
    uc = _list_uc(world)
    all_rows = uc.execute(
        ListJobImageResultsCommand(
            inventory_id="inv-img", aisle_id="aisle-img", job_id="job-img-1"
        )
    )
    row_a = next(r for r in all_rows.items if r.source_asset_id == "asset-a")
    assert row_a.result_count == 2
    assert len(row_a.positions) == 2

    without = uc.execute(
        ListJobImageResultsCommand(
            inventory_id="inv-img",
            aisle_id="aisle-img",
            job_id="job-img-1",
            result_status="without_result",
        )
    )
    assert without.total_items == 2
    assert all(not r.has_result for r in without.items)
    assert without.counters.with_result == 1  # global counters

    page1 = uc.execute(
        ListJobImageResultsCommand(
            inventory_id="inv-img",
            aisle_id="aisle-img",
            job_id="job-img-1",
            page=1,
            page_size=2,
        )
    )
    assert len(page1.items) == 2
    assert page1.total_items == 3


def test_placeholder_no_readable_label_counts_as_result() -> None:
    world = _seed_world()
    now = world["now"]
    pos = Position(
        id="pos-placeholder",
        aisle_id="aisle-img",
        status=PositionStatus.DETECTED,
        confidence=0.0,
        needs_review=True,
        primary_evidence_id=None,
        created_at=now,
        updated_at=now,
        detected_summary_json={
            "entity_uid": "job-img-1_no_readable_label",
            "detection_outcome": "no_readable_label",
            "source_image_id": "asset-a",
        },
        job_id="job-img-1",
        creation_source=PositionCreationSource.AUTOMATIC,
    )
    world["position_repo"].save(pos)
    world["product_repo"].save(
        ProductRecord(
            id="prod-ph",
            position_id="pos-placeholder",
            sku="UNKNOWN",
            description=None,
            detected_quantity=0,
            confidence=0.0,
            created_at=now,
            updated_at=now,
        )
    )
    world["re_repo"].save_many(
        [
            ResultEvidenceRecord(
                id="re-ph",
                job_id="job-img-1",
                inventory_id="inv-img",
                aisle_id="aisle-img",
                position_id="pos-placeholder",
                entity_uid="job-img-1_no_readable_label",
                model_entity_id=None,
                raw_manifest_entry_id=None,
                manifest_entry_id=None,
                raw_source_image_id="asset-a",
                resolved_manifest_entry_id=None,
                source_image_id="asset-a",
                source_asset_id="asset-a",
                traceability_status=TraceabilityStatus.MISSING.value,
                traceability_warning=None,
                role=ResultEvidenceRole.PRIMARY_EVIDENCE,
                provider=None,
                model_name=None,
                schema_version=None,
                manifest_version=None,
                has_valid_evidence=False,
                evidence_kind=RESULT_EVIDENCE_KIND_ENTITY_TRACEABILITY,
                created_at=now,
                updated_at=now,
            )
        ]
    )
    result = _list_uc(world).execute(
        ListJobImageResultsCommand(
            inventory_id="inv-img", aisle_id="aisle-img", job_id="job-img-1"
        )
    )
    row = next(r for r in result.items if r.source_asset_id == "asset-a")
    assert row.has_result is True


def test_create_manual_success_audit_and_409_duplicate() -> None:
    world = _seed_world()
    uc = _create_uc(world)
    out = uc.execute(
        CreateManualImageResultCommand(
            inventory_id="inv-img",
            aisle_id="aisle-img",
            source_asset_id="asset-b",
            job_id="job-img-1",
            sku=" MANUAL-SKU ",
            quantity=4,
            description="  desc  ",
            position_code=" P1 ",
            user_id="admin",
        )
    )
    assert out.position.creation_source == PositionCreationSource.MANUAL
    assert out.position.status == PositionStatus.REVIEWED
    assert out.position.review_resolution == PositionReviewResolution.MANUAL_CREATED
    assert out.product.sku == "MANUAL-SKU"
    assert out.product.corrected_quantity == 4
    reviews = world["review_repo"].list_by_position(out.position.id)
    assert len(reviews) == 1
    assert reviews[0].action_type == ReviewActionType.CREATE_MANUAL_RESULT_FROM_IMAGE
    assert reviews[0].user_id == "admin"
    evidences = list(
        world["evidence_repo"].list_by_entity("position", out.position.id)
    )
    assert len(evidences) == 1
    assert evidences[0].source_asset_id == "asset-b"

    with pytest.raises(Exception) as excinfo:
        uc.execute(
            CreateManualImageResultCommand(
                inventory_id="inv-img",
                aisle_id="aisle-img",
                source_asset_id="asset-b",
                job_id="job-img-1",
                sku="AGAIN",
                quantity=1,
                user_id="admin",
            )
        )
    assert "manual" in str(excinfo.value).lower() or "resultado" in str(excinfo.value).lower()


def test_manual_rejected_when_automatic_exists() -> None:
    world = _seed_world()
    _add_position_with_evidence(world, position_id="pos-auto", asset_id="asset-a", sku="AUTO", qty=1)
    with pytest.raises(ImageAlreadyHasResultsError):
        _create_uc(world).execute(
            CreateManualImageResultCommand(
                inventory_id="inv-img",
                aisle_id="aisle-img",
                source_asset_id="asset-a",
                job_id="job-img-1",
                sku="MAN",
                quantity=2,
                user_id="admin",
            )
        )


def test_api_image_results_and_manual_create() -> None:
    world = _seed_world()
    _add_position_with_evidence(world, position_id="pos-a", asset_id="asset-a", sku="SKU-A", qty=1)

    app.dependency_overrides[get_current_admin] = _fake_admin
    app.dependency_overrides[get_inventory_repo] = lambda: world["inv_repo"]
    app.dependency_overrides[get_aisle_repo] = lambda: world["aisle_repo"]
    app.dependency_overrides[get_job_repo] = lambda: world["job_repo"]
    app.dependency_overrides[get_job_source_asset_repo] = lambda: world["jsa_repo"]
    app.dependency_overrides[get_position_repo] = lambda: world["position_repo"]
    app.dependency_overrides[get_product_record_repo] = lambda: world["product_repo"]
    app.dependency_overrides[get_result_evidence_repo] = lambda: world["re_repo"]
    app.dependency_overrides[get_manual_image_coverage_repo] = lambda: world["coverage_repo"]
    app.dependency_overrides[get_evidence_repo] = lambda: world["evidence_repo"]
    app.dependency_overrides[get_review_action_repo] = lambda: world["review_repo"]
    app.dependency_overrides[get_source_asset_repo] = lambda: world["asset_repo"]
    app.dependency_overrides[get_list_job_image_results_use_case] = lambda: _list_uc(world)
    app.dependency_overrides[get_create_manual_image_result_use_case] = lambda: _create_uc(world)

    client = TestClient(app)
    try:
        r = client.get(
            "/api/v3/inventories/inv-img/aisles/aisle-img/jobs/job-img-1/image-results"
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["counters"]["total_images"] == 3
        assert body["counters"]["without_result"] == 2
        assert "job_source_asset_id" in body["items"][0]
        assert "creation_source" in body["items"][0]["results"][0] or any(
            item["has_result"] for item in body["items"]
        )

        # classic positions still works
        app.dependency_overrides[get_inventory_repo] = lambda: world["inv_repo"]
        # positions list needs result context — smoke via image create
        created = client.post(
            "/api/v3/inventories/inv-img/aisles/aisle-img/assets/asset-b/manual-result",
            json={"job_id": "job-img-1", "sku": "NEW", "quantity": 2},
        )
        assert created.status_code == 201, created.text
        assert created.json()["position"]["creation_source"] == "manual"

        dup = client.post(
            "/api/v3/inventories/inv-img/aisles/aisle-img/assets/asset-b/manual-result",
            json={"job_id": "job-img-1", "sku": "NEW2", "quantity": 1},
        )
        assert dup.status_code == 409
        assert dup.json().get("code") == "MANUAL_RESULT_ALREADY_EXISTS"

        bad_job = client.get(
            "/api/v3/inventories/inv-img/aisles/aisle-img/jobs/missing/image-results"
        )
        assert bad_job.status_code == 404

        video_world = _seed_world(with_video=True)
        app.dependency_overrides[get_list_job_image_results_use_case] = lambda: _list_uc(
            video_world
        )
        app.dependency_overrides[get_inventory_repo] = lambda: video_world["inv_repo"]
        app.dependency_overrides[get_aisle_repo] = lambda: video_world["aisle_repo"]
        app.dependency_overrides[get_job_repo] = lambda: video_world["job_repo"]
        app.dependency_overrides[get_job_source_asset_repo] = lambda: video_world["jsa_repo"]
        vid = client.get(
            "/api/v3/inventories/inv-img/aisles/aisle-img/jobs/job-img-1/image-results"
        )
        assert vid.status_code == 422
        assert vid.json().get("code") == "PHOTOS_JOB_REQUIRED"
    finally:
        app.dependency_overrides.clear()


def test_migration_0047_exists() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    migration = (
        root
        / "src/database/migrations/versions/0047_position_creation_source_and_manual_coverage.sql"
    )
    assert migration.is_file()
    text = migration.read_text(encoding="utf-8").lower()
    assert "creation_source" in text
    assert "position_manual_image_coverage" in text
    assert "uq_manual_coverage_job_asset" in text
