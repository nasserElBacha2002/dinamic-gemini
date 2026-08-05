"""Contract serialization for positioning sequence + operational view (P1 fields)."""

from __future__ import annotations

from src.api.schemas.positioning_operational_schemas import frame_to_dto, view_to_response
from src.domain.positioning_operational.entities import (
    AisleOperationalPositioningView,
    PositioningAllowedActions,
    PositioningSequenceFrame,
)


def test_sequence_frame_json_includes_event_kind_and_reason() -> None:
    frame = PositioningSequenceFrame(
        sequence_number=1,
        source_asset_id="asset-1",
        filename="a.jpg",
        position_detection_status="VALID",
        position_label_name="Pos A",
        transition_action="POSITION_LABEL_RESOLVED",
        transition_message="Etiqueta de posicionamiento resuelta",
        product_count=0,
        reason_code="LABEL_RESOLVED",
        position_label_id="label-1",
    )
    payload = frame_to_dto(frame).model_dump()
    assert payload["transition_action"] == "POSITION_LABEL_RESOLVED"
    assert payload["transition_message"] == "Etiqueta de posicionamiento resuelta"
    assert payload["reason_code"] == "LABEL_RESOLVED"
    assert payload["position_detection_status"] == "VALID"
    assert payload["position_label_id"] == "label-1"


def test_sequence_unresolved_missing_id_contract() -> None:
    frame = PositioningSequenceFrame(
        sequence_number=2,
        source_asset_id="asset-2",
        filename="b.jpg",
        position_detection_status="VALID",
        position_label_name="SoloNombre",
        transition_action="POSITION_LABEL_UNRESOLVED",
        transition_message=(
            "Etiqueta de posicionamiento detectada, pero no resuelta. Motivo: MISSING_POSITION_ID"
        ),
        product_count=0,
        reason_code="MISSING_POSITION_ID",
        position_label_id=None,
    )
    payload = frame_to_dto(frame).model_dump()
    assert payload["transition_action"] == "POSITION_LABEL_UNRESOLVED"
    assert "MISSING_POSITION_ID" in payload["transition_message"]
    assert payload["reason_code"] == "MISSING_POSITION_ID"
    assert payload["position_label_id"] is None


def test_operational_view_detections_count_contract() -> None:
    view = AisleOperationalPositioningView(
        inventory_id="inv1",
        aisle_id="aisle1",
        client_id="c1",
        processing_state="COMPLETED",
        active_job_id=None,
        result_job_id="job1",
        reconciliation_status=None,
        reconciliation_id=None,
        reconciliation_version=None,
        total_results=0,
        assigned_results=0,
        unassigned_results=0,
        assigned_automatic=0,
        assigned_manual=0,
        unassigned_automatic=0,
        unassigned_manual=0,
        manual_overrides_count=0,
        invalid_positions_count=0,
        stale_results_count=0,
        unordered_assets_count=0,
        ambiguous_detections_count=0,
        detections_count=5,
        recoverable=False,
        can_process=True,
        can_reprocess=True,
        can_recover=False,
        can_review=True,
        can_correct=False,
        allowed_actions=PositioningAllowedActions(
            process=True,
            reprocess=True,
            recover=False,
            review=True,
            correct_position=False,
            restore_automatic=False,
            reconcile_only=False,
        ),
    )
    payload = view_to_response(view).model_dump()
    assert payload["detections_count"] == 5
    assert "resolved_detections_count" not in payload
