from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pyodbc
import pytest

from src.application.services.position_materialization import (
    PositionMaterializationCoordinator,
    PreparationStatus,
    PrepareMaterialization,
)
from src.domain.image_processing.contracts import (
    ImageProcessingResult,
    ImageResultStatus,
)
from src.domain.position_label_detection.entities import (
    ImagePositionLabelDetection,
    PositionLabelDetectionStatus,
    PositionLabelSignatureStatus,
)
from src.domain.position_materialization.entities import (
    MaterializePositionResult,
    PositionMaterializationStatus,
)
from src.infrastructure.repositories.memory_image_position_label_detection_repository import (
    MemoryImagePositionLabelDetectionRepository,
)

NOW = datetime(2026, 9, 8, tzinfo=timezone.utc)


class _Clock:
    def now(self) -> datetime:
        return NOW


def _result() -> ImageProcessingResult:
    return ImageProcessingResult(
        job_id="job-1",
        asset_id="asset-1",
        status=ImageResultStatus.RESOLVED_EXTERNAL,
        processing_mode="EXTERNAL_PROVIDER",
        evidence={
            "result_kind": "POSITION_ONLY",
            "position_label_detection": {
                "recognition_source": "VISION",
                "client_id": "client-1",
                "normalized_positions": [{"position_id": "A04-R-02"}],
            },
        },
    )


def _code_result() -> ImageProcessingResult:
    return ImageProcessingResult(
        job_id="job-1",
        asset_id="asset-1",
        status=ImageResultStatus.RESOLVED_INTERNAL,
        processing_mode="CODE_SCAN",
        evidence={"result_kind": "POSITION_ONLY"},
    )


def _detection(code: str, raw_hash: str) -> ImagePositionLabelDetection:
    return ImagePositionLabelDetection(
        id=f"detection-{code}",
        client_id="client-1",
        inventory_id="inventory-1",
        job_id="job-1",
        source_asset_id="asset-1",
        detection_status=PositionLabelDetectionStatus.VALID,
        signature_status=PositionLabelSignatureStatus.SKIPPED,
        payload_version=None,
        raw_payload_hash=raw_hash,
        detector_name="code_scan",
        detector_version="supplier-v1",
        created_at=NOW,
        updated_at=NOW,
        public_identifier=code,
    )


def test_malformed_legacy_vision_evidence_fails_closed_without_writes() -> None:
    repo = MagicMock()
    materializer = MagicMock()
    coordinator = PositionMaterializationCoordinator(
        clock=_Clock(),
        detection_repo=repo,
        materializer=materializer,
        enabled=True,
    )

    prepared = coordinator.prepare(
        PrepareMaterialization(
            result=_result(),
            inventory_id="inventory-1",
            aisle_id="aisle-1",
            snapshot=SimpleNamespace(position_order=0),
        )
    )

    assert prepared.status is PreparationStatus.INVALID_EVIDENCE
    repo.replace_asset_detections_atomically.assert_not_called()
    materializer.execute.assert_not_called()


@pytest.mark.parametrize(
    "repository_error",
    [
        TimeoutError("repository timeout secret-raw-value"),
        pyodbc.OperationalError("database unavailable secret-raw-value"),
    ],
)
def test_repository_operational_failure_returns_typed_retry(
    repository_error: Exception,
    caplog,
) -> None:
    repo = MagicMock()
    repo.list_by_asset.side_effect = repository_error
    coordinator = PositionMaterializationCoordinator(
        clock=_Clock(),
        detection_repo=repo,
        materializer=MagicMock(),
        enabled=True,
    )

    prepared = coordinator.prepare(
        PrepareMaterialization(
            result=_code_result(),
            inventory_id="inventory-1",
            aisle_id="aisle-1",
            snapshot=SimpleNamespace(position_order=0),
        )
    )

    assert prepared.status is PreparationStatus.TECHNICAL_RETRY
    assert prepared.technical_cause is repository_error
    assert "secret-raw-value" not in caplog.text


def test_repository_programming_error_is_not_hidden() -> None:
    repo = MagicMock()
    repo.list_by_asset.side_effect = RuntimeError("malformed repository row")
    coordinator = PositionMaterializationCoordinator(
        clock=_Clock(),
        detection_repo=repo,
        materializer=MagicMock(),
        enabled=True,
    )

    with pytest.raises(RuntimeError, match="malformed repository row"):
        coordinator.prepare(
            PrepareMaterialization(
                result=_code_result(),
                inventory_id="inventory-1",
                aisle_id="aisle-1",
                snapshot=SimpleNamespace(position_order=0),
            )
        )


def test_true_empty_repository_result_is_invalid_evidence() -> None:
    repo = MagicMock()
    repo.list_by_asset.return_value = []
    coordinator = PositionMaterializationCoordinator(
        clock=_Clock(),
        detection_repo=repo,
        materializer=MagicMock(),
        enabled=True,
    )

    prepared = coordinator.prepare(
        PrepareMaterialization(
            result=_code_result(),
            inventory_id="inventory-1",
            aisle_id="aisle-1",
            snapshot=SimpleNamespace(position_order=0),
        )
    )

    assert prepared.status is PreparationStatus.INVALID_EVIDENCE
    assert prepared.technical_cause is None


def test_partial_materialization_compensates_completed_requests() -> None:
    repo = MemoryImagePositionLabelDetectionRepository()
    repo.replace_asset_detections_atomically(
        job_id="job-1",
        source_asset_id="asset-1",
        detector_version="supplier-v1",
        detections=[
            _detection("A04-R-02", "hash-1"),
            _detection("A04-R-03", "hash-2"),
        ],
    )
    materializer = MagicMock()
    materializer.execute.side_effect = [
        MaterializePositionResult(
            status=PositionMaterializationStatus.MATERIALIZED,
            location_id="location-1",
            request_id="request-1",
        ),
        MaterializePositionResult(
            status=PositionMaterializationStatus.RETRYABLE_FAILURE,
        ),
    ]
    coordinator = PositionMaterializationCoordinator(
        clock=_Clock(),
        detection_repo=repo,
        materializer=materializer,
        enabled=True,
    )
    result = _code_result()

    prepared = coordinator.prepare(
        PrepareMaterialization(
            result=result,
            inventory_id="inventory-1",
            aisle_id="aisle-1",
            snapshot=SimpleNamespace(position_order=0),
        )
    )

    assert prepared.status is PreparationStatus.MATERIALIZATION_FAILED
    materializer.complete_association.assert_called_once_with(
        "request-1",
        success=False,
        error_code="IMAGE_MATERIALIZATION_PARTIAL_FAILURE",
        now=NOW,
    )
