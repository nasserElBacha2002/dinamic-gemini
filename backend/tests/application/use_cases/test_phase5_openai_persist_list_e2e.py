"""Phase 5: OpenAI-shaped JSON → normalize → persist → list/detail aligned with multi-run resolver."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.application.services.result_context_resolver import ResultContextResolver
from src.application.use_cases.positions.get_position_detail import GetPositionDetailUseCase
from src.application.use_cases.positions.list_aisle_positions import (
    ListAislePositionsCommand,
    ListAislePositionsUseCase,
)
from src.application.use_cases.pipeline.persist_aisle_result import (
    PersistAisleResultCommand,
    PersistAisleResultUseCase,
)
from src.decision.count_status import assign_count_status
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.pipeline.hybrid_report_to_domain_adapter import (
    default_map_hybrid_report_to_domain,
)
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_evidence_repository import MemoryEvidenceRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.repositories.memory_product_record_repository import (
    MemoryProductRecordRepository,
)
from src.infrastructure.repositories.memory_review_action_repository import (
    MemoryReviewActionRepository,
)
from src.llm.normalization.entity_normalizer import normalize_llm_response
from src.parsing.global_analysis_parser import parse_entities
from src.reporting.hybrid_report import build_hybrid_report


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


def test_openai_normalize_persist_list_detail_job_metadata_and_slice_isolation() -> None:
    """E2E-style chain: canonical ``product_label_quantity`` → normalize → persist → two job slices."""
    now = datetime.now(timezone.utc)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    pos_repo = MemoryPositionRepository()
    product_repo = MemoryProductRecordRepository()
    evidence_repo = MemoryEvidenceRepository()
    job_repo = MemoryJobRepository()
    review_repo = MemoryReviewActionRepository()

    inv_repo.save(Inventory("inv-e2e", "E2E", InventoryStatus.IN_REVIEW, now, now))
    aisle_repo.save(
        Aisle(
            "aisle-e2e",
            "inv-e2e",
            "E",
            AisleStatus.PROCESSED,
            now,
            now,
            operational_job_id="job-openai-a",
        )
    )
    for jid in ("job-openai-a", "job-openai-b"):
        job_repo.save(
            Job(
                id=jid,
                target_type="aisle",
                target_id="aisle-e2e",
                job_type="process_aisle",
                status=JobStatus.SUCCEEDED,
                payload_json={},
                created_at=now,
                updated_at=now,
                provider_name="openai",
                model_name="gpt-4o-mini",
                prompt_key="global_v21",
                prompt_version="global_v21@v2.1",
            )
        )

    clock = FixedClock(now)
    persist = PersistAisleResultUseCase(
        position_repo=pos_repo,
        product_record_repo=product_repo,
        evidence_repo=evidence_repo,
        clock=clock,
        hybrid_mapper=default_map_hybrid_report_to_domain,
        aisle_repo=aisle_repo,
    )

    raw_a = {
        "total_entities_detected": 1,
        "entities": [
            {
                "entity_uid": "ea",
                "entity_type": "PALLET",
                "internal_code": "SKU-OPENAI-A",
                "product_label_quantity": 7,
                "confidence": 0.95,
                "count_status": "COUNTED",
                "evidence_path": "evidence/a.jpg",
            }
        ],
    }
    report_a = normalize_llm_response(raw_a, "openai")
    persist.execute(
        PersistAisleResultCommand(
            aisle_id="aisle-e2e",
            job_id="job-openai-a",
            report=report_a,
            run_dir=Path("/tmp/e2e-run-a"),
            run_id="run-a",
        )
    )

    raw_b = {
        "total_entities_detected": 1,
        "entities": [
            {
                "entity_uid": "eb",
                "entity_type": "PALLET",
                "internal_code": "SKU-OPENAI-B",
                "product_label_quantity": 3,
                "confidence": 0.9,
                "count_status": "COUNTED",
                "evidence_path": "evidence/b.jpg",
            }
        ],
    }
    report_b = normalize_llm_response(raw_b, "openai")
    persist.execute(
        PersistAisleResultCommand(
            aisle_id="aisle-e2e",
            job_id="job-openai-b",
            report=report_b,
            run_dir=Path("/tmp/e2e-run-b"),
            run_id="run-b",
        )
    )

    by_job = {p.job_id: p for p in pos_repo.list_by_aisles(["aisle-e2e"])}
    assert set(by_job) == {"job-openai-a", "job-openai-b"}

    resolver = ResultContextResolver(job_repo, pos_repo)
    list_uc = ListAislePositionsUseCase(
        inv_repo,
        aisle_repo,
        pos_repo,
        resolver,
        product_repo,
        positions_aisle_raw_cap=500,
    )

    default_list = list_uc.execute(
        ListAislePositionsCommand(
            inventory_id="inv-e2e", aisle_id="aisle-e2e", page=1, page_size=50
        )
    )
    assert default_list.result_context_source == "operational"
    assert default_list.resolved_job_id == "job-openai-a"
    assert len(default_list.positions) == 1
    pos_a = default_list.positions[0]
    prods_a = product_repo.list_by_position(pos_a.id)
    assert len(prods_a) == 1
    assert prods_a[0].sku == "SKU-OPENAI-A"
    assert prods_a[0].detected_quantity == 7

    list_b = list_uc.execute(
        ListAislePositionsCommand(
            inventory_id="inv-e2e",
            aisle_id="aisle-e2e",
            page=1,
            page_size=50,
            job_id="job-openai-b",
        )
    )
    assert list_b.result_context_source == "explicit"
    assert list_b.resolved_job_id == "job-openai-b"
    assert len(list_b.positions) == 1
    prods_b = product_repo.list_by_position(list_b.positions[0].id)
    assert prods_b[0].sku == "SKU-OPENAI-B"
    assert prods_b[0].detected_quantity == 3

    detail_uc = GetPositionDetailUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        position_repo=pos_repo,
        product_record_repo=product_repo,
        evidence_repo=evidence_repo,
        review_repo=review_repo,
        job_repo=job_repo,
        result_context_resolver=resolver,
        positions_aisle_raw_cap=500,
    )
    detail = detail_uc.execute("inv-e2e", "aisle-e2e", pos_a.id, explicit_job_id=None)
    assert detail.run_context.provider_name == "openai"
    assert detail.run_context.model_name == "gpt-4o-mini"
    assert detail.run_context.prompt_key == "global_v21"
    assert detail.run_context.prompt_version == "global_v21@v2.1"


def test_openai_pallet_unknown_sku_quantity_alias_hybrid_persist_list_explicit_job() -> None:
    """PALLET + ``quantity`` only (no internal_code): normalize → parse → report → persist → explicit GET /positions."""
    now = datetime.now(timezone.utc)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    pos_repo = MemoryPositionRepository()
    product_repo = MemoryProductRecordRepository()
    evidence_repo = MemoryEvidenceRepository()
    job_repo = MemoryJobRepository()

    inv_id, aisle_id, job_explicit = "inv-pallet-qty", "aisle-pallet-qty", "job-openai-pallet-qty"
    inv_repo.save(Inventory(inv_id, "PalletQty", InventoryStatus.IN_REVIEW, now, now))
    aisle_repo.save(
        Aisle(
            aisle_id,
            inv_id,
            "A",
            AisleStatus.PROCESSED,
            now,
            now,
            operational_job_id=None,
        )
    )
    job_repo.save(
        Job(
            id=job_explicit,
            target_type="aisle",
            target_id=aisle_id,
            job_type="process_aisle",
            status=JobStatus.SUCCEEDED,
            payload_json={},
            created_at=now,
            updated_at=now,
            provider_name="openai",
            model_name="gpt-4o-mini",
            prompt_key="global_v21",
            prompt_version="global_v21@v2.1",
        )
    )

    raw = {
        "total_entities_detected": 2,
        "entities": [
            {
                "entity_type": "PALLET",
                "model_entity_id": "det-1",
                "confidence": 0.91,
                "has_boxes": False,
                "source_image_id": "photo-1",
                "quantity": 2,
                "bbox": [0.1, 0.12, 0.45, 0.55],
            },
            {
                "entity_type": "PALLET",
                "model_entity_id": "det-2",
                "confidence": 0.82,
                "has_boxes": False,
                "source_image_id": "photo-2",
                "quantity": 1,
                "bbox": [0.2, 0.22, 0.55, 0.65],
            },
        ],
    }
    normalized = normalize_llm_response(raw, "openai")
    entities = parse_entities(normalized, job_id=job_explicit)
    for ent in entities:
        assign_count_status(ent)
    hybrid = build_hybrid_report("/tmp/photos_job.mp4", entities, frames_selected=1)

    clock = FixedClock(now)
    persist = PersistAisleResultUseCase(
        position_repo=pos_repo,
        product_record_repo=product_repo,
        evidence_repo=evidence_repo,
        clock=clock,
        hybrid_mapper=default_map_hybrid_report_to_domain,
        aisle_repo=aisle_repo,
    )
    persist.execute(
        PersistAisleResultCommand(
            aisle_id=aisle_id,
            job_id=job_explicit,
            report=hybrid,
            run_dir=Path("/tmp/pallet-qty-run"),
            run_id="run-pq",
        )
    )

    resolver = ResultContextResolver(job_repo, pos_repo)
    list_uc = ListAislePositionsUseCase(
        inv_repo,
        aisle_repo,
        pos_repo,
        resolver,
        product_repo,
        positions_aisle_raw_cap=500,
    )
    listed = list_uc.execute(
        ListAislePositionsCommand(
            inventory_id=inv_id,
            aisle_id=aisle_id,
            page=1,
            page_size=50,
            job_id=job_explicit,
            consolidate_by_sku=False,
            sort_by="photo_sequence",
        )
    )
    assert listed.result_context_source == "explicit"
    assert listed.resolved_job_id == job_explicit
    assert listed.total_items == 2
    assert len(listed.positions) == 2
    for p in listed.positions:
        prods = product_repo.list_by_position(p.id)
        assert len(prods) == 1
        assert prods[0].sku == "UNKNOWN"
        assert prods[0].detected_quantity >= 1
        ds = p.detected_summary_json or {}
        assert ds.get("model_entity_id") in ("det-1", "det-2")
        assert "extent_bbox" in ds or "product_label_bbox" in ds
