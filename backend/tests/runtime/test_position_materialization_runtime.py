"""Runtime wiring tests for repository-backed position materialization."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.api import dependencies
from src.application.dto.access_principal import AccessPrincipal
from src.application.services.position_materialization import MaterializePositionCommand
from src.application.services.position_reconciliation.sequential_reconciler import (
    SequentialPositionReconciler,
)
from src.config import AppSettings
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.position_materialization.entities import (
    PositionMaterializationAssociationReceipt,
)
from src.domain.position_recognition.entities import (
    CanonicalPositionRecognition,
    PositionRecognitionSource,
)
from src.domain.position_reconciliation.entities import (
    AssignmentStatus,
    ItemResultRef,
    OrderedImageFrame,
    PositionDetectionRef,
)
from src.infrastructure.persistence.memory_position_materialization_unit_of_work import (
    MemoryPositionMaterializationUnitOfWork,
)
from src.infrastructure.persistence.position_materialization_schema_verifier import (
    SCHEMA_PRECONDITION_ERROR,
    PositionMaterializationSchemaError,
)
from src.observability.runtime_wiring import (
    stop_position_materialization_recovery_scheduler,
    wire_position_materialization_recovery_scheduler,
)
from src.runtime import app_container as app_container_module
from src.runtime.app_container import AppContainer


def _container(*, recovery_enabled: bool = False) -> AppContainer:
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    container = AppContainer(
        AppSettings(
            sqlserver_enabled=False,
            position_auto_materialization_enabled=False,
            position_materialization_recovery_enabled=recovery_enabled,
        )
    )
    container.get_inventory_repo().save(
        Inventory(
            id="inventory-1",
            name="Inventory",
            client_id="client-1",
            status=InventoryStatus.PROCESSING,
            created_at=now,
            updated_at=now,
        )
    )
    container.get_aisle_repo().save(
        Aisle(
            id="aisle-1",
            inventory_id="inventory-1",
            code="A-01",
            status=AisleStatus.PROCESSING,
            client_supplier_id=None,
            created_at=now,
            updated_at=now,
        )
    )
    return container


def test_memory_runtime_materialization_is_visible_through_location_repository() -> None:
    container = _container()
    service = container.get_position_materialization_service()

    result = service.execute(
        MaterializePositionCommand(
            recognition=CanonicalPositionRecognition(
                raw_code="A-01",
                normalized_code="A-01",
                source=PositionRecognitionSource.CODE_SCAN,
            ),
            inventory_id="inventory-1",
            aisle_id="aisle-1",
            principal=AccessPrincipal(
                actor_id="system:position-materializer",
                client_id="client-1",
                roles=frozenset({"system"}),
                is_platform=False,
            ),
            idempotency_key="runtime-location-visible",
            capture_id="asset-1",
        )
    )

    visible = container.get_aisle_location_repo().list_by_aisle("aisle-1")
    assert result.accepted
    assert len(visible) == 1
    assert visible[0].id == result.location_id
    assert visible[0].normalized_code == "A-01"


def test_container_owns_service_and_isolates_multiple_instances() -> None:
    first = _container()
    second = _container()

    assert (
        first.get_position_materialization_service() is first.get_position_materialization_service()
    )
    assert (
        first.get_position_materialization_service()
        is not second.get_position_materialization_service()
    )
    assert first.get_position_materialization_uow() is not second.get_position_materialization_uow()

    first.close()
    rebuilt = first.get_position_materialization_service()
    assert rebuilt is not second.get_position_materialization_service()


def _associate_detection(container: AppContainer, detection_id: str):
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    result = container.get_position_materialization_service().execute(
        MaterializePositionCommand(
            recognition=CanonicalPositionRecognition(
                raw_code="A04-R-02",
                normalized_code="A04-R-02",
                source=PositionRecognitionSource.VISION,
            ),
            inventory_id="inventory-1",
            aisle_id="aisle-1",
            principal=AccessPrincipal(
                actor_id="system:position-materializer",
                client_id="client-1",
                roles=frozenset({"system"}),
                is_platform=False,
            ),
            idempotency_key=f"identity-{detection_id}",
        )
    )
    assert result.request_id is not None
    materialization_uow = container.get_position_materialization_uow()
    assert isinstance(materialization_uow, MemoryPositionMaterializationUnitOfWork)
    materialization_uow.association_receipt_repository.save(
        PositionMaterializationAssociationReceipt(
            request_id=result.request_id,
            target_type="IMAGE_RESULT",
            target_id=f"evidence-{detection_id}",
            created_at=now,
            source_detection_id=detection_id,
        )
    )
    container.get_position_materialization_service().complete_association(
        result.request_id, success=True, now=now
    )
    return result


def test_memory_identity_state_is_shared_isolated_and_reconciles() -> None:
    first = _container()
    second = _container()
    result = _associate_detection(first, "detection-1")

    first_uow = first.get_position_materialization_uow()
    assert isinstance(first_uow, MemoryPositionMaterializationUnitOfWork)
    manual_repositories = first.get_manual_image_result_uow_factory()().repositories
    assert (
        manual_repositories.materialization_receipt_repo is first_uow.association_receipt_repository
    )

    first_reader = first.get_materialized_position_identity_reader()
    second_reader = second.get_materialized_position_identity_reader()
    identities = first_reader.read_by_detection_ids(
        ["detection-1"],
        client_id="client-1",
        inventory_id="inventory-1",
        aisle_id="aisle-1",
    )
    assert identities["detection-1"].aisle_location_id == result.location_id
    assert (
        second_reader.read_by_detection_ids(
            ["detection-1"],
            client_id="client-1",
            inventory_id="inventory-1",
            aisle_id="aisle-1",
        )
        == {}
    )

    decision = SequentialPositionReconciler().reconcile(
        [
            OrderedImageFrame(
                source_asset_id="position-image",
                ordered_capture_session_id=None,
                sequence_number=0,
                position_detections=(
                    PositionDetectionRef(
                        id="detection-1",
                        client_id="client-1",
                        detection_status="VALID",
                        signature_status="SKIPPED",
                        aisle_location_id=identities["detection-1"].aisle_location_id,
                        position_name_snapshot="A04-R-02",
                    ),
                ),
            ),
            OrderedImageFrame(
                source_asset_id="product-image",
                ordered_capture_session_id=None,
                sequence_number=1,
                item_results=(ItemResultRef("result-1"),),
            ),
        ],
        expected_client_id="client-1",
    )[0]
    assert decision.assignment_status is AssignmentStatus.ASSIGNED_AUTOMATIC
    assert decision.aisle_location_id == result.location_id


def test_close_is_idempotent_across_repeated_cycles() -> None:
    container = _container()
    for _ in range(3):
        service = container.get_position_materialization_service()
        container.close()
        assert container._position_materialization_service is None
        assert container.get_position_materialization_service() is not service


def test_api_dependency_returns_container_owned_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    container = _container()
    monkeypatch.setattr(dependencies, "get_app_container", lambda: container)

    service = dependencies.get_position_materialization_service(
        inventory_repo=container.get_inventory_repo(),
        aisle_repo=container.get_aisle_repo(),
        clock=container.get_clock(),
    )

    assert service is container.get_position_materialization_service()


def test_recovery_scheduler_starts_and_container_close_stops_it() -> None:
    container = _container(recovery_enabled=True)
    scheduler = container.start_position_materialization_recovery_scheduler()

    assert scheduler is not None
    assert scheduler._thread is not None
    assert scheduler._thread.is_alive()

    container.close()
    assert not scheduler._thread.is_alive()


def test_recovery_scheduler_creates_no_thread_when_disabled() -> None:
    container = _container()

    assert container.start_position_materialization_recovery_scheduler() is None
    assert container._position_materialization_recovery_scheduler is None


def test_recovery_only_sql_mode_verifies_schema_before_uow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    container = _container(recovery_enabled=True)
    verify = MagicMock()
    monkeypatch.setattr(container, "is_sql_repository_backend", lambda: True)
    monkeypatch.setattr(container, "_get_v3_sql_client", MagicMock())
    monkeypatch.setattr(
        app_container_module.SqlPositionMaterializationSchemaVerifier,
        "verify",
        verify,
    )

    container.get_position_materialization_uow()

    verify.assert_called_once_with()


def test_recovery_scheduler_fails_closed_before_start_for_bad_sql_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    container = _container(recovery_enabled=True)
    monkeypatch.setattr(container, "is_sql_repository_backend", lambda: True)
    monkeypatch.setattr(container, "_get_v3_sql_client", MagicMock())
    monkeypatch.setattr(
        app_container_module.SqlPositionMaterializationSchemaVerifier,
        "verify",
        MagicMock(side_effect=PositionMaterializationSchemaError()),
    )

    with pytest.raises(PositionMaterializationSchemaError) as exc:
        container.start_position_materialization_recovery_scheduler()

    assert str(exc.value) == SCHEMA_PRECONDITION_ERROR
    assert container._position_materialization_recovery_scheduler is None


def test_observability_startup_and_shutdown_own_scheduler_lifecycle() -> None:
    container = _container(recovery_enabled=True)

    scheduler = wire_position_materialization_recovery_scheduler(container)
    assert scheduler is not None
    assert scheduler._thread is not None and scheduler._thread.is_alive()

    stop_position_materialization_recovery_scheduler(container)
    assert not scheduler._thread.is_alive()
    assert container._position_materialization_recovery_scheduler is None
