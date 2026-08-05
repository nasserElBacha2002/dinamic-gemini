"""Use-case tests for GetAislePositioningSequence (P1 event semantics)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.api.schemas.positioning_operational_schemas import frame_to_dto
from src.application.dto.access_principal import AccessPrincipal
from src.application.services.positioning_operational.sequence_event_classifier import (
    PositionSequenceEventKind,
    PositionSequenceReasonCode,
)
from src.application.use_cases.positioning_operational.get_aisle_positioning_sequence import (
    GetAislePositioningSequenceCommand,
    GetAislePositioningSequenceUseCase,
)
from src.domain.position_label_detection.entities import (
    ImagePositionLabelDetection,
    PositionLabelDetectionStatus,
    PositionLabelSignatureStatus,
)
from src.domain.position_reconciliation.entities import (
    AssignmentStatus,
    ProductPositionAssignment,
)

NOW = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)


def _principal() -> AccessPrincipal:
    return AccessPrincipal(
        actor_id="u1",
        roles=frozenset({"operator"}),
        client_id="c1",
        is_platform=False,
    )


def _link(asset_id: str, seq: int, filename: str = "f.jpg") -> MagicMock:
    link = MagicMock()
    link.source_asset_id = asset_id
    link.sequence_number = seq
    link.position_order = seq
    link.original_filename = filename
    return link


def _det(
    *,
    det_id: str,
    asset_id: str,
    status: PositionLabelDetectionStatus,
    label_id: str | None = None,
    name: str | None = None,
) -> ImagePositionLabelDetection:
    return ImagePositionLabelDetection(
        id=det_id,
        client_id="c1",
        inventory_id="inv1",
        job_id="job1",
        source_asset_id=asset_id,
        detection_status=status,
        signature_status=PositionLabelSignatureStatus.VALID,
        payload_version=1,
        raw_payload_hash=None,
        detector_name="code_scan_shared",
        detector_version="1",
        created_at=NOW,
        updated_at=NOW,
        position_label_id=label_id,
        position_name_snapshot=name,
    )


def _assignment(
    *,
    asset_id: str,
    result_id: str = "result-1",
    reason: str = "LAST_VALID_POSITION",
    status: AssignmentStatus = AssignmentStatus.UNASSIGNED_NO_PREVIOUS_POSITION,
) -> ProductPositionAssignment:
    return ProductPositionAssignment(
        id=f"asg-{result_id}",
        client_id="c1",
        inventory_id="inv1",
        job_id="job1",
        result_id=result_id,
        source_asset_id=asset_id,
        ordered_capture_session_id=None,
        sequence_number=1,
        assignment_status=status,
        assignment_reason=reason,
        reconciliation_id="recon-1",
        reconciliation_version="1.0.0",
        created_at=NOW,
        updated_at=NOW,
    )


def _build_uc(
    *,
    links: list,
    detections: list,
    assignments: list | None = None,
) -> GetAislePositioningSequenceUseCase:
    aisle_repo = MagicMock()
    aisle = MagicMock()
    aisle.inventory_id = "inv1"
    aisle_repo.get_by_id.return_value = aisle

    job = MagicMock()
    job.target_type = "aisle"
    job.target_id = "aisle1"
    job_repo = MagicMock()
    job_repo.get_by_id.return_value = job

    access = MagicMock()
    recon = MagicMock()
    recon.list_active_assignments.return_value = assignments or []
    det_repo = MagicMock()
    det_repo.list_by_job.return_value = detections
    link_repo = MagicMock()
    link_repo.list_for_job.return_value = links
    coverage = MagicMock()
    coverage.load_positions_for_assets.return_value = {}
    products = MagicMock()
    products.list_by_position_ids.return_value = []

    return GetAislePositioningSequenceUseCase(
        aisle_repo=aisle_repo,
        job_repo=job_repo,
        access_policy=access,
        reconciliation_repo=recon,
        detection_repo=det_repo,
        job_source_asset_repo=link_repo,
        override_repo=None,
        label_repo=None,
        coverage_repo=coverage,
        product_record_repo=products,
    )


def test_sequence_does_not_depend_on_first_repo_detection_order() -> None:
    links = [_link("a1", 1)]
    # Put NO_LABEL first so asset_det[0] would wrongly pick no-symbol.
    detections = [
        _det(
            det_id="n",
            asset_id="a1",
            status=PositionLabelDetectionStatus.NO_LABEL,
        ),
        _det(
            det_id="v",
            asset_id="a1",
            status=PositionLabelDetectionStatus.VALID,
            label_id="L1",
            name="Pos A",
        ),
    ]
    uc = _build_uc(links=links, detections=detections)
    result = uc.execute(
        GetAislePositioningSequenceCommand(
            inventory_id="inv1",
            aisle_id="aisle1",
            principal=_principal(),
            job_id="job1",
        )
    )
    frame = result.items[0]
    assert frame.transition_action == PositionSequenceEventKind.POSITION_LABEL_RESOLVED.value
    assert frame.reason_code == PositionSequenceReasonCode.LABEL_RESOLVED.value
    assert frame.position_label_id == "L1"
    assert frame.transition_message == "Etiqueta de posicionamiento resuelta"


def test_assignment_reason_does_not_drive_transition() -> None:
    links = [_link("a1", 1)]
    detections = [
        _det(
            det_id="v",
            asset_id="a1",
            status=PositionLabelDetectionStatus.VALID,
            label_id="L1",
            name="A",
        )
    ]
    assignments = [
        _assignment(asset_id="a1", reason="LAST_VALID_POSITION"),
    ]
    uc = _build_uc(links=links, detections=detections, assignments=assignments)
    result = uc.execute(
        GetAislePositioningSequenceCommand(
            inventory_id="inv1",
            aisle_id="aisle1",
            principal=_principal(),
            job_id="job1",
        )
    )
    frame = result.items[0]
    assert frame.transition_action != "LAST_VALID_POSITION"
    assert frame.transition_action == PositionSequenceEventKind.POSITION_LABEL_RESOLVED.value
    assert "transición" not in (frame.transition_message or "").lower()


def test_snapshot_name_without_id_serializes_unresolved() -> None:
    links = [_link("a1", 1)]
    detections = [
        _det(
            det_id="v",
            asset_id="a1",
            status=PositionLabelDetectionStatus.VALID,
            label_id=None,
            name="NombreSinId",
        )
    ]
    uc = _build_uc(links=links, detections=detections)
    result = uc.execute(
        GetAislePositioningSequenceCommand(
            inventory_id="inv1",
            aisle_id="aisle1",
            principal=_principal(),
            job_id="job1",
        )
    )
    frame = result.items[0]
    dto = frame_to_dto(frame)
    assert dto.transition_action == PositionSequenceEventKind.POSITION_LABEL_UNRESOLVED.value
    assert dto.reason_code == PositionSequenceReasonCode.MISSING_POSITION_ID.value
    assert dto.position_detection_status == "VALID"
    assert dto.position_label_name == "NombreSinId"
    assert dto.position_label_id is None
    assert "MISSING_POSITION_ID" in (dto.transition_message or "")


def test_asset_without_detection_is_no_symbol() -> None:
    links = [_link("a1", 1)]
    uc = _build_uc(links=links, detections=[])
    result = uc.execute(
        GetAislePositioningSequenceCommand(
            inventory_id="inv1",
            aisle_id="aisle1",
            principal=_principal(),
            job_id="job1",
        )
    )
    frame = result.items[0]
    assert frame.transition_action == PositionSequenceEventKind.NO_POSITION_SYMBOL.value
    assert frame.transition_message is None
    assert frame.reason_code == PositionSequenceReasonCode.NO_SYMBOL.value


def test_multiple_detections_reduced_deterministically() -> None:
    links = [_link("a1", 1)]
    detections = [
        _det(
            det_id="b",
            asset_id="a1",
            status=PositionLabelDetectionStatus.VALID,
            label_id="L2",
            name="B",
        ),
        _det(
            det_id="a",
            asset_id="a1",
            status=PositionLabelDetectionStatus.VALID,
            label_id="L1",
            name="A",
        ),
    ]
    uc = _build_uc(links=links, detections=detections)
    result = uc.execute(
        GetAislePositioningSequenceCommand(
            inventory_id="inv1",
            aisle_id="aisle1",
            principal=_principal(),
            job_id="job1",
        )
    )
    frame = result.items[0]
    assert frame.transition_action == PositionSequenceEventKind.POSITION_LABEL_UNRESOLVED.value
    assert frame.reason_code == PositionSequenceReasonCode.AMBIGUOUS_DISTINCT_LABELS.value


def test_preserves_frame_order_by_sequence() -> None:
    links = [_link("a2", 2, "b.jpg"), _link("a1", 1, "a.jpg")]
    uc = _build_uc(links=links, detections=[])
    result = uc.execute(
        GetAislePositioningSequenceCommand(
            inventory_id="inv1",
            aisle_id="aisle1",
            principal=_principal(),
            job_id="job1",
        )
    )
    assert [f.source_asset_id for f in result.items] == ["a1", "a2"]
    assert [f.sequence_number for f in result.items] == [1, 2]
