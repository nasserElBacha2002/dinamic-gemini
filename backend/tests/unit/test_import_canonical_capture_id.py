"""Import canonical materialization must accept long mobile capture_photo_id values."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.dto.access_principal import AccessPrincipal
from src.application.services.import_canonical_position_materializer import (
    _command_for,
    materialization_capture_id,
)
from src.domain.local_csv_import.entities import LocalCsvProductiveResult
from src.domain.local_csv_import.sources import INGESTION_SOURCE_LOCAL_CSV_IMPORT
from src.domain.position_materialization.entities import MAX_ID_LENGTH
from src.domain.position_recognition.entities import PositionRecognitionSource

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)


def _result(**overrides: object) -> LocalCsvProductiveResult:
    base: dict[str, object] = dict(
        id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        inventory_id="inventory-1",
        aisle_id="aisle-1",
        import_id="import-1",
        import_row_id="row-1",
        capture_session_id="session-1",
        capture_photo_id="photo-1",
        client_file_id="file-1",
        capture_order=1,
        position_code="A04-R-02",
        internal_code="SKU1",
        quantity=1,
        quantity_status="PRESENT",
        detection_status="DETECTED",
        detection_source="LOCAL_CODE_SCAN",
        ingestion_source=INGESTION_SOURCE_LOCAL_CSV_IMPORT,
        requires_review=False,
        has_image_evidence=True,
        confirmed_by_user_id="user-1",
        created_at=NOW,
        updated_at=NOW,
        source_asset_id=None,
    )
    base.update(overrides)
    return LocalCsvProductiveResult(**base)  # type: ignore[arg-type]


def test_short_capture_photo_id_passthrough() -> None:
    result = _result(capture_photo_id="photo-1")
    assert materialization_capture_id(result) == "photo-1"


def test_prefers_source_asset_uuid_when_present() -> None:
    mobile_id = "a30062c7-ef22-41d7-99b8-e0e0fb893cb9:1000329869"
    asset = "11111111-2222-3333-4444-555555555555"
    result = _result(capture_photo_id=mobile_id, source_asset_id=asset)
    assert materialization_capture_id(result) == asset


def test_mobile_session_media_id_maps_to_uuid_length() -> None:
    mobile_id = "a30062c7-ef22-41d7-99b8-e0e0fb893cb9:1000329869"
    assert len(mobile_id) > MAX_ID_LENGTH
    result = _result(capture_photo_id=mobile_id)
    capture_id = materialization_capture_id(result)
    assert len(capture_id) == 36
    assert capture_id == materialization_capture_id(result)


def test_command_keeps_original_capture_photo_id_in_evidence() -> None:
    mobile_id = "a30062c7-ef22-41d7-99b8-e0e0fb893cb9:1000329869"
    result = _result(capture_photo_id=mobile_id)
    command = _command_for(
        result,
        normalized_code="A04-R-02",
        source=PositionRecognitionSource.CSV,
        principal=AccessPrincipal(
            actor_id="tester",
            client_id="client-1",
            roles=frozenset({"system"}),
            is_platform=False,
        ),
    )
    assert len(command.capture_id or "") <= MAX_ID_LENGTH
    assert command.recognition.evidence.get("capture_photo_id") == mobile_id


def test_command_stamps_aisle_client_supplier_id() -> None:
    result = _result()
    supplier = "c314c8c3-b6fd-490c-98dc-7b1ac40dca47"
    command = _command_for(
        result,
        normalized_code="A04-R-02",
        source=PositionRecognitionSource.CSV,
        principal=AccessPrincipal(
            actor_id="tester",
            client_id="client-1",
            roles=frozenset({"system"}),
            is_platform=False,
        ),
        client_supplier_id=supplier,
    )
    assert command.recognition.client_supplier_id == supplier


def test_materializer_resolves_supplier_from_aisle_repo() -> None:
    from unittest.mock import MagicMock

    from src.application.services.import_canonical_position_materializer import (
        ImportCanonicalPositionMaterializer,
    )
    from src.domain.aisle.entities import Aisle, AisleStatus
    from src.domain.position_materialization.entities import (
        MaterializePositionResult,
        PositionMaterializationStatus,
    )
    from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository

    aisle_repo = MemoryAisleRepository()
    supplier = "c314c8c3-b6fd-490c-98dc-7b1ac40dca47"
    aisle_repo.save(
        Aisle(
            id="aisle-1",
            inventory_id="inventory-1",
            code="02",
            status=AisleStatus.CREATED,
            created_at=NOW,
            updated_at=NOW,
            client_supplier_id=supplier,
        )
    )
    service = MagicMock()
    service.execute.return_value = MaterializePositionResult(
        status=PositionMaterializationStatus.MATERIALIZED,
        location_id="loc-1",
    )
    materializer = ImportCanonicalPositionMaterializer(
        materialize_service=service,
        enabled=True,
        aisle_repo=aisle_repo,
    )
    summary = materializer.materialize_from_results(
        [_result()],
        client_id="client-1",
        actor_id="tester",
    )
    assert summary.failed == 0
    assert summary.created_or_reused == 1
    command = service.execute.call_args.args[0]
    assert command.recognition.client_supplier_id == supplier
