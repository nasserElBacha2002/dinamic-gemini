"""Tests for GLOBAL_BATCH corrections — eligibility, journal, merge plan, coordinator."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.application.services.image_processing.external_fallback_mode import (
    EXTERNAL_FALLBACK_MODE_GLOBAL_BATCH,
    EXTERNAL_FALLBACK_MODE_PER_ASSET,
    ExternalFallbackModeError,
    parse_external_fallback_mode,
)
from src.application.services.image_processing.global_external_fallback_coordinator import (
    GlobalExternalFallbackCoordinator,
    GlobalFallbackBatchAnalysisResult,
)
from src.application.services.image_processing.global_fallback_batching import (
    AssetOrderKey,
    build_batch_slices,
    chunk_asset_ids,
    compute_batch_fingerprint,
    stable_ordered_asset_ids,
)
from src.application.services.image_processing.global_fallback_eligibility import (
    evaluate_global_fallback_eligibility,
)
from src.application.services.image_processing.global_fallback_fingerprints import (
    asset_content_identity_hash,
    configuration_fingerprint_from_snapshot,
)
from src.application.services.image_processing.global_fallback_merge_applier import (
    GlobalFallbackMergeApplier,
)
from src.application.services.image_processing.global_fallback_merge_planner import (
    build_merge_plan,
)
from src.application.services.image_processing.global_fallback_merge_policy import (
    ExternalEntityEvidence,
    GlobalFallbackMergeAction,
    InternalAssetEvidence,
    decide_merge_for_asset,
    decide_multi_entity_for_asset,
    normalize_provider_source_image_id,
)
from src.application.services.image_processing.global_fallback_schema_validation import (
    GlobalFallbackSchemaError,
    validate_global_fallback_report,
)
from src.domain.image_processing.global_fallback_batch_request import (
    GlobalFallbackBatchStatus,
)
from src.domain.image_processing.job_processing_lease import (
    JobProcessingLease,
    JobProcessingLeaseStatus,
)
from src.infrastructure.repositories.memory_global_fallback_batch_request_repository import (
    MemoryGlobalFallbackBatchRequestRepository,
)


def test_parse_mode_default_and_valid():
    assert parse_external_fallback_mode(None) == EXTERNAL_FALLBACK_MODE_GLOBAL_BATCH
    assert parse_external_fallback_mode("PER_ASSET") == EXTERNAL_FALLBACK_MODE_PER_ASSET


def test_parse_mode_unknown_fails_closed():
    with pytest.raises(ExternalFallbackModeError):
        parse_external_fallback_mode("SILENT_FALLBACK")


def test_eligibility_all_resolved_skips():
    evidence = {
        f"a{i}": InternalAssetEvidence(f"a{i}", "RESOLVED", f"C{i}", 1.0, True)
        for i in range(5)
    }
    d = evaluate_global_fallback_eligibility(evidence)
    assert d.needs_fallback is False
    assert d.reason == "all_resolved_internal"


def test_eligibility_one_unrecognized_needs_all_images_context():
    evidence = {
        "a0": InternalAssetEvidence("a0", "RESOLVED", "C0", 1.0, True),
        "a1": InternalAssetEvidence("a1", "UNRECOGNIZED", None, None, False),
    }
    d = evaluate_global_fallback_eligibility(evidence)
    assert d.needs_fallback is True
    assert d.eligible_count >= 1


@pytest.mark.parametrize(
    "n,max_per,expected_batches",
    [(1, 48, 1), (5, 48, 1), (48, 48, 1), (49, 48, 2)],
)
def test_chunk_sizes(n, max_per, expected_batches):
    ids = [f"a{i:03d}" for i in range(n)]
    chunks = chunk_asset_ids(ids, max_per_batch=max_per)
    assert len(chunks) == expected_batches


def test_capture_order_not_uuid_sort():
    keys = [
        AssetOrderKey("b", sequence=0),
        AssetOrderKey("a", sequence=1),
        AssetOrderKey("c", sequence=2),
    ]
    ordered = stable_ordered_asset_ids(["a", "b", "c"], order_keys=keys)
    assert ordered == ("b", "a", "c")


def test_fingerprint_requires_prepared_hashes():
    with pytest.raises(ValueError, match="PREPARED_IMAGE_HASHES"):
        compute_batch_fingerprint(
            job_id="j",
            execution_id="e",
            attempt=1,
            fallback_mode="GLOBAL_BATCH",
            provider="claude",
            model="m",
            schema_version="v2.1",
            configuration_fingerprint="cfg",
            prompt_fingerprint="p",
            batch_index=0,
            ordered_asset_ids=["a1"],
            prepared_image_hashes=[""],
        )


def test_fingerprint_changes_with_bytes():
    common = dict(
        job_id="j",
        execution_id="e",
        attempt=1,
        fallback_mode="GLOBAL_BATCH",
        provider="claude",
        model="m",
        schema_version="v2.1",
        configuration_fingerprint="cfg",
        prompt_fingerprint="p",
        batch_index=0,
        ordered_asset_ids=["a1"],
    )
    fp1 = compute_batch_fingerprint(**common, prepared_image_hashes=["hash-a"])
    fp2 = compute_batch_fingerprint(**common, prepared_image_hashes=["hash-b"])
    assert fp1 != fp2


def test_configuration_fingerprint_from_snapshot():
    snap = {"external_fallback": {"fallback_mode": "GLOBAL_BATCH", "fallback_model": "m"}}
    fp1 = configuration_fingerprint_from_snapshot(snap)
    snap2 = {**snap, "external_fallback": {**snap["external_fallback"], "fallback_model": "other"}}
    fp2 = configuration_fingerprint_from_snapshot(snap2)
    assert fp1 != fp2


def test_schema_rejects_unknown_and_external_fallback():
    with pytest.raises(GlobalFallbackSchemaError):
        validate_global_fallback_report(
            {"schema_version": "foo_v9", "entities": [], "total_entities_detected": 0}
        )
    with pytest.raises(GlobalFallbackSchemaError):
        validate_global_fallback_report(
            {
                "schema_version": "external_fallback_v1",
                "entities": [],
                "total_entities_detected": 0,
            }
        )


def test_schema_accepts_operational_entities():
    ents = validate_global_fallback_report(
        {
            "schema_version": "v2.1",
            "entities": [
                {"internal_code": "X", "quantity": 1, "source_image_id": "a1"},
            ],
            "total_entities_detected": 1,
        }
    )
    assert len(ents) == 1


def test_img_n_mapping():
    mapped = normalize_provider_source_image_id(
        "img_1",
        asset_id_set={"a0", "a1"},
        ordered_asset_ids=("a0", "a1"),
        frame_to_asset_map={},
    )
    assert mapped == "a1"


def test_multi_entity_conflict():
    d = decide_multi_entity_for_asset(
        asset_id="a1",
        first=ExternalEntityEvidence("X", 1.0, source_image_id="a1"),
        second=ExternalEntityEvidence("Y", 1.0, source_image_id="a1"),
    )
    assert d.action is GlobalFallbackMergeAction.CONFLICT_REVIEW


def test_merge_plan_no_side_effects():
    plan = build_merge_plan(
        batch_fingerprint="fp",
        entities=[{"internal_code": "C", "quantity": 2, "source_image_id": "a1"}],
        evidence_by_asset={
            "a1": InternalAssetEvidence("a1", "UNRECOGNIZED", None, None, False)
        },
        ordered_asset_ids=["a1"],
    )
    assert len(plan.operations) == 1
    assert plan.operations[0].decision.action is GlobalFallbackMergeAction.APPLY_EXTERNAL


def test_merge_policy_code_without_quantity_applies_needs_review():
    d = decide_merge_for_asset(
        internal=InternalAssetEvidence("a1", "UNRECOGNIZED", None, None, False),
        external=ExternalEntityEvidence("3075807", None, source_image_id="a1"),
    )
    assert d.action is GlobalFallbackMergeAction.APPLY_EXTERNAL
    assert d.reason == "external_code_missing_quantity"


def test_merge_policy_no_code_still_skips():
    d = decide_merge_for_asset(
        internal=InternalAssetEvidence("a1", "UNRECOGNIZED", None, None, False),
        external=ExternalEntityEvidence(None, 12.0, source_image_id="a1"),
    )
    assert d.action is GlobalFallbackMergeAction.SKIP_EMPTY
    assert d.reason == "external_entity_incomplete"


def test_merge_policy_keeps_resolved_internal_when_external_missing_qty():
    d = decide_merge_for_asset(
        internal=InternalAssetEvidence("a1", "RESOLVED", "3075807", 16.0, True),
        external=ExternalEntityEvidence("3075807", None, source_image_id="a1"),
    )
    assert d.action is GlobalFallbackMergeAction.KEEP_INTERNAL


def test_merge_plan_code_only_entities_like_claude_report():
    """Regression: Claude returned codes without product_label_quantity → must apply."""
    plan = build_merge_plan(
        batch_fingerprint="fp",
        entities=[
            {
                "internal_code": "3075807",
                "product_label_quantity": None,
                "source_image_id": "a1",
                "confidence": 0.9,
            },
            {
                "internal_code": "1242879",
                "product_label_quantity": None,
                "source_image_id": "a2",
                "confidence": 0.9,
            },
        ],
        evidence_by_asset={
            "a1": InternalAssetEvidence("a1", "UNRECOGNIZED", None, None, False),
            "a2": InternalAssetEvidence("a2", "UNRECOGNIZED", None, None, False),
        },
        ordered_asset_ids=["a1", "a2"],
    )
    assert len(plan.operations) == 2
    assert all(
        op.decision.reason == "external_code_missing_quantity" for op in plan.operations
    )
    assert plan.to_public_dict()["apply_count"] == 2
    assert plan.to_public_dict()["skipped_count"] == 0


def test_applier_marks_pending_manual_review_when_quantity_missing():
    from src.domain.image_processing.global_fallback_batch_request import (
        GlobalFallbackBatchRequest,
    )
    from src.domain.image_processing.job_asset_processing_state import (
        JobAssetProcessingStatus,
    )

    now = datetime.now(timezone.utc)
    journal = MemoryGlobalFallbackBatchRequestRepository()
    batch_row = GlobalFallbackBatchRequest(
        id="br-1",
        job_id="job-1",
        execution_id="ex-1",
        attempt=1,
        batch_index=0,
        batch_count=1,
        batch_fingerprint="fp",
        status=GlobalFallbackBatchStatus.VALIDATED,
        ordered_asset_ids=["a1"],
        provider="claude",
        model="sonnet",
        schema_version="v2.1",
        configuration_fingerprint="cfg",
        prompt_fingerprint="ph",
        prepared_image_hashes=["h1"],
        created_at=now,
        updated_at=now,
    )
    journal.save(batch_row)

    plan = build_merge_plan(
        batch_fingerprint="fp",
        entities=[
            {
                "internal_code": "3075807",
                "product_label_quantity": None,
                "source_image_id": "a1",
            }
        ],
        evidence_by_asset={
            "a1": InternalAssetEvidence("a1", "UNRECOGNIZED", None, None, False)
        },
        ordered_asset_ids=["a1"],
    )

    state = MagicMock()
    state.status = JobAssetProcessingStatus.UNRECOGNIZED
    state_repo = MagicMock()
    state_repo.get_by_job_and_asset.return_value = state
    persister = _FakePersister()
    clock = MagicMock()
    clock.now.return_value = now
    applier = GlobalFallbackMergeApplier(
        result_persister=persister,
        batch_journal=journal,
        state_repo=state_repo,
        clock=clock,
    )
    result = applier.apply(
        job=_FakeJob(),
        aisle=_FakeAisle(),
        asset_by_id={"a1": _FakeAsset("a1")},
        plan=plan,
        batch_row=batch_row,
        snapshot=_FakeSnapshot(),
    )
    assert result.applied == 1
    assert state.status is JobAssetProcessingStatus.PENDING_MANUAL_REVIEW
    assert state.error_code == "MISSING_QUANTITY"
    assert persister.persisted[0].quantity is None
    assert persister.persisted[0].internal_code == "3075807"


@dataclass
class _FakeAsset:
    id: str
    original_filename: str | None = None
    storage_key: str | None = None
    etag: str | None = None
    file_size_bytes: int | None = None
    mime_type: str | None = "image/jpeg"
    uploaded_at: datetime | None = None


@dataclass
class _FakeSnapshot:
    enabled: bool = True
    provider: str = "claude"
    model: str = "sonnet"
    fallback_mode: str = EXTERNAL_FALLBACK_MODE_GLOBAL_BATCH
    supplier_id: str | None = None
    supplier_prompt: dict | None = None
    supplier_prompt_required: bool = False
    client_rules: dict | None = None


@dataclass
class _FakeJob:
    id: str = "job-1"
    attempt_count: int = 1
    execution_id: str = "exec-1"
    result_json: dict = field(default_factory=dict)
    configuration_snapshot_version: int = 1
    engine_params_json: dict = field(
        default_factory=lambda: {
            "identification_execution": {
                "external_fallback": {"fallback_mode": "GLOBAL_BATCH"}
            }
        }
    )


@dataclass
class _FakeAisle:
    id: str = "aisle-1"
    inventory_id: str = "inv-1"


class _FakeAnalyzer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def analyze_batch(self, *, job, aisle, assets, batch, snapshot, prompt_fingerprint):
        ids = tuple(a.id for a in assets)
        self.calls.append(ids)
        entities = [
            {
                "internal_code": f"C-{a.id}",
                "quantity": 1,
                "source_image_id": a.id,
                "confidence": 0.9,
            }
            for a in assets
        ]
        return GlobalFallbackBatchAnalysisResult(
            ok=True,
            entities=entities,
            schema_version="v2.1",
            prompt_key="global_v22",
            provider="claude",
            model="sonnet",
            raw_report={
                "schema_version": "v2.1",
                "entities": entities,
                "total_entities_detected": len(entities),
            },
            frame_to_asset_map={f"img_{i}": a.id for i, a in enumerate(assets)},
        )


class _FakeLeaseRepo:
    def __init__(self) -> None:
        self.heartbeats = 0
        self.completed = 0

    def try_acquire_lease(self, **kwargs: Any) -> JobProcessingLease:
        now = datetime.now(timezone.utc)
        return JobProcessingLease(
            id="lease-1",
            job_id=kwargs["job_id"],
            strategy=kwargs["strategy"],
            execution_scope=kwargs["execution_scope"],
            status=JobProcessingLeaseStatus.ACQUIRED,
            created_at=now,
            updated_at=now,
            worker_token=kwargs["worker_token"],
        )

    def heartbeat(self, lease_id: str, **kwargs: Any) -> JobProcessingLease:
        self.heartbeats += 1
        now = datetime.now(timezone.utc)
        return JobProcessingLease(
            id=lease_id,
            job_id="job-1",
            strategy="GLOBAL_EXTERNAL_FALLBACK",
            execution_scope="AISLE_BATCH",
            status=JobProcessingLeaseStatus.ACQUIRED,
            created_at=now,
            updated_at=now,
            worker_token=kwargs["worker_token"],
        )

    def complete(self, lease_id: str, **kwargs: Any) -> None:
        self.completed += 1

    def fail(self, lease_id: str, **kwargs: Any) -> None:
        pass

    def release(self, lease_id: str, **kwargs: Any) -> None:
        pass


class _FakePersister:
    def __init__(self) -> None:
        self.persisted: list[Any] = []

    def persist(self, *, result, inventory_id, aisle_id):
        self.persisted.append(result)
        return MagicMock(persisted=True, reconciled=False)


def _hashes_for(assets: list[_FakeAsset]) -> dict[str, str]:
    return {
        a.id: asset_content_identity_hash(
            asset_id=a.id,
            storage_key=a.storage_key or a.id,
            etag=a.etag or "e",
            file_size_bytes=a.file_size_bytes or 1,
            mime_type=a.mime_type,
        )
        for a in assets
    }


def _coordinator(analyzer=None, journal=None, lease_repo=None, summaries=None):
    analyzer = analyzer or _FakeAnalyzer()
    journal = journal or MemoryGlobalFallbackBatchRequestRepository()
    lease_repo = lease_repo or _FakeLeaseRepo()
    persister = _FakePersister()
    clock = MagicMock()
    clock.now.return_value = datetime.now(timezone.utc)
    summaries = summaries if summaries is not None else []

    def persist_summary(job_id: str, summary: dict) -> None:
        summaries.append(summary)

    applier = GlobalFallbackMergeApplier(
        result_persister=persister,
        batch_journal=journal,
        state_repo=None,
        clock=clock,
    )
    return (
        GlobalExternalFallbackCoordinator(
            lease_repo=lease_repo,
            clock=clock,
            batch_analyzer=analyzer,
            batch_journal=journal,
            merge_applier=applier,
            persist_job_summary=persist_summary,
            max_frames_per_batch=48,
        ),
        analyzer,
        journal,
        lease_repo,
        persister,
        summaries,
    )


def test_coordinator_all_resolved_zero_calls():
    assets = [_FakeAsset(f"a{i}") for i in range(5)]
    evidence = {
        a.id: InternalAssetEvidence(a.id, "RESOLVED", f"C{a.id}", 1.0, True) for a in assets
    }
    coord, analyzer, *_ = _coordinator()
    outcome = coord.process_after_internal_pass(
        job=_FakeJob(),
        aisle=_FakeAisle(),
        assets=assets,
        snapshot=_FakeSnapshot(),
        worker_token="w",
        is_cancelled=lambda: False,
        evidence_by_asset=evidence,
        configuration_fingerprint="cfg",
        prepared_image_hashes_by_asset=_hashes_for(assets),
        order_keys=[AssetOrderKey(a.id, sequence=i) for i, a in enumerate(assets)],
    )
    assert outcome.skipped
    assert outcome.skip_reason == "all_resolved_internal"
    assert analyzer.calls == []
    assert outcome.public_summary.get("requests_count") == 0


def test_coordinator_five_images_one_call_when_needed():
    assets = [_FakeAsset(f"a{i}") for i in range(5)]
    evidence = {
        a.id: InternalAssetEvidence(a.id, "UNRECOGNIZED", None, None, False) for a in assets
    }
    summaries: list = []
    coord, analyzer, journal, lease_repo, persister, _ = _coordinator(summaries=summaries)
    cfg = configuration_fingerprint_from_snapshot(
        {"external_fallback": {"fallback_mode": "GLOBAL_BATCH"}}
    )
    outcome = coord.process_after_internal_pass(
        job=_FakeJob(),
        aisle=_FakeAisle(),
        assets=assets,
        snapshot=_FakeSnapshot(),
        worker_token="w1",
        is_cancelled=lambda: False,
        evidence_by_asset=evidence,
        configuration_fingerprint=cfg,
        prepared_image_hashes_by_asset=_hashes_for(assets),
        order_keys=[AssetOrderKey(a.id, sequence=i) for i, a in enumerate(assets)],
        execution_id="exec-1",
    )
    assert not outcome.failed
    assert outcome.requests_count == 1
    assert len(analyzer.calls) == 1
    assert len(analyzer.calls[0]) == 5
    assert lease_repo.heartbeats >= 1
    assert lease_repo.completed == 1
    assert summaries, "summary must be persisted before lease complete"
    rows = journal.list_by_job("job-1")
    assert len(rows) == 1
    assert rows[0].status is GlobalFallbackBatchStatus.COMPLETED
    assert rows[0].normalized_response_json is not None


def test_journal_reuse_skips_second_provider_call():
    assets = [_FakeAsset("a0")]
    evidence = {
        "a0": InternalAssetEvidence("a0", "UNRECOGNIZED", None, None, False),
    }
    journal = MemoryGlobalFallbackBatchRequestRepository()
    analyzer = _FakeAnalyzer()
    summaries: list = []
    coord, _, _, _, _, _ = _coordinator(
        analyzer=analyzer, journal=journal, summaries=summaries
    )
    cfg = configuration_fingerprint_from_snapshot({"k": 1})
    hashes = _hashes_for(assets)
    kwargs = dict(
        job=_FakeJob(),
        aisle=_FakeAisle(),
        assets=assets,
        snapshot=_FakeSnapshot(),
        worker_token="w",
        is_cancelled=lambda: False,
        evidence_by_asset=evidence,
        configuration_fingerprint=cfg,
        prepared_image_hashes_by_asset=hashes,
        order_keys=[AssetOrderKey("a0", sequence=0)],
        execution_id="exec-1",
    )
    first = coord.process_after_internal_pass(**kwargs)
    assert first.requests_count == 1
    analyzer2 = _FakeAnalyzer()
    coord2, _, _, _, _, _ = _coordinator(
        analyzer=analyzer2, journal=journal, summaries=summaries
    )
    second = coord2.process_after_internal_pass(**kwargs)
    assert analyzer2.calls == []
    assert second.requests_count == 0


def test_build_batch_slices_49_requires_hashes():
    ids = [f"a{i:03d}" for i in range(49)]
    hashes = {aid: f"h-{aid}" for aid in ids}
    slices = build_batch_slices(
        ids,
        max_per_batch=48,
        job_id="j",
        execution_id="e",
        attempt=1,
        fallback_mode="GLOBAL_BATCH",
        provider="gemini",
        model="x",
        schema_version="v2.1",
        configuration_fingerprint="c",
        prompt_fingerprint="p",
        prepared_image_hashes_by_asset=hashes,
        order_keys=[AssetOrderKey(aid, sequence=i) for i, aid in enumerate(ids)],
    )
    assert len(slices) == 2
