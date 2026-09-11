from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from src.application.dto.access_principal import AccessPrincipal
from src.application.dto.position_materialization import (
    POSITION_MATERIALIZATION_FINGERPRINT_VERSION,
    build_fingerprint_v1,
)
from src.application.services.position_materialization import (
    MaterializePositionCommand,
    MaterializePositionService,
)
from src.domain.aisle_location.entities import AisleLocation, AisleLocationStatus
from src.domain.position_materialization import (
    PositionMaterializationAssociationStatus,
    PositionMaterializationStatus,
)
from src.domain.position_materialization.errors import PositionMaterializationConflictError
from src.domain.position_recognition.entities import (
    CanonicalPositionRecognition,
    PositionRecognitionSource,
)
from src.infrastructure.persistence.memory_position_materialization_unit_of_work import (
    MemoryMaterializationAisle,
    MemoryMaterializationInventory,
    MemoryMaterializationRequest,
    MemoryMaterializedLocation,
    MemoryPositionMaterializationUnitOfWork,
)
from src.infrastructure.repositories.memory_aisle_location_repository import (
    MemoryAisleLocationRepository,
)
from src.observability.metrics.instruments import POSITION_MATERIALIZATION_TOTAL
from src.observability.metrics.registry import get_metrics_registry

NOW = datetime(2026, 9, 8, tzinfo=timezone.utc)


def _recognition(**overrides: object) -> CanonicalPositionRecognition:
    values: dict[str, object] = {
        "raw_code": "  rack-a / 01  ",
        "normalized_code": "RACK-A/01",
        "source": PositionRecognitionSource.CODE_SCAN,
        "pallet": "A",
        "side": "LEFT",
        "level": 1,
        "marker_index": 1,
        "marker_total": 2,
        "profile_id": "profile-1",
        "profile_version": 3,
        "client_supplier_id": "supplier-1",
    }
    values.update(overrides)
    return CanonicalPositionRecognition(**values)  # type: ignore[arg-type]


def _command(
    *,
    key: str = "request-1",
    recognition: CanonicalPositionRecognition | None = None,
    client_id: str | None = "client-1",
    inventory_id: str = "inventory-1",
    aisle_id: str = "aisle-1",
    actor_id: str = "user-1",
) -> MaterializePositionCommand:
    return MaterializePositionCommand(
        recognition=recognition or _recognition(),
        inventory_id=inventory_id,
        aisle_id=aisle_id,
        principal=AccessPrincipal(
            actor_id=actor_id,
            client_id=client_id,
            roles=frozenset({"operator"}),
            is_platform=False,
        ),
        idempotency_key=key,
        capture_id="capture-1",
    )


def _uow(*, status: str = "processing") -> MemoryPositionMaterializationUnitOfWork:
    return MemoryPositionMaterializationUnitOfWork(
        inventories=[
            MemoryMaterializationInventory(
                id="inventory-1",
                client_id="client-1",
                status=status,
            )
        ],
        aisles=[
            MemoryMaterializationAisle(
                id="aisle-1",
                inventory_id="inventory-1",
                client_supplier_id="supplier-1",
            )
        ],
    )


def _service(uow: MemoryPositionMaterializationUnitOfWork) -> MaterializePositionService:
    return MaterializePositionService(uow, clock=lambda: NOW)


def _metric_labels(outcome: str, reason_code: str = "none") -> dict[str, str]:
    return {
        "component": "service",
        "source": "CODE_SCAN",
        "mode": "SUPPLIER",
        "outcome": outcome,
        "reason_code": reason_code,
    }


def test_materializes_and_preserves_raw_recognition_evidence() -> None:
    uow = _uow()
    result = _service(uow).execute(_command())

    assert result.status is PositionMaterializationStatus.MATERIALIZED
    assert result.idempotent_replay is False
    location = uow.locations[result.location_id or ""]
    assert location.normalized_code == "RACK-A/01"
    assert location.raw_recognition_code == "  rack-a / 01  "
    assert location.creation_source == "AUTO"
    assert len(uow.requests) == 1


def test_materialization_service_records_exact_created_replay_and_pending_metrics() -> None:
    registry = get_metrics_registry()
    registry.reset_for_tests()
    service = _service(_uow())

    service.execute(_command())
    service.execute(_command())

    assert (
        registry.get_counter_value(POSITION_MATERIALIZATION_TOTAL, _metric_labels("created")) == 1.0
    )
    assert (
        registry.get_counter_value(
            POSITION_MATERIALIZATION_TOTAL,
            _metric_labels("idempotent_replay"),
        )
        == 1.0
    )
    assert (
        registry.get_counter_value(
            POSITION_MATERIALIZATION_TOTAL,
            _metric_labels("association_pending"),
        )
        == 2.0
    )
    rendered = registry.render_prometheus()
    assert "RACK-A/01" not in rendered
    assert "client-1" not in rendered
    registry.reset_for_tests()


def test_materialization_service_records_reused_conflict_validation_and_review() -> None:
    registry = get_metrics_registry()
    registry.reset_for_tests()
    service = _service(_uow())

    created = service.execute(_command(key="created"))
    service.execute(_command(key="reused"))
    service.execute(
        _command(
            key="created",
            recognition=_recognition(normalized_code="DIFFERENT"),
        )
    )
    service.execute(
        _command(
            key="identity-conflict",
            recognition=_recognition(level=2),
        )
    )
    service.execute(_command(key="invalid", recognition=_recognition(source="INVALID")))
    assert created.request_id is not None
    service.complete_association(
        created.request_id,
        success=False,
        error_code="DOWNSTREAM_FAILED",
    )

    expected = (
        ("reused", "none"),
        ("idempotency_conflict", "idempotency_conflict"),
        ("identity_conflict", "identity_conflict"),
    )
    for outcome, reason in expected:
        assert (
            registry.get_counter_value(
                POSITION_MATERIALIZATION_TOTAL,
                _metric_labels(outcome, reason),
            )
            == 1.0
        )
    validation_labels = {
        **_metric_labels("validation_rejected", "invalid_request"),
        "source": "API",
    }
    assert (
        registry.get_counter_value(
            POSITION_MATERIALIZATION_TOTAL,
            validation_labels,
        )
        == 1.0
    )
    review_labels = {
        "component": "service",
        "source": "API",
        "mode": "DINAMIC",
        "outcome": "requires_review",
        "reason_code": "downstream_requires_review",
    }
    assert registry.get_counter_value(POSITION_MATERIALIZATION_TOTAL, review_labels) == 1.0
    registry.reset_for_tests()


def test_two_requests_reuse_one_location() -> None:
    uow = _uow()
    service = _service(uow)

    first = service.execute(_command(key="one"))
    second = service.execute(_command(key="two"))

    assert first.status is PositionMaterializationStatus.MATERIALIZED
    assert second.status is PositionMaterializationStatus.REUSED
    assert first.idempotent_replay is False
    assert second.idempotent_replay is False
    assert second.location_id == first.location_id
    assert len(uow.locations) == 1
    assert len(uow.requests) == 2


def test_replay_only_lookup_never_creates_and_rejects_hash_mismatch() -> None:
    uow = _uow()
    service = _service(uow)
    command = _command()

    assert service.lookup_replay(command) is None
    assert uow.locations == {}
    assert uow.requests == {}

    created = service.execute(command)
    replay = service.lookup_replay(command)
    assert replay is not None
    assert replay.request_id == created.request_id
    assert replay.idempotent_replay is True
    with pytest.raises(PositionMaterializationConflictError) as exc:
        service.lookup_replay(_command(recognition=_recognition(raw_code="different evidence")))
    assert exc.value.code == "IDEMPOTENCY_KEY_CONFLICT"
    assert len(uow.locations) == 1
    assert len(uow.requests) == 1


def test_committed_replay_succeeds_after_inventory_closes() -> None:
    uow = _uow()
    service = _service(uow)
    command = _command()
    first = service.execute(command)
    uow.inventories["inventory-1"] = replace(
        uow.inventories["inventory-1"],
        status="completed",
    )

    replay = service.execute(command)

    assert replay.status is first.status
    assert replay.location_id == first.location_id
    assert replay.request_id == first.request_id
    assert replay.idempotent_replay is True


def test_historical_v1_fingerprint_replays() -> None:
    uow = _uow()
    service = _service(uow)
    command = _command()
    created = service.execute(command)
    request = uow.requests[("client-1", "request-1")]

    assert request.fingerprint_version == POSITION_MATERIALIZATION_FINGERPRINT_VERSION
    assert service.execute(command).request_id == created.request_id


def test_unsupported_fingerprint_version_is_invariant() -> None:
    uow = _uow()
    service = _service(uow)
    command = _command()
    service.execute(command)
    key = ("client-1", "request-1")
    request: MemoryMaterializationRequest = uow.requests[key]
    uow.requests[key] = replace(request, fingerprint_version=99)

    result = service.execute(command)

    assert result.status is PositionMaterializationStatus.INVARIANT_VIOLATION
    assert result.error_code == "UNSUPPORTED_MATERIALIZATION_FINGERPRINT_VERSION"


def test_same_key_with_different_payload_conflicts() -> None:
    uow = _uow()
    service = _service(uow)
    service.execute(_command())

    result = service.execute(_command(recognition=_recognition(raw_code="different evidence")))

    assert result.status is PositionMaterializationStatus.REJECTED_IDEMPOTENCY_CONFLICT
    assert result.error_code == "IDEMPOTENCY_KEY_CONFLICT"


def test_fingerprint_v1_excludes_actor_and_opaque_evidence() -> None:
    first = _command(
        recognition=_recognition(evidence={"score": 0.9, "diagnostic": "first"}),
        actor_id="user-1",
    )
    second = _command(
        recognition=_recognition(evidence={"diagnostic": "second", "score": 0.1}),
        actor_id="user-2",
    )

    assert build_fingerprint_v1(first).version == POSITION_MATERIALIZATION_FINGERPRINT_VERSION
    from src.application.services.position_materialization import canonical_request_fingerprint

    assert canonical_request_fingerprint(first) == canonical_request_fingerprint(second)


def test_fingerprint_changes_for_functional_field() -> None:
    from src.application.services.position_materialization import canonical_request_fingerprint

    first = canonical_request_fingerprint(_command())
    changed = canonical_request_fingerprint(_command(recognition=_recognition(marker_total=3)))

    assert first != changed


def test_invalid_functional_fingerprint_field_is_validation_rejection() -> None:
    command = _command(recognition=_recognition(source="CODE_SCAN"))

    result = _service(_uow()).execute(command)

    assert result.status is PositionMaterializationStatus.REJECTED_VALIDATION
    assert result.error_code == "INVALID_MATERIALIZATION_REQUEST"


@pytest.mark.parametrize(
    ("command", "expected_code"),
    [
        (_command(client_id="other-client"), "INVENTORY_SCOPE_MISMATCH"),
        (_command(inventory_id="other-inventory"), "INVENTORY_SCOPE_MISMATCH"),
        (_command(aisle_id="other-aisle"), "AISLE_SCOPE_MISMATCH"),
        (
            _command(recognition=_recognition(client_supplier_id="other-supplier")),
            "SUPPLIER_SCOPE_MISMATCH",
        ),
    ],
)
def test_rejects_scope_mismatches(
    command: MaterializePositionCommand,
    expected_code: str,
) -> None:
    result = _service(_uow()).execute(command)

    assert result.status is PositionMaterializationStatus.REJECTED_SCOPE
    assert result.error_code == expected_code


def test_rejects_closed_inventory_for_new_request() -> None:
    result = _service(_uow(status="completed")).execute(_command())

    assert result.status is PositionMaterializationStatus.REJECTED_INVENTORY_STATE


def test_rejects_inactive_aisle() -> None:
    uow = _uow()
    uow.aisles["aisle-1"] = replace(uow.aisles["aisle-1"], is_active=False)

    result = _service(uow).execute(_command())

    assert result.status is PositionMaterializationStatus.REJECTED_SCOPE
    assert result.error_code == "AISLE_INACTIVE"


def test_rejects_inactive_canonical_identity() -> None:
    uow = _uow()
    uow.add_location(
        MemoryMaterializedLocation(
            id="location-old",
            public_identifier="loc_old",
            client_id="client-1",
            aisle_id="aisle-1",
            code="RACK-A/01",
            normalized_code="RACK-A/01",
            status="INACTIVE",
            created_by="user-old",
            created_at=NOW,
            updated_at=NOW,
        )
    )

    result = _service(uow).execute(_command())

    assert result.status is PositionMaterializationStatus.REJECTED_IDENTITY_CONFLICT
    assert result.error_code == "INACTIVE_POSITION_IDENTITY"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("profile_id", "other-profile"),
        ("profile_version", 9),
        ("pallet", "B"),
        ("side", "RIGHT"),
        ("level", 2),
        ("marker_index", 2),
        ("marker_total", 3),
    ],
)
def test_rejects_contradictory_existing_provenance(field: str, value: object) -> None:
    uow = _uow()
    first = _service(uow).execute(_command())

    result = _service(uow).execute(
        _command(key="second", recognition=_recognition(**{field: value}))
    )

    assert first.accepted
    assert result.status is PositionMaterializationStatus.REJECTED_IDENTITY_CONFLICT


def test_legacy_null_provenance_is_compatible_without_last_write_wins() -> None:
    uow = _uow()
    legacy = MemoryMaterializedLocation(
        id="legacy",
        public_identifier="loc_legacy",
        client_id="client-1",
        aisle_id="aisle-1",
        code="RACK-A/01",
        normalized_code="RACK-A/01",
        status="ACTIVE",
        created_by="legacy",
        created_at=NOW,
        updated_at=NOW,
        creation_source="MANUAL",
    )
    uow.add_location(legacy)

    result = _service(uow).execute(_command())

    assert result.status is PositionMaterializationStatus.REUSED
    assert legacy.profile_id is None
    assert legacy.raw_recognition_code is None


def test_failure_rolls_back_location_and_ledger() -> None:
    def fail() -> None:
        raise OSError("database unavailable")

    base = _uow()
    uow = MemoryPositionMaterializationUnitOfWork(
        inventories=list(base.inventories.values()),
        aisles=list(base.aisles.values()),
        failure_hook=fail,
    )

    result = _service(uow).execute(_command())

    assert result.status is PositionMaterializationStatus.RETRYABLE_FAILURE
    assert uow.locations == {}
    assert uow.requests == {}


def test_transaction_boundary_rolls_back_and_reraises_original_cause() -> None:
    original = RuntimeError("unexpected persistence defect")

    def fail() -> None:
        raise original

    base = _uow()
    uow = MemoryPositionMaterializationUnitOfWork(
        inventories=list(base.inventories.values()),
        aisles=list(base.aisles.values()),
        failure_hook=fail,
    )

    with pytest.raises(RuntimeError) as raised:
        uow.materialize(_command(), request_hash="a" * 64, now=NOW)

    assert raised.value is original
    assert uow.locations == {}
    assert uow.requests == {}


def test_new_location_is_committed_to_repository_sink() -> None:
    repository = MemoryAisleLocationRepository()
    base = _uow()
    uow = MemoryPositionMaterializationUnitOfWork(
        inventories=list(base.inventories.values()),
        aisles=list(base.aisles.values()),
        location_repository=repository,
    )

    result = _service(uow).execute(_command())

    persisted = repository.get_by_id(result.location_id or "")
    assert result.status is PositionMaterializationStatus.MATERIALIZED
    assert persisted is not None
    assert persisted.normalized_code == "RACK-A/01"


def test_repository_source_location_is_visible_and_reused() -> None:
    repository = MemoryAisleLocationRepository()
    repository.save(
        AisleLocation(
            id="repository-location",
            public_identifier="loc_repository",
            client_id="client-1",
            aisle_id="aisle-1",
            code="RACK-A/01",
            normalized_code="RACK-A/01",
            status=AisleLocationStatus.ACTIVE,
            created_by="legacy",
            created_at=NOW,
            updated_at=NOW,
        )
    )
    base = _uow()
    uow = MemoryPositionMaterializationUnitOfWork(
        inventories=list(base.inventories.values()),
        aisles=list(base.aisles.values()),
        location_repository=repository,
    )

    result = _service(uow).execute(_command())

    assert result.status is PositionMaterializationStatus.REUSED
    assert result.location_id == "repository-location"
    assert len(uow.locations) == 1


def test_repository_save_failure_rolls_back_memory_state() -> None:
    class FailingLocationRepository(MemoryAisleLocationRepository):
        def save(self, location: AisleLocation) -> None:
            raise OSError("sink unavailable")

    base = _uow()
    uow = MemoryPositionMaterializationUnitOfWork(
        inventories=list(base.inventories.values()),
        aisles=list(base.aisles.values()),
        location_repository=FailingLocationRepository(),
    )

    result = _service(uow).execute(_command())

    assert result.status is PositionMaterializationStatus.RETRYABLE_FAILURE
    assert result.error_code == "LOCATION_REPOSITORY_SAVE_FAILED"
    assert uow.locations == {}
    assert uow.requests == {}


def test_association_completion_is_idempotent_and_review_can_converge() -> None:
    uow = _uow()
    service = _service(uow)
    result = service.execute(_command())
    assert result.request_id is not None
    assert service.get_association_status("missing-request") is None
    request_key = ("client-1", "request-1")
    assert (
        uow.requests[request_key].association_status
        is PositionMaterializationAssociationStatus.PENDING
    )

    assert service.complete_association(
        result.request_id,
        success=False,
        error_code="CHANNEL_CONFLICT",
        now=NOW,
    )
    assert (
        uow.requests[request_key].association_status
        is PositionMaterializationAssociationStatus.REQUIRES_REVIEW
    )
    assert service.complete_association(result.request_id, success=True, now=NOW)
    assert service.complete_association(result.request_id, success=True, now=NOW)
    request = uow.requests[request_key]
    assert request.association_status is PositionMaterializationAssociationStatus.ASSOCIATED
    assert (
        service.get_association_status(result.request_id)
        is PositionMaterializationAssociationStatus.ASSOCIATED
    )
    assert request.associated_at == NOW
    assert request.association_error_code is None
    assert (
        service.complete_association(
            result.request_id,
            success=False,
            error_code="LATE_CONFLICT",
            now=NOW,
        )
        is False
    )


def test_repository_refresh_observes_active_to_inactive_and_field_changes() -> None:
    repository = MemoryAisleLocationRepository()
    location = AisleLocation(
        id="repository-location",
        public_identifier="loc_repository",
        client_id="client-1",
        aisle_id="aisle-1",
        code="OLD DISPLAY",
        normalized_code="RACK-A/01",
        status=AisleLocationStatus.ACTIVE,
        created_by="legacy",
        created_at=NOW,
        updated_at=NOW,
    )
    repository.save(location)
    base = _uow()
    uow = MemoryPositionMaterializationUnitOfWork(
        inventories=list(base.inventories.values()),
        aisles=list(base.aisles.values()),
        location_repository=repository,
    )
    first = _service(uow).execute(_command(key="first"))
    assert first.status is PositionMaterializationStatus.REUSED

    location.status = AisleLocationStatus.INACTIVE
    location.code = "UPDATED DISPLAY"
    repository.save(location)
    second = _service(uow).execute(_command(key="second"))

    assert second.status is PositionMaterializationStatus.REJECTED_IDENTITY_CONFLICT
    assert second.error_code == "INACTIVE_POSITION_IDENTITY"
    assert uow.locations["repository-location"].status == "INACTIVE"
    assert uow.locations["repository-location"].code == "UPDATED DISPLAY"
