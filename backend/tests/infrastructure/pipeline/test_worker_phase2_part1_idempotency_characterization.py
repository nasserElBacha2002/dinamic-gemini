"""Phase 2 Part 1 — result ownership and idempotency characterization (P2-T001–T003)."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from src.application.services.export_inventory_collector import ExportInventoryCollector
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.services.result_context_resolver import ResultContextResolver
from src.application.use_cases.pipeline.recompute_consolidated_counts import (
    RecomputeConsolidatedCountsCommand,
)
from src.application.use_cases.positions.list_aisle_positions import (
    ListAislePositionsCommand,
    ListAislePositionsUseCase,
)
from src.domain.aisle.entities import AisleStatus
from src.domain.inventory.entities import InventoryProcessingMode
from src.domain.jobs.entities import JobStatus
from src.infrastructure.pipeline.v3_job_execution_state import V3JobExecutionStateService
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from tests.support.worker_phase1.doubles import FailOnNthSavePositionRepository
from tests.support.worker_phase1.duplicate_detection import (
    duplicate_evidence_by_job_path,
    duplicate_final_counts_by_sku,
    duplicate_normalized_labels_by_sku,
    duplicate_positions_by_job_entity_uid,
    duplicate_products_by_job_sku,
    duplicate_raw_labels_by_source_reference,
    entity_uid_from_position,
)
from tests.support.worker_phase1.executor_harness import (
    ExecutorHarness,
    FixedClock,
    make_entity_hybrid_report,
    make_two_entity_hybrid_report,
)


def _standard_two_entity_report() -> dict:
    return make_two_entity_hybrid_report()


def _abc_report(
    *,
    qty_a: int = 2,
    qty_b: int = 4,
    include_b: bool = True,
    include_c: bool = False,
    qty_c: int = 5,
) -> dict:
    entities = [
        {
            "entity_uid": "e1",
            "entity_type": "PALLET",
            "model_entity_id": "E1",
            "internal_code": "SKU-A",
            "final_quantity": qty_a,
            "product_label_quantity": qty_a,
            "confidence": 0.9,
            "count_status": "COUNTED",
            "evidence_path": "evidence/crop_a.jpg",
            "source_image_id": "asset-1",
        },
    ]
    if include_b:
        entities.append(
            {
                "entity_uid": "e2",
                "entity_type": "PALLET",
                "model_entity_id": "E2",
                "internal_code": "SKU-B",
                "final_quantity": qty_b,
                "product_label_quantity": qty_b,
                "confidence": 0.85,
                "count_status": "COUNTED",
                "evidence_path": "evidence/crop_b.jpg",
                "source_image_id": "asset-2",
            }
        )
    if include_c:
        entities.append(
            {
                "entity_uid": "e3",
                "entity_type": "PALLET",
                "model_entity_id": "E3",
                "internal_code": "SKU-C",
                "final_quantity": qty_c,
                "product_label_quantity": qty_c,
                "confidence": 0.8,
                "count_status": "COUNTED",
                "evidence_path": "evidence/crop_c.jpg",
                "source_image_id": "asset-1",
            }
        )
    return make_entity_hybrid_report(entities)


# --- P2-T001 ------------------------------------------------------------------


def test_p2_t001_same_job_identical_persist_is_non_idempotent(tmp_path: Path) -> None:
    """P2-T001: second identical persist duplicates rows (NON_IDEMPOTENT)."""
    harness = ExecutorHarness.build(tmp_path, job_id="job-p2-t001")
    report = _standard_two_entity_report()
    cmd_report = report

    harness.persist_report(cmd_report, job_id="job-p2-t001")
    snap1 = harness.snapshot_job_scope("job-p2-t001")

    harness.persist_report(cmd_report, job_id="job-p2-t001")
    snap2 = harness.snapshot_job_scope("job-p2-t001")

    assert snap1.position_count == 2
    assert snap2.position_count == 4
    assert len(set(snap1.position_ids) & set(snap2.position_ids)) == 2
    assert len(set(snap2.position_ids) - set(snap1.position_ids)) == 2

    all_positions = harness.positions_for_job("job-p2-t001")
    dup_pos = duplicate_positions_by_job_entity_uid(all_positions)
    assert ("job-p2-t001", "e1") in dup_pos
    assert dup_pos[("job-p2-t001", "e1")] == 2
    assert dup_pos[("job-p2-t001", "e2")] == 2

    pos_map = harness.position_job_id_map("job-p2-t001")
    all_products = [
        p for pos in all_positions for p in harness.product_repo.list_by_position(pos.id)
    ]
    dup_prod = duplicate_products_by_job_sku(all_products, position_job_id=pos_map)
    assert dup_prod[("job-p2-t001", "SKU-ONE")] == 2
    assert dup_prod[("job-p2-t001", "SKU-TWO")] == 2

    all_evidence = harness.evidence_for_job("job-p2-t001")
    dup_ev = duplicate_evidence_by_job_path(all_evidence, position_job_id=pos_map)
    assert len(dup_ev) == 2
    assert all(count == 2 for count in dup_ev.values())

    raw_labels = harness.raw_labels_for_job("job-p2-t001")
    assert len(raw_labels) == 4
    raw_dup = duplicate_raw_labels_by_source_reference(raw_labels)
    assert raw_dup[("job-p2-t001", "e1")] == 2
    assert raw_dup[("job-p2-t001", "e2")] == 2

    norm_labels = harness.normalized_labels_for_job("job-p2-t001")
    assert len(norm_labels) == 4
    norm_dup = duplicate_normalized_labels_by_sku(norm_labels)
    assert norm_dup[("job-p2-t001", "SKU-ONE")] == 2
    assert norm_dup[("job-p2-t001", "SKU-TWO")] == 2

    finals = harness.final_counts_for_job("job-p2-t001")
    assert len(finals) == 4
    final_dup = duplicate_final_counts_by_sku(finals)
    assert final_dup[("job-p2-t001", "SKU-ONE")] == 2
    assert final_dup[("job-p2-t001", "SKU-TWO")] == 2


# --- P2-T002 ------------------------------------------------------------------


def test_p2_t002_same_job_changed_report_appends_stale_and_new_rows(tmp_path: Path) -> None:
    """P2-T002: changed report on same job_id appends; entity A duplicated; B stale; C added."""
    harness = ExecutorHarness.build(tmp_path, job_id="job-p2-t002")
    first = _abc_report(qty_a=2, qty_b=4, include_b=True, include_c=False)
    second = _abc_report(qty_a=99, qty_b=4, include_b=False, include_c=True, qty_c=5)

    harness.persist_report(first, job_id="job-p2-t002")
    harness.persist_report(second, job_id="job-p2-t002")

    positions = harness.positions_for_job("job-p2-t002")
    by_uid: dict[str, list] = {}
    for p in positions:
        uid = entity_uid_from_position(p) or ""
        by_uid.setdefault(uid, []).append(p)

    assert len(positions) == 4
    assert len(by_uid["e1"]) == 2
    assert len(by_uid["e2"]) == 1
    assert len(by_uid["e3"]) == 1

    qtys_e1 = sorted(
        (p.detected_summary_json or {}).get("final_quantity") for p in by_uid["e1"]
    )
    assert qtys_e1 == [2, 99]

    stale_b = by_uid["e2"][0]
    assert (stale_b.detected_summary_json or {}).get("final_quantity") == 4

    new_c = by_uid["e3"][0]
    assert (new_c.detected_summary_json or {}).get("final_quantity") == 5

    assert duplicate_positions_by_job_entity_uid(positions)[("job-p2-t002", "e1")] == 2

    raw_labels = harness.raw_labels_for_job("job-p2-t002")
    assert len(raw_labels) == 4
    raw_entity_counts = Counter((lb.job_id, lb.source_reference) for lb in raw_labels)
    assert raw_entity_counts[("job-p2-t002", "e1")] == 2
    assert raw_entity_counts[("job-p2-t002", "e2")] == 1
    assert raw_entity_counts[("job-p2-t002", "e3")] == 1
    assert duplicate_raw_labels_by_source_reference(raw_labels)[("job-p2-t002", "e1")] == 2

    norm_labels = harness.normalized_labels_for_job("job-p2-t002")
    assert len(norm_labels) == 4

    finals = harness.final_counts_for_job("job-p2-t002")
    assert len(finals) == 4


# --- P2-T003 ------------------------------------------------------------------


def test_p2_t003_partial_fail_then_success_retry_isolates_by_job_id(tmp_path: Path) -> None:
    """P2-T003: failed partial job rows retained; success job operational; readers isolated."""
    inner_pos = MemoryPositionRepository()
    failing_pos = FailOnNthSavePositionRepository(inner_pos, fail_on_call=2)

    harness_fail = ExecutorHarness.build(
        tmp_path,
        job_id="job-failed",
        position_repo=failing_pos,
        processing_mode=InventoryProcessingMode.PRODUCTION,
    )
    fail_report = _abc_report(qty_a=99, qty_b=99, include_b=True, include_c=False)

    with pytest.raises(RuntimeError, match="simulated position save failure"):
        harness_fail.persist_report(fail_report, job_id="job-failed")

    snap_failed = harness_fail.snapshot_job_scope("job-failed")
    assert snap_failed.position_count == 1
    assert snap_failed.raw_label_count == 0

    aisle = harness_fail.aisle_repo.get_by_id(harness_fail.aisle_id)
    assert aisle is not None
    aisle.status = AisleStatus.QUEUED
    aisle.operational_job_id = None
    harness_fail.aisle_repo.save(aisle)

    harness_ok = ExecutorHarness.build(
        tmp_path,
        job_id="job-success",
        job_status=JobStatus.STARTING,
        aisle_status=AisleStatus.QUEUED,
        processing_mode=InventoryProcessingMode.PRODUCTION,
        job_repo=harness_fail.job_repo,
        aisle_repo=harness_fail.aisle_repo,
        inventory_repo=harness_fail.inventory_repo,
        position_repo=inner_pos,
        product_repo=harness_fail.product_repo,
        evidence_repo=harness_fail.evidence_repo,
        raw_repo=harness_fail.raw_repo,
        norm_repo=harness_fail.norm_repo,
        final_repo=harness_fail.final_repo,
    )
    success_report = _abc_report(qty_a=5, qty_b=5, include_b=True, include_c=False)
    harness_ok.persist_report(success_report, job_id="job-success")

    state_svc = V3JobExecutionStateService(
        job_repo=harness_ok.job_repo,
        aisle_repo=harness_ok.aisle_repo,
        inventory_repo=harness_ok.inventory_repo,
        inventory_status_reconciler=InventoryStatusReconciler(
            harness_ok.inventory_repo,
            harness_ok.aisle_repo,
            FixedClock(harness_ok.now),
        ),
        clock=FixedClock(harness_ok.now),
    )
    aisle_for_success = harness_ok.aisle_repo.get_by_id(harness_ok.aisle_id)
    assert aisle_for_success is not None
    state_svc.mark_success(
        "job-success",
        aisle_for_success,
        report_path=tmp_path / "hybrid_report.json",
        run_metadata={"provider": "test"},
    )

    assert harness_ok.operational_job_id() == "job-success"

    snap_success = harness_ok.snapshot_job_scope("job-success")
    assert snap_success.position_count == 2
    assert snap_success.raw_label_count >= 1
    assert not duplicate_positions_by_job_entity_uid(harness_ok.positions_for_job("job-success"))

    failed_positions = harness_ok.positions_for_job("job-failed")
    success_positions = harness_ok.positions_for_job("job-success")
    assert len(failed_positions) == 1
    assert len(success_positions) == 2
    assert (failed_positions[0].detected_summary_json or {}).get("final_quantity") == 99
    assert all(
        (p.detected_summary_json or {}).get("final_quantity") == 5 for p in success_positions
    )

    resolver = ResultContextResolver(harness_ok.job_repo)
    list_uc = ListAislePositionsUseCase(
        harness_ok.inventory_repo,
        harness_ok.aisle_repo,
        harness_ok.position_repo,
        resolver,
        harness_ok.product_repo,
        positions_aisle_raw_cap=500,
    )
    list_result = list_uc.execute(
        ListAislePositionsCommand(
            inventory_id=harness_ok.inventory_id,
            aisle_id=harness_ok.aisle_id,
            page=1,
            page_size=50,
        )
    )
    assert list_result.resolved_job_id == "job-success"
    assert {p.id for p in list_result.positions} == {p.id for p in success_positions}
    assert not {p.id for p in list_result.positions} & {p.id for p in failed_positions}

    export_collector = ExportInventoryCollector(
        harness_ok.inventory_repo,
        harness_ok.aisle_repo,
        harness_ok.position_repo,
        harness_ok.product_repo,
        resolver,
    )
    export_data = export_collector.collect_aisle(
        harness_ok.inventory_id,
        harness_ok.aisle_id,
    )
    bundle = export_data.aisle_bundles[0]
    assert bundle.job_id_for_slice == "job-success"
    export_qtys = sorted(
        int(row.internal_row.get("final_quantity") or 0) for row in bundle.rows
    )
    assert export_qtys == [5, 5]
    assert 99 not in export_qtys

    recompute_result = harness_ok.recompute_uc.execute(
        RecomputeConsolidatedCountsCommand(
            inventory_id=harness_ok.inventory_id,
            aisle_id=harness_ok.aisle_id,
            apply_to_product_records=False,
            job_scope="job-success",
        )
    )
    assert recompute_result.raw_count >= 1
    success_raw = harness_ok.raw_labels_for_job("job-success")
    failed_raw = harness_ok.raw_labels_for_job("job-failed")
    assert len(failed_raw) == 0
    assert len(success_raw) >= 1

    all_scope_recompute = harness_ok.recompute_uc.execute(
        RecomputeConsolidatedCountsCommand(
            inventory_id=harness_ok.inventory_id,
            aisle_id=harness_ok.aisle_id,
            apply_to_product_records=False,
            job_scope="all",
        )
    )
    assert all_scope_recompute.raw_count >= len(success_raw)
