"""Integration: real CODE_SCAN decoder through aisle orchestrator to terminal counters.

Exercises the durable asset path the executor delegates to: real pyzbar strategy →
processor → persist outcome → job outcome counters / per-asset events.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone

import pytest

pytest.importorskip("pyzbar")
qrcode = pytest.importorskip("qrcode")

from src.application.services.image_processing.aisle_processing_orchestrator import (  # noqa: E402
    AisleProcessingOrchestrator,
)
from src.application.services.image_processing.asset_result_coverage_resolver import (  # noqa: E402
    AssetResultCoverageResolver,
)
from src.application.services.image_processing.code_detection_consolidator import (  # noqa: E402
    CodeDetectionConsolidator,
)
from src.application.services.image_processing.code_scan_processing_strategy import (  # noqa: E402
    CodeScanConfig,
    CodeScanProcessingStrategy,
)
from src.application.services.image_processing.encoded_label_payload_parser import (  # noqa: E402
    EncodedLabelPayloadParser,
)
from src.application.services.image_processing.image_processing_orchestrator import (  # noqa: E402
    ImageProcessingOrchestrator,
)
from src.application.services.image_processing.legacy_llm_processing_strategy import (  # noqa: E402
    LegacyLlmProcessingStrategy,
)
from src.application.services.image_processing.processing_result_persister import (  # noqa: E402
    PersistOutcome,
)
from src.application.services.image_processing.processing_strategy_resolver import (  # noqa: E402
    ProcessingStrategyResolver,
)
from src.domain.aisle.entities import Aisle, AisleStatus  # noqa: E402
from src.domain.aisle_identification.modes import (  # noqa: E402
    CONFIGURATION_SNAPSHOT_VERSION,
    AisleIdentificationExecutionStrategy,
    AisleIdentificationMode,
    AisleIdentificationModeSource,
)
from src.domain.assets.entities import SourceAsset, SourceAssetType  # noqa: E402
from src.domain.image_processing.contracts import ImageResultStatus  # noqa: E402
from src.domain.jobs.entities import Job, JobStatus  # noqa: E402
from src.infrastructure.repositories.memory_batch_processing_attempt_repository import (  # noqa: E402
    MemoryBatchProcessingAttemptRepository,
)
from src.infrastructure.repositories.memory_evidence_repository import (  # noqa: E402
    MemoryEvidenceRepository,
)
from src.infrastructure.repositories.memory_job_asset_processing_state_repository import (  # noqa: E402
    MemoryJobAssetProcessingStateRepository,
)
from src.infrastructure.repositories.memory_job_processing_lease_repository import (  # noqa: E402
    MemoryJobProcessingLeaseRepository,
)
from src.infrastructure.repositories.memory_position_repository import (  # noqa: E402
    MemoryPositionRepository,
)
from src.infrastructure.repositories.memory_processing_attempt_repository import (  # noqa: E402
    MemoryProcessingAttemptRepository,
)
from src.infrastructure.repositories.memory_result_evidence_repository import (  # noqa: E402
    MemoryResultEvidenceRepository,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


class FixedClock:
    def now(self) -> datetime:
        return NOW


class _FixedContentReader:
    def __init__(self, content: bytes) -> None:
        self._content = content

    def read_image_bytes(self, asset: SourceAsset) -> bytes:
        return self._content


class _RecordingPersister:
    def __init__(self) -> None:
        self.calls: list = []

    def persist(self, *, result, inventory_id, aisle_id) -> PersistOutcome:
        self.calls.append(result)
        if result.status is ImageResultStatus.RESOLVED_INTERNAL:
            return PersistOutcome(
                persisted=True,
                reconciled=False,
                position_id=f"pos-{result.asset_id}",
                active_result_id=f"ar-{result.asset_id}",
            )
        return PersistOutcome(persisted=False, reconciled=False)


def _qr_png(payload: str) -> bytes:
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _real_strategy(content: bytes, events: list[str] | None = None):
    try:
        from src.infrastructure.code_scanning.pyzbar_code_scanner import PyzbarCodeScanner

        scanner = PyzbarCodeScanner()
    except Exception:  # pragma: no cover
        pytest.skip("pyzbar/libzbar not available")

    class _Capture:
        def publish(self, **kwargs):
            if events is not None:
                events.append(str(kwargs.get("event_type")))

    return CodeScanProcessingStrategy(
        scanner=scanner,
        content_reader=_FixedContentReader(content),
        parser=EncodedLabelPayloadParser(quantity_max=99999999, allow_decimal_quantity=False),
        consolidator=CodeDetectionConsolidator(),
        config=CodeScanConfig(quantity_max=99999999),
        event_publisher=_Capture() if events is not None else None,
    )


def _build(strategy, persister, *, concurrency: int = 1):
    clock = FixedClock()
    state_repo = MemoryJobAssetProcessingStateRepository()
    attempt_repo = MemoryProcessingAttemptRepository()
    lease_repo = MemoryJobProcessingLeaseRepository()
    batch_attempt_repo = MemoryBatchProcessingAttemptRepository()
    result_evidence_repo = MemoryResultEvidenceRepository()
    evidence_repo = MemoryEvidenceRepository()
    position_repo = MemoryPositionRepository()
    image_orch = ImageProcessingOrchestrator(
        state_repo, attempt_repo, clock, attempts_enabled=True
    )
    orch = AisleProcessingOrchestrator(
        state_repo=state_repo,
        attempt_repo=attempt_repo,
        lease_repo=lease_repo,
        batch_attempt_repo=batch_attempt_repo,
        clock=clock,
        image_orchestrator=image_orch,
        strategy_resolver=ProcessingStrategyResolver(),
        legacy_strategy=LegacyLlmProcessingStrategy(),
        coverage_resolver=AssetResultCoverageResolver(
            result_evidence_repo=result_evidence_repo,
            evidence_repo=evidence_repo,
            position_repo=position_repo,
        ),
        attempts_enabled=True,
        code_scan_strategy=strategy,
        result_persister=persister,
        code_scan_concurrency=concurrency,
    )
    return orch, state_repo, persister


def _job() -> Job:
    return Job(
        id="job-int-1",
        job_type="process_aisle",
        target_type="aisle",
        target_id="aisle-1",
        status=JobStatus.RUNNING,
        payload_json={"aisle_id": "aisle-1"},
        created_at=NOW,
        updated_at=NOW,
        identification_mode=AisleIdentificationMode.CODE_SCAN,
        identification_mode_source=AisleIdentificationModeSource.REQUEST,
        configuration_snapshot_version=CONFIGURATION_SNAPSHOT_VERSION,
        execution_strategy=AisleIdentificationExecutionStrategy.CODE_SCAN,
        provider_name=None,
        model_name=None,
        prompt_key=None,
    )


def _aisle() -> Aisle:
    return Aisle(
        id="aisle-1",
        inventory_id="inv-1",
        code="A1",
        status=AisleStatus.CREATED,
        created_at=NOW,
        updated_at=NOW,
    )


def _asset(aid: str = "s1") -> SourceAsset:
    return SourceAsset(
        id=aid,
        aisle_id="aisle-1",
        type=SourceAssetType.PHOTO,
        original_filename=f"{aid}.png",
        storage_path=f"/{aid}.png",
        mime_type="image/png",
        uploaded_at=NOW,
    )


def test_real_qr_through_orchestrator_resolves_and_persists() -> None:
    events: list[str] = []
    strategy = _real_strategy(_qr_png("INTPOS|9"), events=events)
    orch, state_repo, persister = _build(strategy, _RecordingPersister())

    outcome = orch.process_with_code_scan(
        job=_job(),
        aisle=_aisle(),
        assets=[_asset()],
        pipeline_enabled=True,
        orchestrator_enabled=True,
        is_cancelled=lambda: False,
        worker_token="w1",
    )

    assert outcome.ok is True
    assert outcome.assets_eligible == 1
    assert outcome.assets_started == 1
    assert outcome.progress.resolved == 1
    assert outcome.job_outcome.value == "SUCCEEDED"
    assert len(persister.calls) == 1
    assert persister.calls[0].internal_code == "INTPOS"
    assert int(persister.calls[0].quantity) == 9
    assert persister.calls[0].status is ImageResultStatus.RESOLVED_INTERNAL
    state = state_repo.get_by_job_and_asset("job-int-1", "s1")
    assert state is not None
    assert state.active_result_id == "ar-s1"
    assert "code_scan.asset_started" in events
    assert "code_scan.asset_finalized" in events


def test_real_blank_image_through_orchestrator_unrecognized() -> None:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color="white").save(buf, format="PNG")
    strategy = _real_strategy(buf.getvalue())
    orch, _, persister = _build(strategy, _RecordingPersister())

    outcome = orch.process_with_code_scan(
        job=_job(),
        aisle=_aisle(),
        assets=[_asset()],
        pipeline_enabled=True,
        orchestrator_enabled=True,
        is_cancelled=lambda: False,
        worker_token="w1",
    )

    assert outcome.progress.unrecognized == 1
    assert outcome.progress.resolved == 0
    assert all(
        c.status is not ImageResultStatus.RESOLVED_INTERNAL for c in persister.calls
    )
