"""Phase 1 multi-run persistence: job-scoped rows and repository isolation (memory)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.application.ports.repositories import JOB_ID_FILTER_UNSET
from src.application.services.final_count_builder import FinalCountBuilder
from src.application.services.label_normalization import LabelNormalizationService
from src.application.use_cases.pipeline.persist_aisle_result import (
    PersistAisleResultCommand,
)
from src.application.use_cases.pipeline.recompute_consolidated_counts import (
    RecomputeConsolidatedCountsCommand,
    RecomputeConsolidatedCountsUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.labels.entities import RawLabel
from src.domain.labels.merge import MergeRuleEngine
from src.domain.positions.entities import Position, PositionStatus
from src.infrastructure.pipeline.v3_report_mapper import map_hybrid_report_to_domain
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_evidence_repository import MemoryEvidenceRepository
from src.infrastructure.repositories.memory_final_count_repository import MemoryFinalCountRepository
from src.infrastructure.repositories.memory_normalized_label_repository import (
    MemoryNormalizedLabelRepository,
)
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.repositories.memory_product_record_repository import (
    MemoryProductRecordRepository,
)
from src.infrastructure.repositories.memory_raw_label_repository import MemoryRawLabelRepository


def _aisle(inv_id: str, aisle_id: str) -> Aisle:
    now = datetime.now(timezone.utc)
    return Aisle(
        id=aisle_id,
        inventory_id=inv_id,
        code="A1",
        status=AisleStatus.PROCESSING,
        created_at=now,
        updated_at=now,
    )


def _report_one_entity() -> dict:
    return {
        "entities": [
            {
                "entity_uid": "e1",
                "entity_type": "PALLET",
                "internal_code": "SKU-A",
                "count_status": "COUNTED",
                "confidence": 0.9,
                "evidence_path": "crop1.jpg",
                "final_quantity": 3,
            }
        ]
    }


@pytest.fixture
def memory_stack():
    pos = MemoryPositionRepository()
    prod = MemoryProductRecordRepository()
    ev = MemoryEvidenceRepository()
    raw = MemoryRawLabelRepository()
    norm = MemoryNormalizedLabelRepository()
    final = MemoryFinalCountRepository()
    aisle_repo = MemoryAisleRepository()
    inv_id, aisle_id = "inv-mr", "aisle-mr"
    aisle_repo.save(_aisle(inv_id, aisle_id))
    clock = MagicMock()
    clock.now.return_value = datetime.now(timezone.utc)
    from tests.support.worker_phase2.persist_builders import build_persist_aisle_result_use_case

    persist = build_persist_aisle_result_use_case(
        position_repo=pos,
        product_record_repo=prod,
        evidence_repo=ev,
        clock=clock,
        aisle_repo=aisle_repo,
        raw_label_repo=raw,
        normalized_label_repo=norm,
        final_count_repo=final,
    )
    recompute = RecomputeConsolidatedCountsUseCase(
        raw_label_repo=raw,
        normalized_label_repo=norm,
        final_count_repo=final,
        product_record_repo=prod,
        position_repo=pos,
        normalization_service=LabelNormalizationService(merge_rule_engine=MergeRuleEngine()),
        final_count_builder=FinalCountBuilder(),
    )
    return {
        "position_repo": pos,
        "raw_repo": raw,
        "norm_repo": norm,
        "final_repo": final,
        "aisle_repo": aisle_repo,
        "persist": persist,
        "recompute": recompute,
        "inv_id": inv_id,
        "aisle_id": aisle_id,
        "clock": clock,
    }


def test_migration_file_0010_exists_and_mentions_job_scoping():
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    mig = root / "src/database/migrations/versions/0010_multi_run_job_scoping.sql"
    assert mig.is_file(), "0010_multi_run_job_scoping.sql must exist"
    text = mig.read_text()
    assert "positions" in text and "job_id" in text
    assert "provider_name" in text


def test_persist_two_jobs_same_aisle_isolated_positions(memory_stack):
    s = memory_stack
    inv_id, aisle_id = s["inv_id"], s["aisle_id"]
    job_a, job_b = str(uuid4()), str(uuid4())
    run_dir = Path("/tmp")
    now = datetime.now(timezone.utc)
    s["clock"].now.return_value = now

    s["persist"].execute(
        PersistAisleResultCommand(
            aisle_id=aisle_id,
            job_id=job_a,
            report=_report_one_entity(),
            run_dir=run_dir,
            run_id="r1",
        )
    )
    assert s["aisle_repo"].get_by_id(aisle_id).operational_job_id is None
    s["persist"].execute(
        PersistAisleResultCommand(
            aisle_id=aisle_id,
            job_id=job_b,
            report=_report_one_entity(),
            run_dir=run_dir,
            run_id="r2",
        )
    )

    all_pos = list(
        s["position_repo"].list_by_aisle(
            aisle_id, page=1, page_size=100, job_id=JOB_ID_FILTER_UNSET
        )
    )
    assert len(all_pos) == 2
    ja = list(s["position_repo"].list_by_aisle(aisle_id, page=1, page_size=100, job_id=job_a))
    jb = list(s["position_repo"].list_by_aisle(aisle_id, page=1, page_size=100, job_id=job_b))
    assert len(ja) == 1 and len(jb) == 1
    assert ja[0].id != jb[0].id
    assert ja[0].job_id == job_a and jb[0].job_id == job_b

    legacy = list(s["position_repo"].list_by_aisle(aisle_id, page=1, page_size=100, job_id=None))
    assert len(legacy) == 0

    raws_a = list(s["raw_repo"].list_for_scope(inv_id, aisle_id, job_id=job_a))
    raws_b = list(s["raw_repo"].list_for_scope(inv_id, aisle_id, job_id=job_b))
    assert len(raws_a) == 1 and len(raws_b) == 1
    assert raws_a[0].position_id == ja[0].id

    finals_a = list(s["final_repo"].list_for_scope(inv_id, aisle_id, job_id=job_a))
    assert len(finals_a) >= 1
    assert finals_a[0].job_id == job_a


def test_recompute_legacy_null_scope_does_not_see_job_scoped_raw_labels(memory_stack):
    s = memory_stack
    inv_id, aisle_id = s["inv_id"], s["aisle_id"]
    job_id = str(uuid4())
    s["persist"].execute(
        PersistAisleResultCommand(
            aisle_id=aisle_id,
            job_id=job_id,
            report=_report_one_entity(),
            run_dir=Path("/tmp"),
            run_id="r1",
        )
    )
    uc: RecomputeConsolidatedCountsUseCase = s["recompute"]
    res = uc.execute(
        RecomputeConsolidatedCountsCommand(
            inventory_id=inv_id,
            aisle_id=aisle_id,
            apply_to_product_records=False,
            job_scope="legacy_null",
        )
    )
    assert res.raw_count == 0


def test_map_hybrid_report_sets_job_id_on_position_and_raw():
    now = datetime.now(timezone.utc)
    jid = str(uuid4())
    m = map_hybrid_report_to_domain(
        aisle_id="a1",
        report=_report_one_entity(),
        run_dir=Path("."),
        run_id="run",
        job_id=jid,
        now=now,
        inventory_id="inv1",
    )
    assert m.positions[0].job_id == jid
    assert m.raw_labels[0].job_id == jid


def test_legacy_null_raw_label_list_and_recompute(memory_stack):
    s = memory_stack
    inv_id, aisle_id = s["inv_id"], s["aisle_id"]
    now = datetime.now(timezone.utc)
    pos = Position(
        id=str(uuid4()),
        aisle_id=aisle_id,
        status=PositionStatus.DETECTED,
        confidence=0.5,
        needs_review=True,
        primary_evidence_id=None,
        created_at=now,
        updated_at=now,
        job_id=None,
    )
    s["position_repo"].save(pos)
    rl = RawLabel(
        id=str(uuid4()),
        inventory_id=inv_id,
        aisle_id=aisle_id,
        position_id=pos.id,
        evidence_id=None,
        group_key="g",
        provider="p",
        source_type="s",
        source_reference=None,
        sku_raw="x",
        sku_candidate="x",
        product_name_raw=None,
        detected_text=None,
        confidence=0.5,
        metadata={},
        created_at=now,
        job_id=None,
    )
    s["raw_repo"].save_many([rl])

    listed = list(s["raw_repo"].list_for_scope(inv_id, aisle_id, job_id=None))
    assert len(listed) == 1

    res = s["recompute"].execute(
        RecomputeConsolidatedCountsCommand(
            inventory_id=inv_id,
            aisle_id=aisle_id,
            apply_to_product_records=False,
            job_scope="legacy_null",
        )
    )
    assert res.raw_count == 1
