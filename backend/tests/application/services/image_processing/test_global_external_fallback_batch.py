"""Tests for GLOBAL_BATCH external fallback — mode, batching, merge, coordinator."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Sequence
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
    build_batch_slices,
    chunk_asset_ids,
    compute_batch_fingerprint,
    stable_ordered_asset_ids,
)
from src.application.services.image_processing.global_fallback_merge_policy import (
    ExternalEntityEvidence,
    GlobalFallbackMergeAction,
    InternalAssetEvidence,
    decide_merge_for_asset,
    decide_unmapped_entity,
)
from src.domain.image_processing.job_processing_lease import (
    JobProcessingLease,
    JobProcessingLeaseStatus,
)


def test_parse_mode_default_and_valid():
    assert parse_external_fallback_mode(None) == EXTERNAL_FALLBACK_MODE_GLOBAL_BATCH
    assert parse_external_fallback_mode("") == EXTERNAL_FALLBACK_MODE_GLOBAL_BATCH
    assert parse_external_fallback_mode("global_batch") == EXTERNAL_FALLBACK_MODE_GLOBAL_BATCH
    assert parse_external_fallback_mode("PER_ASSET") == EXTERNAL_FALLBACK_MODE_PER_ASSET


def test_parse_mode_unknown_fails_closed():
    with pytest.raises(ExternalFallbackModeError):
        parse_external_fallback_mode("SILENT_FALLBACK")


@pytest.mark.parametrize(
    "n,max_per,expected_batches",
    [
        (1, 48, 1),
        (5, 48, 1),
        (48, 48, 1),
        (49, 48, 2),
    ],
)
def test_chunk_sizes(n, max_per, expected_batches):
    ids = [f"a{i:03d}" for i in range(n)]
    chunks = chunk_asset_ids(ids, max_per_batch=max_per)
    assert len(chunks) == expected_batches
    assert sum(len(c) for c in chunks) == n
    if n > 1:
        assert all(len(c) > 0 for c in chunks)
        if n == 49:
            assert len(chunks[0]) == 48
            assert len(chunks[1]) == 1


def test_stable_order_and_fingerprint_deterministic():
    ids = ["b", "a", "c"]
    ordered = stable_ordered_asset_ids(ids)
    assert ordered == ("a", "b", "c")
    fp1 = compute_batch_fingerprint(
        job_id="j1",
        execution_id="e1",
        attempt=1,
        fallback_mode="GLOBAL_BATCH",
        provider="claude",
        model="m",
        schema_version="v2.1",
        configuration_fingerprint="cfg",
        prompt_fingerprint="p",
        batch_index=0,
        ordered_asset_ids=ordered,
    )
    fp2 = compute_batch_fingerprint(
        job_id="j1",
        execution_id="e1",
        attempt=1,
        fallback_mode="GLOBAL_BATCH",
        provider="claude",
        model="m",
        schema_version="v2.1",
        configuration_fingerprint="cfg",
        prompt_fingerprint="p",
        batch_index=0,
        ordered_asset_ids=("a", "b", "c"),
    )
    assert fp1 == fp2


def test_build_batch_slices_49():
    ids = [f"a{i:03d}" for i in range(49)]
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
    )
    assert len(slices) == 2
    assert slices[0].batch_count == 2
    assert slices[0].fingerprint != slices[1].fingerprint


@pytest.mark.parametrize(
    "internal,external,action",
    [
        (
            InternalAssetEvidence("a1", "RESOLVED", "CODE1", 2.0, True),
            ExternalEntityEvidence("CODE1", 2.0, source_image_id="a1"),
            GlobalFallbackMergeAction.KEEP_INTERNAL,
        ),
        (
            InternalAssetEvidence("a1", "UNRECOGNIZED", "CODE1", None, False),
            ExternalEntityEvidence("CODE1", 5.0, source_image_id="a1"),
            GlobalFallbackMergeAction.COMBINE_QUANTITY,
        ),
        (
            InternalAssetEvidence("a1", "UNRECOGNIZED", None, None, False),
            ExternalEntityEvidence("CODE9", 1.0, source_image_id="a1"),
            GlobalFallbackMergeAction.APPLY_EXTERNAL,
        ),
        (
            InternalAssetEvidence("a1", "RESOLVED", "CODE1", 1.0, True),
            ExternalEntityEvidence("CODE2", 1.0, source_image_id="a1"),
            GlobalFallbackMergeAction.CONFLICT_REVIEW,
        ),
        (
            InternalAssetEvidence("a1", "RESOLVED", "CODE1", 1.0, True),
            None,
            GlobalFallbackMergeAction.KEEP_INTERNAL,
        ),
    ],
)
def test_merge_matrix(internal, external, action):
    d = decide_merge_for_asset(internal=internal, external=external)
    assert d.action is action


def test_unmapped_entity_review():
    d = decide_unmapped_entity(ExternalEntityEvidence("X", 1.0))
    assert d.action is GlobalFallbackMergeAction.UNMAPPED_REVIEW


@dataclass
class _FakeAsset:
    id: str
    original_filename: str | None = None


@dataclass
class _FakeSnapshot:
    enabled: bool = True
    provider: str = "claude"
    model: str = "sonnet"
    fallback_mode: str = EXTERNAL_FALLBACK_MODE_GLOBAL_BATCH
    supplier_id: str | None = None
    supplier_prompt: dict | None = None
    supplier_prompt_required: bool = False


@dataclass
class _FakeJob:
    id: str = "job-1"
    attempt_count: int = 1
    result_json: dict = field(default_factory=dict)
    configuration_snapshot_version: int = 1


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
        return GlobalFallbackBatchAnalysisResult(
            ok=True,
            entities=[
                {
                    "internal_code": f"C-{a.id}",
                    "quantity": 1,
                    "source_image_id": a.id,
                    "confidence": 0.9,
                }
                for a in assets
            ],
            schema_version="v2.1",
            prompt_key="global_v22",
            provider="claude",
            model="sonnet",
        )


class _FakeLeaseRepo:
    def __init__(self) -> None:
        self.acquired = 0
        self.completed = 0

    def try_acquire_lease(self, **kwargs: Any) -> JobProcessingLease:
        self.acquired += 1
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


def test_coordinator_five_images_one_call():
    assets = [_FakeAsset(f"a{i}") for i in range(5)]
    analyzer = _FakeAnalyzer()
    lease_repo = _FakeLeaseRepo()
    persister = _FakePersister()
    clock = MagicMock()
    clock.now.return_value = datetime.now(timezone.utc)

    coordinator = GlobalExternalFallbackCoordinator(
        lease_repo=lease_repo,
        clock=clock,
        batch_analyzer=analyzer,
        result_persister=persister,
        max_frames_per_batch=48,
        load_internal_evidence=lambda _j, aid: InternalAssetEvidence(
            aid, "UNRECOGNIZED", None, None, False
        ),
    )
    outcome = coordinator.process_after_internal_pass(
        job=_FakeJob(),
        aisle=_FakeAisle(),
        assets=assets,
        snapshot=_FakeSnapshot(),
        worker_token="w1",
        is_cancelled=lambda: False,
    )
    assert not outcome.failed
    assert not outcome.skipped or outcome.skip_reason is None or outcome.requests_count == 1
    assert outcome.requests_count == 1
    assert len(analyzer.calls) == 1
    assert len(analyzer.calls[0]) == 5
    assert outcome.public_summary.get("requests_count") == 1
    assert outcome.public_summary.get("batch_count") == 1
    assert outcome.public_summary.get("fallback_mode") == "GLOBAL_BATCH"
    assert outcome.public_summary.get("analysis_contract") == "GlobalEntityResponseV21"
    assert persister.persisted  # applied external for unresolved


def test_coordinator_skips_when_disabled():
    coordinator = GlobalExternalFallbackCoordinator(
        lease_repo=_FakeLeaseRepo(),
        clock=MagicMock(),
        batch_analyzer=_FakeAnalyzer(),
        result_persister=_FakePersister(),
    )
    outcome = coordinator.process_after_internal_pass(
        job=_FakeJob(),
        aisle=_FakeAisle(),
        assets=[_FakeAsset("a1")],
        snapshot=_FakeSnapshot(enabled=False),
        worker_token="w",
        is_cancelled=lambda: False,
    )
    assert outcome.skipped
    assert outcome.skip_reason == "fallback_disabled"


def test_coordinator_skips_per_asset_mode():
    analyzer = _FakeAnalyzer()
    coordinator = GlobalExternalFallbackCoordinator(
        lease_repo=_FakeLeaseRepo(),
        clock=MagicMock(),
        batch_analyzer=analyzer,
        result_persister=_FakePersister(),
    )
    outcome = coordinator.process_after_internal_pass(
        job=_FakeJob(),
        aisle=_FakeAisle(),
        assets=[_FakeAsset("a1")],
        snapshot=_FakeSnapshot(fallback_mode=EXTERNAL_FALLBACK_MODE_PER_ASSET),
        worker_token="w",
        is_cancelled=lambda: False,
    )
    assert outcome.skipped
    assert outcome.skip_reason == "mode_per_asset"
    assert analyzer.calls == []


def test_coordinator_cancelled_no_call():
    analyzer = _FakeAnalyzer()
    coordinator = GlobalExternalFallbackCoordinator(
        lease_repo=_FakeLeaseRepo(),
        clock=MagicMock(),
        batch_analyzer=analyzer,
        result_persister=_FakePersister(),
    )
    outcome = coordinator.process_after_internal_pass(
        job=_FakeJob(),
        aisle=_FakeAisle(),
        assets=[_FakeAsset("a1")],
        snapshot=_FakeSnapshot(),
        worker_token="w",
        is_cancelled=lambda: True,
    )
    assert outcome.cancelled
    assert analyzer.calls == []


def test_coordinator_keeps_valid_internal_no_overwrite():
    assets = [_FakeAsset("a1")]
    analyzer = _FakeAnalyzer()
    persister = _FakePersister()
    clock = MagicMock()
    clock.now.return_value = datetime.now(timezone.utc)
    coordinator = GlobalExternalFallbackCoordinator(
        lease_repo=_FakeLeaseRepo(),
        clock=clock,
        batch_analyzer=analyzer,
        result_persister=persister,
        load_internal_evidence=lambda _j, aid: InternalAssetEvidence(
            aid, "RESOLVED", "C-a1", 1.0, True
        ),
    )
    outcome = coordinator.process_after_internal_pass(
        job=_FakeJob(),
        aisle=_FakeAisle(),
        assets=assets,
        snapshot=_FakeSnapshot(),
        worker_token="w",
        is_cancelled=lambda: False,
    )
    assert outcome.requests_count == 1
    assert outcome.kept_internal >= 1
    assert persister.persisted == []


def test_build_external_fallback_snapshot_dict_global_identity():
    from src.application.services.image_processing.external_provider_fallback_orchestrator import (
        build_external_fallback_snapshot_dict,
    )

    d = build_external_fallback_snapshot_dict(
        enabled=True,
        provider="claude",
        model="m",
        timeout_seconds=60,
        max_attempts=1,
        max_concurrency=1,
        max_image_dimension=1800,
        quantity_max=99,
        circuit_breaker_threshold=5,
        circuit_breaker_cooldown_seconds=60,
        snapshot_version=1,
        fallback_mode="GLOBAL_BATCH",
    )
    assert d["fallback_mode"] == "GLOBAL_BATCH"
    assert d["prompt_key"] == "global_v22"
    assert d["schema_version"] == "v2.1"
    assert d["analysis_contract"] == "GlobalEntityResponseV21"
    assert d["execution_scope"] == "AISLE_BATCH"
