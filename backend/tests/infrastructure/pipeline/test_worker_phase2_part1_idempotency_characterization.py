"""Phase 2 Part 1 — result ownership and idempotency characterization."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from src.application.services.export_inventory_collector import ExportInventoryCollector
from src.application.services.result_context_resolver import ResultContextResolver
from src.application.use_cases.aisles.retry_aisle_job import RetryAisleJobCommand
from src.application.use_cases.pipeline.recompute_consolidated_counts import (
    RecomputeConsolidatedCountsCommand,
)
from src.application.use_cases.positions.list_aisle_positions import (
    ListAislePositionsCommand,
    ListAislePositionsUseCase,
)
from src.domain.aisle.entities import AisleStatus
from src.domain.inventory.entities import InventoryProcessingMode, InventoryStatus
from src.domain.jobs.entities import JobStatus
from src.domain.labels.entities import RawLabel
from tests.support.worker_phase1.doubles import ArtifactUploadSpy
from tests.support.worker_phase1.executor_harness import (
    ExecutorHarness,
    make_entity_hybrid_report,
    make_two_entity_hybrid_report,
)
from tests.support.worker_phase2.duplicate_detection import (
    duplicate_evidence_by_scope,
    duplicate_final_counts,
    duplicate_normalized_labels,
    duplicate_positions_by_job_entity_uid,
    duplicate_products_by_job_position_sku,
    duplicate_raw_labels,
    entity_uid_from_position,
    repeated_evidence_by_job_path,
    repeated_final_counts_by_job_sku,
    repeated_normalized_labels_by_job_sku,
    repeated_products_by_job_sku,
    repeated_raw_labels_by_source_reference,
)
from tests.support.worker_phase2.job_scope_inspection import assert_no_row_id_overlap
from tests.support.worker_phase2.recompute_doubles import FailingJobScopedRecomputeFactory
from tests.support.worker_phase2.retry_flow import build_retry_flow_services


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


def _single_entity_report(
    *,
    entity_uid: str,
    sku: str,
    quantity: int,
    evidence_path: str,
    source_image_id: str = "asset-1",
) -> dict:
    return make_entity_hybrid_report(
        [
            {
                "entity_uid": entity_uid,
                "entity_type": "PALLET",
                "model_entity_id": entity_uid.upper(),
                "internal_code": sku,
                "final_quantity": quantity,
                "product_label_quantity": quantity,
                "confidence": 0.9,
                "count_status": "COUNTED",
                "evidence_path": evidence_path,
                "source_image_id": source_image_id,
            }
        ]
    )


def _shared_retry_harness(
    tmp_path: Path,
    *,
    job_id: str,
    recompute_uc,
    processing_mode: InventoryProcessingMode = InventoryProcessingMode.PRODUCTION,
    **shared,
) -> ExecutorHarness:
    return ExecutorHarness.build(
        tmp_path,
        job_id=job_id,
        recompute_uc=recompute_uc,
        processing_mode=processing_mode,
        **shared,
    )


# --- P2-T001: direct persist characterization ---------------------------------


def test_p2_t001_same_job_identical_persist_is_idempotent_after_part2(tmp_path: Path) -> None:
    """P2-T001: Part 2 delete-and-replace makes identical re-persist idempotent."""
    harness = ExecutorHarness.build(tmp_path, job_id="job-p2-t001")
    report = _standard_two_entity_report()

    harness.persist_report(report, job_id="job-p2-t001")
    snap1 = harness.snapshot_job_scope("job-p2-t001")
    harness.persist_report(report, job_id="job-p2-t001")
    snap2 = harness.snapshot_job_scope("job-p2-t001")

    assert snap1.position_count == 2
    assert snap2.position_count == 2
    assert snap1.product_count == snap2.product_count == 2
    assert snap1.raw_label_count == snap2.raw_label_count == 2

    all_positions = harness.positions_for_job("job-p2-t001")
    assert duplicate_positions_by_job_entity_uid(all_positions) == {}

    pos_map = harness.position_job_id_map("job-p2-t001")
    all_products = harness.products_for_job("job-p2-t001")
    assert duplicate_products_by_job_position_sku(all_products, position_job_id=pos_map) == {}
    assert repeated_products_by_job_sku(all_products, position_job_id=pos_map) == {}

    all_evidence = harness.evidence_for_job("job-p2-t001")
    assert duplicate_evidence_by_scope(all_evidence, position_job_id=pos_map) == {}
    assert repeated_evidence_by_job_path(all_evidence, position_job_id=pos_map) == {}

    raw_labels = harness.raw_labels_for_job("job-p2-t001")
    assert len(raw_labels) == 2
    assert duplicate_raw_labels(raw_labels) == {}
    assert repeated_raw_labels_by_source_reference(raw_labels) == {}

    norm_labels = harness.normalized_labels_for_job("job-p2-t001")
    assert len(norm_labels) == 2
    assert duplicate_normalized_labels(norm_labels) == {}
    assert repeated_normalized_labels_by_job_sku(norm_labels) == {}

    finals = harness.final_counts_for_job("job-p2-t001")
    assert len(finals) == 2
    assert duplicate_final_counts(finals) == {}
    assert repeated_final_counts_by_job_sku(finals) == {}


# --- P2-T002: direct persist characterization ---------------------------------


def test_p2_t002_same_job_changed_report_replaces_stale_rows_after_part2(tmp_path: Path) -> None:
    """P2-T002: Part 2 delete-and-replace removes stale B and keeps one A + C."""
    harness = ExecutorHarness.build(tmp_path, job_id="job-p2-t002")
    first = _abc_report(qty_a=2, qty_b=4, include_b=True, include_c=False)
    second = _abc_report(qty_a=99, qty_b=4, include_b=False, include_c=True, qty_c=5)

    harness.persist_report(first, job_id="job-p2-t002")
    harness.persist_report(second, job_id="job-p2-t002")

    positions = harness.positions_for_job("job-p2-t002")
    by_uid = {entity_uid_from_position(p): p for p in positions}

    assert len(positions) == 2
    assert set(by_uid) == {"e1", "e3"}
    assert (by_uid["e1"].detected_summary_json or {}).get("final_quantity") == 99
    assert (by_uid["e3"].detected_summary_json or {}).get("final_quantity") == 5
    assert duplicate_positions_by_job_entity_uid(positions) == {}

    pos_map = harness.position_job_id_map("job-p2-t002")
    products = harness.products_for_job("job-p2-t002")
    assert len(products) == 2
    assert {p.sku for p in products} == {"SKU-A", "SKU-C"}
    assert duplicate_products_by_job_position_sku(products, position_job_id=pos_map) == {}

    evidence = harness.evidence_for_job("job-p2-t002")
    assert len(evidence) == 2
    assert duplicate_evidence_by_scope(evidence, position_job_id=pos_map) == {}

    raw_labels = harness.raw_labels_for_job("job-p2-t002")
    assert len(raw_labels) == 2
    assert duplicate_raw_labels(raw_labels) == {}

    norm_labels = harness.normalized_labels_for_job("job-p2-t002")
    assert len(norm_labels) == 2
    assert {n.canonical_sku for n in norm_labels} == {"SKU-A", "SKU-C"}
    assert duplicate_normalized_labels(norm_labels) == {}

    finals = harness.final_counts_for_job("job-p2-t002")
    assert len(finals) == 2
    assert {f.sku for f in finals} == {"SKU-A", "SKU-C"}
    assert duplicate_final_counts(finals) == {}


# --- P2-T003: real executor failure + RetryAisleJobUseCase --------------------


def test_p2_t003_real_failed_job_retry_isolates_all_layers(tmp_path: Path) -> None:
    """P2-T003: executor failure → FAILED job; RetryAisleJobUseCase → success; layers isolated."""
    harness = _shared_retry_harness(tmp_path, job_id="job-failed", recompute_uc=None)
    failing_factory = FailingJobScopedRecomputeFactory()
    failed_report = _single_entity_report(
        entity_uid="e-failed",
        sku="SKU-FAILED",
        quantity=99,
        evidence_path="evidence/failed.jpg",
    )
    executor = harness.make_executor(job_scoped_recompute_factory=failing_factory)
    handled = harness.run_with_mock_pipeline(executor, report=failed_report)
    assert handled is True
    assert failing_factory.execute_calls == 1

    failed_job = harness.job_repo.get_by_id("job-failed")
    assert failed_job is not None
    assert failed_job.status == JobStatus.FAILED
    assert failed_job.failure_code == "PROCESSING_FAILED"
    assert failed_job.error_message is not None
    assert failed_job.error_message.startswith("Persist:")

    failed_aisle = harness.aisle_repo.get_by_id(harness.aisle_id)
    assert failed_aisle is not None
    assert failed_aisle.status == AisleStatus.FAILED
    assert failed_aisle.operational_job_id is None

    failed_inv = harness.inventory_repo.get_by_id(harness.inventory_id)
    assert failed_inv is not None
    assert failed_inv.status == InventoryStatus.FAILED

    snap_failed = harness.snapshot_job_scope("job-failed")
    assert snap_failed.position_count == 0
    assert snap_failed.product_count == 0
    assert snap_failed.evidence_count == 0
    assert snap_failed.raw_label_count == 0
    assert snap_failed.normalized_label_count == 0
    assert snap_failed.final_count_count == 0

    retry_services = build_retry_flow_services(harness)
    retry_job = retry_services.retry_use_case.execute(
        RetryAisleJobCommand(harness.inventory_id, harness.aisle_id, "job-failed")
    )
    assert retry_job.id != "job-failed"
    assert retry_job.retry_of_job_id == "job-failed"
    assert retry_job.status == JobStatus.STARTING
    assert retry_job.target_id == harness.aisle_id
    assert retry_services.worker_launch.launched == [retry_job.id]

    retry_harness = _shared_retry_harness(
        tmp_path,
        job_id=retry_job.id,
        recompute_uc=None,
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
    success_report = _single_entity_report(
        entity_uid="e-success",
        sku="SKU-SUCCESS",
        quantity=5,
        evidence_path="evidence/success.jpg",
    )
    retry_executor = retry_harness.make_executor(artifact_store=ArtifactUploadSpy())
    assert retry_harness.run_with_mock_pipeline(retry_executor, report=success_report) is True

    success_job = retry_harness.job_repo.get_by_id(retry_job.id)
    assert success_job is not None
    assert success_job.status == JobStatus.SUCCEEDED

    aisle_after = retry_harness.aisle_repo.get_by_id(retry_harness.aisle_id)
    assert aisle_after is not None
    assert aisle_after.status == AisleStatus.PROCESSED
    assert aisle_after.operational_job_id == retry_job.id
    assert operational_job_id_for_retry(retry_harness) == retry_job.id

    snap_success = retry_harness.snapshot_job_scope(retry_job.id)
    assert snap_success.position_count == 1
    assert snap_success.raw_label_count == 1
    assert snap_success.normalized_label_count == 1
    assert snap_success.final_count_count == 1

    _assert_cross_job_layer_isolation(retry_harness, "job-failed", retry_job.id)

    resolver = ResultContextResolver(retry_harness.job_repo)
    list_uc = ListAislePositionsUseCase(
        retry_harness.inventory_repo,
        retry_harness.aisle_repo,
        retry_harness.position_repo,
        resolver,
        retry_harness.product_repo,
        positions_aisle_raw_cap=500,
    )
    list_result = list_uc.execute(
        ListAislePositionsCommand(
            inventory_id=retry_harness.inventory_id,
            aisle_id=retry_harness.aisle_id,
            page=1,
            page_size=50,
        )
    )
    assert list_result.resolved_job_id == retry_job.id
    success_positions = retry_harness.positions_for_job(retry_job.id)
    assert {p.id for p in list_result.positions} == {p.id for p in success_positions}
    assert all(
        (p.detected_summary_json or {}).get("final_quantity") == 5 for p in list_result.positions
    )
    assert "SKU-FAILED" not in {
        p.sku for p in list_result.primary_products if p is not None
    }

    export_collector = ExportInventoryCollector(
        retry_harness.inventory_repo,
        retry_harness.aisle_repo,
        retry_harness.position_repo,
        retry_harness.product_repo,
        resolver,
    )
    export_data = export_collector.collect_aisle(
        retry_harness.inventory_id,
        retry_harness.aisle_id,
    )
    bundle = export_data.aisle_bundles[0]
    assert bundle.job_id_for_slice == retry_job.id
    export_skus = sorted(row.internal_row.get("product_sku") or "" for row in bundle.rows)
    assert export_skus == ["SKU-SUCCESS"]
    export_qtys = [int(row.internal_row.get("final_quantity") or 0) for row in bundle.rows]
    assert export_qtys == [5]
    assert 99 not in export_qtys


def _seed_historical_failed_job_raw_label(harness: ExecutorHarness, *, job_id: str) -> None:
    """Simulate audit-retained raw label from a complete failed job snapshot."""
    now = datetime.now(timezone.utc)
    harness.raw_repo.save_many(
        [
            RawLabel(
                id=str(uuid4()),
                inventory_id=harness.inventory_id,
                aisle_id=harness.aisle_id,
                position_id=None,
                evidence_id=None,
                group_key="e-failed",
                provider="pipeline",
                source_type="hybrid",
                source_reference="e-failed",
                sku_raw="SKU-FAILED",
                sku_candidate="SKU-FAILED",
                product_name_raw=None,
                detected_text=None,
                confidence=0.9,
                metadata={},
                created_at=now,
                job_id=job_id,
            )
        ]
    )


def operational_job_id_for_retry(harness: ExecutorHarness) -> str | None:
    aisle = harness.aisle_repo.get_by_id(harness.aisle_id)
    if aisle is None or not aisle.operational_job_id:
        return None
    return str(aisle.operational_job_id).strip() or None


def _assert_cross_job_layer_isolation(
    harness: ExecutorHarness,
    failed_job_id: str,
    success_job_id: str,
) -> None:
    failed_positions = harness.positions_for_job(failed_job_id)
    success_positions = harness.positions_for_job(success_job_id)
    assert len(failed_positions) == 0
    assert len(success_positions) == 1
    assert (success_positions[0].detected_summary_json or {}).get("final_quantity") == 5
    assert duplicate_positions_by_job_entity_uid(success_positions) == {}

    failed_products = harness.products_for_job(failed_job_id)
    success_products = harness.products_for_job(success_job_id)
    assert len(failed_products) == 0
    assert len(success_products) == 1
    assert success_products[0].sku == "SKU-SUCCESS"
    assert success_products[0].detected_quantity == 5

    failed_evidence = harness.evidence_for_job(failed_job_id)
    success_evidence = harness.evidence_for_job(success_job_id)
    assert len(failed_evidence) == 0
    assert len(success_evidence) == 1
    assert "success.jpg" in success_evidence[0].storage_path

    failed_raw = harness.raw_labels_for_job(failed_job_id)
    success_raw = harness.raw_labels_for_job(success_job_id)
    assert len(failed_raw) == 0
    assert len(success_raw) == 1
    assert success_raw[0].sku_raw == "SKU-SUCCESS"

    failed_norm = harness.normalized_labels_for_job(failed_job_id)
    success_norm = harness.normalized_labels_for_job(success_job_id)
    assert len(failed_norm) == 0
    assert len(success_norm) == 1
    assert success_norm[0].canonical_sku == "SKU-SUCCESS"

    failed_final = harness.final_counts_for_job(failed_job_id)
    success_final = harness.final_counts_for_job(success_job_id)
    assert len(failed_final) == 0
    assert len(success_final) == 1
    assert success_final[0].sku == "SKU-SUCCESS"
    assert success_final[0].quantity == 1

    snap_failed = harness.snapshot_job_scope(failed_job_id)
    snap_success = harness.snapshot_job_scope(success_job_id)
    assert_no_row_id_overlap(
        snap_failed.position_ids,
        snap_success.position_ids,
        snap_failed.product_ids,
        snap_success.product_ids,
        snap_failed.evidence_ids,
        snap_success.evidence_ids,
        snap_failed.raw_label_ids,
        snap_success.raw_label_ids,
        snap_success.normalized_label_ids,
        snap_success.final_count_ids,
    )


# --- P2-T003-ALL-SCOPE: cross-job recompute leakage ---------------------------


def test_p2_t003_all_scope_recompute_mixes_failed_and_success_raw_labels(
    tmp_path: Path,
) -> None:
    """P2-T003-ALL-SCOPE: job_scope='all' includes raw labels from FAILED and SUCCEEDED jobs."""
    harness = _shared_retry_harness(tmp_path, job_id="job-failed-all", recompute_uc=None)
    failing_factory = FailingJobScopedRecomputeFactory()
    failed_report = _single_entity_report(
        entity_uid="e-failed",
        sku="SKU-FAILED",
        quantity=99,
        evidence_path="evidence/failed.jpg",
    )
    harness.run_with_mock_pipeline(
        harness.make_executor(job_scoped_recompute_factory=failing_factory),
        report=failed_report,
    )
    assert harness.job_repo.get_by_id("job-failed-all").status == JobStatus.FAILED
    assert harness.raw_labels_for_job("job-failed-all").__len__() == 0
    _seed_historical_failed_job_raw_label(harness, job_id="job-failed-all")

    retry_job = build_retry_flow_services(harness).retry_use_case.execute(
        RetryAisleJobCommand(harness.inventory_id, harness.aisle_id, "job-failed-all")
    )
    retry_harness = _shared_retry_harness(
        tmp_path,
        job_id=retry_job.id,
        recompute_uc=None,
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
    success_report = _single_entity_report(
        entity_uid="e-success",
        sku="SKU-SUCCESS",
        quantity=5,
        evidence_path="evidence/success.jpg",
    )
    retry_harness.run_with_mock_pipeline(
        retry_harness.make_executor(artifact_store=ArtifactUploadSpy()),
        report=success_report,
    )
    assert retry_harness.job_repo.get_by_id(retry_job.id).status == JobStatus.SUCCEEDED

    expected_failed_raw = 1
    expected_success_raw = 1
    success_scope = retry_harness.recompute_uc.execute(
        RecomputeConsolidatedCountsCommand(
            inventory_id=retry_harness.inventory_id,
            aisle_id=retry_harness.aisle_id,
            apply_to_product_records=False,
            job_scope=retry_job.id,
        )
    )
    all_scope = retry_harness.recompute_uc.execute(
        RecomputeConsolidatedCountsCommand(
            inventory_id=retry_harness.inventory_id,
            aisle_id=retry_harness.aisle_id,
            apply_to_product_records=False,
            job_scope="all",
        )
    )
    assert success_scope.raw_count == expected_success_raw
    assert all_scope.raw_count == expected_failed_raw + expected_success_raw
    assert all_scope.raw_count > success_scope.raw_count
    assert all_scope.normalized_count == 2
    assert success_scope.normalized_count == 1
    assert all_scope.final_count == 2
    assert success_scope.final_count == 1

    all_norm = list(
        retry_harness.norm_repo.list_for_scope(
            retry_harness.inventory_id, retry_harness.aisle_id, job_id="all"
        )
    )
    assert len(all_norm) == 2
    assert {n.canonical_sku for n in all_norm} == {"SKU-FAILED", "SKU-SUCCESS"}
