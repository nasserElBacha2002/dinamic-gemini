"""Use-case tests for GetAisleOperationalPositioningView (detections_count compat)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.api.schemas.positioning_operational_schemas import view_to_response
from src.application.dto.access_principal import AccessPrincipal
from src.application.use_cases.positioning_operational.get_aisle_operational_view import (
    GetAisleOperationalPositioningViewCommand,
    GetAisleOperationalPositioningViewUseCase,
)
from src.domain.position_label_detection.entities import (
    ImagePositionLabelDetection,
    PositionLabelDetectionStatus,
    PositionLabelSignatureStatus,
)

NOW = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)


def _principal() -> AccessPrincipal:
    return AccessPrincipal(
        actor_id="u1",
        roles=frozenset({"operator"}),
        client_id="c1",
        is_platform=False,
    )


def _det(
    *,
    det_id: str,
    status: PositionLabelDetectionStatus,
    label_id: str | None = None,
) -> ImagePositionLabelDetection:
    return ImagePositionLabelDetection(
        id=det_id,
        client_id="c1",
        inventory_id="inv1",
        job_id="job1",
        source_asset_id="a1",
        detection_status=status,
        signature_status=PositionLabelSignatureStatus.VALID,
        payload_version=1,
        raw_payload_hash=None,
        detector_name="code_scan_shared",
        detector_version="1",
        created_at=NOW,
        updated_at=NOW,
        position_label_id=label_id,
    )


def _run_view(*, detections: list) -> object:
    status_uc = MagicMock()
    aisle = MagicMock()
    aisle.operational_job_id = "job1"
    latest = MagicMock()
    latest.id = "job1"
    latest.status = MagicMock()
    latest.status.value = "succeeded"
    status_uc.execute.return_value = MagicMock(
        aisle=aisle,
        latest_job=latest,
        recent_jobs=[latest],
    )

    inventory = MagicMock()
    inventory.client_id = "c1"
    inventory_repo = MagicMock()
    inventory_repo.get_by_id.return_value = inventory

    access = MagicMock()
    recon = MagicMock()
    recon.get_published_by_job.return_value = None
    recon.get_last_attempt_by_job.return_value = None
    recon.list_active_assignments.return_value = []

    det_repo = MagicMock()
    det_repo.list_by_job.return_value = detections

    link_repo = MagicMock()
    link_repo.list_for_job.return_value = []

    coverage = MagicMock()
    coverage.load_positions_for_assets.return_value = {}
    products = MagicMock()
    products.list_by_position_ids.return_value = []

    clock = MagicMock()
    clock.now.return_value = NOW

    processing = MagicMock()
    processing.state = "COMPLETED"
    processing.job_id = "job1"
    processing.can_start_new = True
    processing.recoverable = False
    processing.updated_at = NOW

    uc = GetAisleOperationalPositioningViewUseCase(
        status_use_case=status_uc,
        inventory_repo=inventory_repo,
        access_policy=access,
        reconciliation_repo=recon,
        detection_repo=det_repo,
        override_repo=None,
        label_repo=None,
        job_source_asset_repo=link_repo,
        coverage_repo=coverage,
        product_record_repo=products,
        clock=clock,
        operational_ux_enabled=True,
        reprocessing_enabled=True,
        recovery_enabled=True,
        overrides_enabled=False,
    )

    with patch(
        "src.application.use_cases.positioning_operational.get_aisle_operational_view.resolve_aisle_processing_state",
        return_value=processing,
    ):
        return uc.execute(
            GetAisleOperationalPositioningViewCommand(
                inventory_id="inv1",
                aisle_id="aisle1",
                principal=_principal(),
                job_id="job1",
            )
        )


def test_detections_count_is_total_persisted() -> None:
    detections = [
        _det(det_id="1", status=PositionLabelDetectionStatus.VALID, label_id="L1"),
        _det(det_id="2", status=PositionLabelDetectionStatus.NO_LABEL),
        _det(det_id="3", status=PositionLabelDetectionStatus.LABEL_NOT_FOUND),
    ]
    view = _run_view(detections=detections)
    assert view.detections_count == 3
    dto = view_to_response(view)
    assert dto.detections_count == 3


def test_warning_uses_resolved_count_when_none_resolved() -> None:
    detections = [
        _det(det_id="1", status=PositionLabelDetectionStatus.LABEL_NOT_FOUND),
        _det(det_id="2", status=PositionLabelDetectionStatus.NO_LABEL),
    ]
    # Force unassigned > 0 via assignment path when override_repo is None
    # assignments empty → unassigned 0. Patch build_operational_warnings call path
    # by injecting unassigned via assignments.
    status_uc = MagicMock()
    aisle = MagicMock()
    aisle.operational_job_id = "job1"
    latest = MagicMock()
    latest.id = "job1"
    status_uc.execute.return_value = MagicMock(
        aisle=aisle, latest_job=latest, recent_jobs=[latest]
    )
    inventory = MagicMock()
    inventory.client_id = "c1"
    inventory_repo = MagicMock()
    inventory_repo.get_by_id.return_value = inventory
    access = MagicMock()

    from src.domain.position_reconciliation.entities import (
        AssignmentStatus,
        ProductPositionAssignment,
    )

    assignment = ProductPositionAssignment(
        id="asg1",
        client_id="c1",
        inventory_id="inv1",
        job_id="job1",
        result_id="r1",
        source_asset_id="a1",
        ordered_capture_session_id=None,
        sequence_number=1,
        assignment_status=AssignmentStatus.UNASSIGNED_NO_PREVIOUS_POSITION,
        assignment_reason="NO_PREVIOUS",
        reconciliation_id="recon",
        reconciliation_version="1",
        created_at=NOW,
        updated_at=NOW,
    )
    recon = MagicMock()
    recon.get_published_by_job.return_value = None
    recon.get_last_attempt_by_job.return_value = None
    recon.list_active_assignments.return_value = [assignment]
    det_repo = MagicMock()
    det_repo.list_by_job.return_value = detections
    link_repo = MagicMock()
    link = MagicMock()
    link.source_asset_id = "a1"
    link_repo.list_for_job.return_value = [link]
    coverage = MagicMock()
    coverage.load_positions_for_assets.return_value = {}
    products = MagicMock()
    products.list_by_position_ids.return_value = []
    clock = MagicMock()
    clock.now.return_value = NOW
    processing = MagicMock()
    processing.state = "COMPLETED"
    processing.job_id = "job1"
    processing.can_start_new = True
    processing.recoverable = False
    processing.updated_at = NOW

    uc = GetAisleOperationalPositioningViewUseCase(
        status_use_case=status_uc,
        inventory_repo=inventory_repo,
        access_policy=access,
        reconciliation_repo=recon,
        detection_repo=det_repo,
        override_repo=None,
        label_repo=None,
        job_source_asset_repo=link_repo,
        coverage_repo=coverage,
        product_record_repo=products,
        clock=clock,
    )
    with patch(
        "src.application.use_cases.positioning_operational.get_aisle_operational_view.resolve_aisle_processing_state",
        return_value=processing,
    ):
        view = uc.execute(
            GetAisleOperationalPositioningViewCommand(
                inventory_id="inv1",
                aisle_id="aisle1",
                principal=_principal(),
                job_id="job1",
            )
        )
    assert view.detections_count == 2
    codes = {w.code for w in view.warnings}
    assert "NO_POSITION_LABEL_DETECTIONS" in codes


def test_total_gt_zero_resolved_gt_zero_no_empty_warning() -> None:
    detections = [
        _det(det_id="1", status=PositionLabelDetectionStatus.VALID, label_id="L1"),
        _det(det_id="2", status=PositionLabelDetectionStatus.NO_LABEL),
    ]
    from src.domain.position_reconciliation.entities import (
        AssignmentStatus,
        ProductPositionAssignment,
    )

    assignment = ProductPositionAssignment(
        id="asg1",
        client_id="c1",
        inventory_id="inv1",
        job_id="job1",
        result_id="r1",
        source_asset_id="a1",
        ordered_capture_session_id=None,
        sequence_number=1,
        assignment_status=AssignmentStatus.UNASSIGNED_NO_PREVIOUS_POSITION,
        assignment_reason="NO_PREVIOUS",
        reconciliation_id="recon",
        reconciliation_version="1",
        created_at=NOW,
        updated_at=NOW,
    )
    status_uc = MagicMock()
    aisle = MagicMock()
    aisle.operational_job_id = "job1"
    latest = MagicMock()
    latest.id = "job1"
    status_uc.execute.return_value = MagicMock(
        aisle=aisle, latest_job=latest, recent_jobs=[latest]
    )
    inventory = MagicMock()
    inventory.client_id = "c1"
    inventory_repo = MagicMock()
    inventory_repo.get_by_id.return_value = inventory
    access = MagicMock()
    recon = MagicMock()
    recon.get_published_by_job.return_value = None
    recon.get_last_attempt_by_job.return_value = None
    recon.list_active_assignments.return_value = [assignment]
    det_repo = MagicMock()
    det_repo.list_by_job.return_value = detections
    link_repo = MagicMock()
    link = MagicMock()
    link.source_asset_id = "a1"
    link_repo.list_for_job.return_value = [link]
    coverage = MagicMock()
    coverage.load_positions_for_assets.return_value = {}
    products = MagicMock()
    products.list_by_position_ids.return_value = []
    clock = MagicMock()
    clock.now.return_value = NOW
    processing = MagicMock()
    processing.state = "COMPLETED"
    processing.job_id = "job1"
    processing.can_start_new = True
    processing.recoverable = False
    processing.updated_at = NOW

    uc = GetAisleOperationalPositioningViewUseCase(
        status_use_case=status_uc,
        inventory_repo=inventory_repo,
        access_policy=access,
        reconciliation_repo=recon,
        detection_repo=det_repo,
        override_repo=None,
        label_repo=None,
        job_source_asset_repo=link_repo,
        coverage_repo=coverage,
        product_record_repo=products,
        clock=clock,
    )
    with patch(
        "src.application.use_cases.positioning_operational.get_aisle_operational_view.resolve_aisle_processing_state",
        return_value=processing,
    ):
        view = uc.execute(
            GetAisleOperationalPositioningViewCommand(
                inventory_id="inv1",
                aisle_id="aisle1",
                principal=_principal(),
                job_id="job1",
            )
        )
    assert view.detections_count == 2
    codes = {w.code for w in view.warnings}
    assert "NO_POSITION_LABEL_DETECTIONS" not in codes


def test_dto_compat_keeps_detections_count_field() -> None:
    view = _run_view(
        detections=[
            _det(det_id="1", status=PositionLabelDetectionStatus.VALID, label_id="L1"),
        ]
    )
    payload = view_to_response(view).model_dump()
    assert "detections_count" in payload
    assert payload["detections_count"] == 1
    assert "resolved_detections_count" not in payload
