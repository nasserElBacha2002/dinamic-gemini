from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from src.application.dto.access_principal import AccessPrincipal
from src.application.dto.position_materialization import MaterializePositionCommand
from src.application.ports.manual_image_result_unit_of_work import (
    ManualImageResultRepositories,
)
from src.application.services.position_materialization.recovery import (
    PositionMaterializationAssociationRecoveryService,
    PositionMaterializationRecoveryConfig,
)
from src.application.services.position_materialization.recovery_scheduler import (
    build_position_materialization_recovery_scheduler,
)
from src.domain.position_materialization import (
    PositionMaterializationAssociationReceipt,
    PositionMaterializationAssociationStatus,
)
from src.domain.position_recognition.entities import (
    CanonicalPositionRecognition,
    PositionRecognitionSource,
)
from src.infrastructure.persistence.memory_manual_image_result_unit_of_work import (
    MemoryManualImageResultUnitOfWork,
)
from src.infrastructure.persistence.memory_position_materialization_association_receipt_repository import (
    MemoryPositionMaterializationAssociationReceiptRepository,
)
from src.infrastructure.persistence.memory_position_materialization_unit_of_work import (
    MemoryMaterializationAisle,
    MemoryMaterializationInventory,
    MemoryPositionMaterializationUnitOfWork,
)
from src.observability.metrics.instruments import POSITION_MATERIALIZATION_TOTAL
from src.observability.metrics.registry import get_metrics_registry

NOW = datetime(2026, 9, 8, tzinfo=timezone.utc)


class _Clock:
    def now(self) -> datetime:
        return NOW


def _uow() -> tuple[MemoryPositionMaterializationUnitOfWork, str]:
    uow = MemoryPositionMaterializationUnitOfWork(
        inventories=[
            MemoryMaterializationInventory(
                id="inventory-1", client_id="client-1", status="processing"
            )
        ],
        aisles=[MemoryMaterializationAisle(id="aisle-1", inventory_id="inventory-1")],
    )
    result = uow.materialize(
        MaterializePositionCommand(
            recognition=CanonicalPositionRecognition(
                raw_code="A-1",
                normalized_code="A-1",
                source=PositionRecognitionSource.CODE_SCAN,
            ),
            inventory_id="inventory-1",
            aisle_id="aisle-1",
            principal=AccessPrincipal(
                actor_id="test",
                client_id="client-1",
                roles=frozenset({"system"}),
                is_platform=False,
            ),
            idempotency_key="key-1",
        ),
        request_hash="a" * 64,
        now=NOW,
    )
    assert result.request_id is not None
    return uow, result.request_id


def _service(
    uow: MemoryPositionMaterializationUnitOfWork, *, max_attempts: int = 2
) -> PositionMaterializationAssociationRecoveryService:
    return PositionMaterializationAssociationRecoveryService(
        uow,
        config=PositionMaterializationRecoveryConfig(
            lease=timedelta(minutes=2),
            batch_size=10,
            max_attempts=max_attempts,
            backoff_base=timedelta(minutes=1),
            backoff_max=timedelta(minutes=10),
        ),
    )


def _request(uow: MemoryPositionMaterializationUnitOfWork):
    return next(iter(uow.requests.values()))


def test_location_without_downstream_evidence_retries_then_exhausts() -> None:
    registry = get_metrics_registry()
    registry.reset_for_tests()
    uow, _ = _uow()
    service = _service(uow)

    assert service.run_once(owner="worker-1", now=NOW) == 1
    row = _request(uow)
    assert row.association_status is PositionMaterializationAssociationStatus.PENDING
    assert row.attempt_count == 1
    assert row.next_retry_at == NOW + timedelta(minutes=1)

    assert service.run_once(owner="worker-1", now=row.next_retry_at) == 1
    row = _request(uow)
    assert row.association_status is PositionMaterializationAssociationStatus.EXHAUSTED
    assert row.attempt_count == 2
    base_labels = {
        "component": "recovery",
        "source": "RECOVERY",
        "mode": "DINAMIC",
    }
    assert (
        registry.get_counter_value(
            POSITION_MATERIALIZATION_TOTAL,
            {
                **base_labels,
                "outcome": "technical_retry",
                "reason_code": "association_evidence_absent",
            },
        )
        == 1.0
    )
    assert (
        registry.get_counter_value(
            POSITION_MATERIALIZATION_TOTAL,
            {
                **base_labels,
                "outcome": "retry_exhausted",
                "reason_code": "max_attempts",
            },
        )
        == 1.0
    )
    registry.reset_for_tests()


def test_image_receipt_recovers_pending_ledger() -> None:
    registry = get_metrics_registry()
    registry.reset_for_tests()
    uow, request_id = _uow()
    uow.receipts[request_id] = PositionMaterializationAssociationReceipt(
        request_id=request_id,
        target_type="IMAGE_RESULT",
        target_id="result-1",
        created_at=NOW,
    )

    assert _service(uow).run_once(owner="worker-1", now=NOW) == 1
    assert _request(uow).association_status is PositionMaterializationAssociationStatus.ASSOCIATED
    assert (
        registry.get_counter_value(
            POSITION_MATERIALIZATION_TOTAL,
            {
                "component": "recovery",
                "source": "RECOVERY",
                "mode": "DINAMIC",
                "outcome": "association_recovered",
                "reason_code": "none",
            },
        )
        == 1.0
    )
    registry.reset_for_tests()


def test_preliminary_request_reference_recovers_pending_ledger() -> None:
    uow, request_id = _uow()
    uow.preliminary_request_ids.add(request_id)

    assert _service(uow).run_once(owner="worker-1", now=NOW) == 1
    assert _request(uow).association_status is PositionMaterializationAssociationStatus.ASSOCIATED


def test_stale_lease_reclaimed_and_old_owner_fenced() -> None:
    uow, request_id = _uow()
    first = uow.claim_due_associations(
        owner="worker-1",
        now=NOW,
        lease=timedelta(seconds=5),
        batch=1,
        max_attempts=3,
    )
    assert len(first) == 1
    later = NOW + timedelta(seconds=6)
    second = uow.claim_due_associations(
        owner="worker-2",
        now=later,
        lease=timedelta(seconds=5),
        batch=1,
        max_attempts=3,
    )
    assert len(second) == 1
    assert not uow.complete_claimed(request_id=request_id, owner="worker-1", now=later)
    assert uow.complete_claimed(request_id=request_id, owner="worker-2", now=later)


def test_scheduler_disabled_performs_no_writes() -> None:
    uow, _ = _uow()
    scheduler = build_position_materialization_recovery_scheduler(
        service=_service(uow),
        clock=_Clock(),
        enabled=False,
        interval_sec=60,
    )

    assert scheduler.run_once() == 0
    assert _request(uow).attempt_count == 0


def test_manual_image_uow_rollback_removes_receipt() -> None:
    receipt_repo = MemoryPositionMaterializationAssociationReceiptRepository()
    repositories = ManualImageResultRepositories(
        position_repo=MagicMock(),
        product_record_repo=MagicMock(),
        evidence_repo=MagicMock(),
        manual_coverage_repo=MagicMock(),
        result_evidence_repo=MagicMock(),
        review_repo=MagicMock(),
        image_coverage_repo=MagicMock(),
        counted_product_label_repo=MagicMock(),
        materialization_receipt_repo=receipt_repo,
    )
    uow = MemoryManualImageResultUnitOfWork(
        repositories=repositories,
        _lifecycle_sync=MagicMock(),
    )
    with uow:
        receipt_repo.save(
            PositionMaterializationAssociationReceipt(
                request_id="request-1",
                target_type="IMAGE_RESULT",
                target_id="result-1",
                created_at=NOW,
            )
        )

    assert not receipt_repo.exists("request-1")
