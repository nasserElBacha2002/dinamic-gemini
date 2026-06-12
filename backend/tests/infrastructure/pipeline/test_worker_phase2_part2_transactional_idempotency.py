"""Phase 2 Part 2 — transactional idempotent persistence by job scope."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.services.export_inventory_collector import ExportInventoryCollector
from src.application.services.result_context_resolver import ResultContextResolver
from src.application.use_cases.aisles.retry_aisle_job import RetryAisleJobCommand
from src.application.use_cases.pipeline.persist_aisle_result import PersistAisleResultCommand
from src.application.use_cases.positions.list_aisle_positions import (
    ListAislePositionsCommand,
    ListAislePositionsUseCase,
)
from src.domain.jobs.entities import JobStatus
from tests.support.worker_phase1.doubles import ArtifactUploadSpy, FailOnNthSavePositionRepository
from tests.support.worker_phase2.recompute_doubles import FailingJobScopedRecomputeFactory
from tests.support.worker_phase2.uow_doubles import HookingMemoryJobResultUnitOfWorkFactory
from tests.support.worker_phase1.executor_harness import (
    ExecutorHarness,
    make_entity_hybrid_report,
    make_two_entity_hybrid_report,
)
from tests.support.worker_phase2.duplicate_detection import (
    duplicate_positions_by_job_entity_uid,
    entity_uid_from_position,
    repeated_final_counts_by_job_sku,
)
from tests.support.worker_phase2.job_scope_inspection import assert_no_row_id_overlap
from tests.support.worker_phase2.retry_flow import build_retry_flow_services


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


def _single_entity_report(
    *,
    entity_uid: str,
    sku: str,
    quantity: int,
    evidence_path: str,
) -> dict:
    return make_entity_hybrid_report(
        [
            {
                "entity_uid": entity_uid,
                "entity_type": "PALLET",
                "internal_code": sku,
                "final_quantity": quantity,
                "product_label_quantity": quantity,
                "confidence": 0.9,
                "count_status": "COUNTED",
                "evidence_path": evidence_path,
                "source_image_id": "asset-1",
            }
        ]
    )


def test_p2_p2_t001_identical_same_job_persist_is_idempotent(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path, job_id="job-idem")
    report = make_two_entity_hybrid_report()
    harness.persist_report(report, job_id="job-idem")
    snap1 = harness.snapshot_job_scope("job-idem")
    harness.persist_report(report, job_id="job-idem")
    snap2 = harness.snapshot_job_scope("job-idem")
    assert snap1.position_count == 2
    assert snap2.position_count == 2
    assert snap1.product_count == snap2.product_count == 2
    assert duplicate_positions_by_job_entity_uid(harness.positions_for_job("job-idem")) == {}
    assert repeated_final_counts_by_job_sku(harness.final_counts_for_job("job-idem")) == {}


def test_p2_p2_t002_changed_same_job_report_replaces_snapshot(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path, job_id="job-replace")
    harness.persist_report(_abc_report(), job_id="job-replace")
    harness.persist_report(
        _abc_report(qty_a=99, include_b=False, include_c=True, qty_c=5),
        job_id="job-replace",
    )
    positions = harness.positions_for_job("job-replace")
    by_uid = {entity_uid_from_position(p): p for p in positions}
    assert len(positions) == 2
    assert set(by_uid) == {"e1", "e3"}
    assert (by_uid["e1"].detected_summary_json or {}).get("final_quantity") == 99
    assert (by_uid["e3"].detected_summary_json or {}).get("final_quantity") == 5
    skus = {p.sku for p in harness.products_for_job("job-replace")}
    assert skus == {"SKU-A", "SKU-C"}
    assert len(harness.raw_labels_for_job("job-replace")) == 2
    assert {n.canonical_sku for n in harness.normalized_labels_for_job("job-replace")} == {
        "SKU-A",
        "SKU-C",
    }
    assert "SKU-B" not in {f.sku for f in harness.final_counts_for_job("job-replace")}


def test_p2_p2_t003_repersist_does_not_affect_other_job(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path, job_id="job-one")
    harness.persist_report(_abc_report(qty_a=1, qty_b=2), job_id="job-one")
    snap_one_before = harness.snapshot_job_scope("job-one")
    harness.persist_report(
        _abc_report(qty_a=50, include_b=False, include_c=True, qty_c=7),
        job_id="job-two",
    )
    snap_one_after = harness.snapshot_job_scope("job-one")
    snap_two = harness.snapshot_job_scope("job-two")
    assert snap_one_before == snap_one_after
    assert snap_two.position_count == 2
    assert snap_one_after.position_count == 2


def test_p2_p2_t004_rollback_after_deletion_restores_prior_snapshot(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path, job_id="job-rb-del")
    harness.persist_report(_abc_report(), job_id="job-rb-del")
    before = harness.snapshot_job_scope("job-rb-del")

    def _fail() -> None:
        raise RuntimeError("fail after delete")

    persist = harness.make_persist_use_case(
        job_result_uow_factory=HookingMemoryJobResultUnitOfWorkFactory(
            after_delete_hook=_fail
        ),
    )
    with pytest.raises(RuntimeError, match="fail after delete"):
        persist.execute(
            PersistAisleResultCommand(
                aisle_id=harness.aisle_id,
                job_id="job-rb-del",
                report=_abc_report(qty_a=99, include_b=False, include_c=True),
                run_dir=tmp_path,
            )
        )
    assert harness.snapshot_job_scope("job-rb-del") == before


def test_p2_p2_t005_rollback_during_entity_persist_restores_snapshot(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path, job_id="job-rb-pos")
    harness.persist_report(_abc_report(), job_id="job-rb-pos")
    before = harness.snapshot_job_scope("job-rb-pos")
    failing = FailOnNthSavePositionRepository(harness.position_repo, fail_on_call=1)
    persist = harness.make_persist_use_case(position_repo=failing)
    with pytest.raises(RuntimeError, match="simulated position save failure"):
        persist.execute(
            PersistAisleResultCommand(
                aisle_id=harness.aisle_id,
                job_id="job-rb-pos",
                report=_abc_report(qty_a=88, include_b=False, include_c=True),
                run_dir=tmp_path,
            )
        )
    after = harness.snapshot_job_scope("job-rb-pos")
    assert after == before


def test_p2_p2_t006_rollback_during_recompute_restores_snapshot(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path, job_id="job-rb-rec")
    harness.persist_report(_abc_report(), job_id="job-rb-rec")
    before = harness.snapshot_job_scope("job-rb-rec")
    persist = harness.make_persist_use_case(
        job_scoped_recompute_factory=FailingJobScopedRecomputeFactory()
    )
    with pytest.raises(RuntimeError, match="simulated recompute failure"):
        persist.execute(
            PersistAisleResultCommand(
                aisle_id=harness.aisle_id,
                job_id="job-rb-rec",
                report=_abc_report(qty_a=77, include_b=False, include_c=True),
                run_dir=tmp_path,
            )
        )
    assert harness.snapshot_job_scope("job-rb-rec") == before


def test_p2_p2_t007_retry_job_isolated_after_transactional_persist(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path, job_id="job-failed")
    failing_factory = FailingJobScopedRecomputeFactory()
    harness.run_with_mock_pipeline(
        harness.make_executor(job_scoped_recompute_factory=failing_factory),
        report=_single_entity_report(
            entity_uid="e-failed",
            sku="SKU-FAILED",
            quantity=99,
            evidence_path="evidence/failed.jpg",
        ),
    )
    assert harness.job_repo.get_by_id("job-failed").status == JobStatus.FAILED
    failed_snap = harness.snapshot_job_scope("job-failed")
    assert failed_snap.position_count == 0

    retry_job = build_retry_flow_services(harness).retry_use_case.execute(
        RetryAisleJobCommand(harness.inventory_id, harness.aisle_id, "job-failed")
    )
    retry_harness = ExecutorHarness.build(
        tmp_path,
        job_id=retry_job.id,
        job_repo=harness.job_repo,
        aisle_repo=harness.aisle_repo,
        inventory_repo=harness.inventory_repo,
        position_repo=harness.position_repo,
        product_repo=harness.product_repo,
        evidence_repo=harness.evidence_repo,
        raw_repo=harness.raw_repo,
        norm_repo=harness.norm_repo,
        final_repo=harness.final_repo,
    )
    retry_harness.run_with_mock_pipeline(
        retry_harness.make_executor(artifact_store=ArtifactUploadSpy()),
        report=_single_entity_report(
            entity_uid="e-success",
            sku="SKU-SUCCESS",
            quantity=5,
            evidence_path="evidence/success.jpg",
        ),
    )
    assert retry_harness.job_repo.get_by_id(retry_job.id).status == JobStatus.SUCCEEDED
    assert retry_harness.aisle_repo.get_by_id(retry_harness.aisle_id).operational_job_id == retry_job.id
    assert harness.snapshot_job_scope("job-failed") == failed_snap
    assert retry_harness.snapshot_job_scope(retry_job.id).position_count == 1
    assert_no_row_id_overlap(
        failed_snap.position_ids,
        retry_harness.snapshot_job_scope(retry_job.id).position_ids,
    )


def test_p2_p2_t008_operational_readers_resolve_success_job_only(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path, job_id="job-f")
    failing_factory = FailingJobScopedRecomputeFactory()
    harness.run_with_mock_pipeline(
        harness.make_executor(job_scoped_recompute_factory=failing_factory),
        report=_single_entity_report(
            entity_uid="e-f",
            sku="SKU-FAILED",
            quantity=99,
            evidence_path="evidence/failed.jpg",
        ),
    )
    retry_job = build_retry_flow_services(harness).retry_use_case.execute(
        RetryAisleJobCommand(harness.inventory_id, harness.aisle_id, "job-f")
    )
    rh = ExecutorHarness.build(
        tmp_path,
        job_id=retry_job.id,
        job_repo=harness.job_repo,
        aisle_repo=harness.aisle_repo,
        inventory_repo=harness.inventory_repo,
        position_repo=harness.position_repo,
        product_repo=harness.product_repo,
        evidence_repo=harness.evidence_repo,
        raw_repo=harness.raw_repo,
        norm_repo=harness.norm_repo,
        final_repo=harness.final_repo,
    )
    rh.run_with_mock_pipeline(
        rh.make_executor(artifact_store=ArtifactUploadSpy()),
        report=_single_entity_report(
            entity_uid="e-s",
            sku="SKU-SUCCESS",
            quantity=5,
            evidence_path="evidence/success.jpg",
        ),
    )
    resolver = ResultContextResolver(rh.job_repo)
    list_result = ListAislePositionsUseCase(
        rh.inventory_repo,
        rh.aisle_repo,
        rh.position_repo,
        resolver,
        rh.product_repo,
        positions_aisle_raw_cap=500,
    ).execute(
        ListAislePositionsCommand(
            inventory_id=rh.inventory_id, aisle_id=rh.aisle_id, page=1, page_size=50
        )
    )
    assert list_result.resolved_job_id == retry_job.id
    bundle = ExportInventoryCollector(
        rh.inventory_repo, rh.aisle_repo, rh.position_repo, rh.product_repo, resolver
    ).collect_aisle(rh.inventory_id, rh.aisle_id).aisle_bundles[0]
    assert bundle.job_id_for_slice == retry_job.id
    assert {row.internal_row.get("product_sku") for row in bundle.rows} == {"SKU-SUCCESS"}


def test_p2_p2_t009_persist_rejects_broad_job_id(tmp_path: Path) -> None:
    harness = ExecutorHarness.build(tmp_path)
    with pytest.raises(ValueError, match="rejects broad"):
        harness.make_persist_use_case().execute(
            PersistAisleResultCommand(
                aisle_id=harness.aisle_id,
                job_id="all",
                report=make_two_entity_hybrid_report(),
                run_dir=tmp_path,
            )
        )
