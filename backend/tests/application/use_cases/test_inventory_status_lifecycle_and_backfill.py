"""Inventory status rollup: lifecycle, review completion, and backfill maintenance."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.services.aisle_review_lifecycle_sync import AisleReviewLifecycleSync
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.services.operational_execution_config_resolver import (
    OperationalPrimaryExecutionConfig,
)
from src.application.use_cases.aisles.create_aisle import CreateAisleCommand, CreateAisleUseCase
from src.application.use_cases.inventories.backfill_inventory_statuses import (
    BackfillInventoryStatusesUseCase,
)
from src.application.use_cases.inventories.create_inventory import (
    CreateInventoryCommand,
    CreateInventoryUseCase,
)
from src.application.use_cases.positions.confirm_position import ConfirmPositionUseCase
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.client.entities import Client, ClientStatus
from src.domain.client_supplier.entities import ClientSupplier, ClientSupplierStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.positions.entities import Position, PositionStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_client_repository import MemoryClientRepository
from src.infrastructure.repositories.memory_client_supplier_repository import (
    MemoryClientSupplierRepository,
)
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.repositories.memory_review_action_repository import (
    MemoryReviewActionRepository,
)
from tests.support.processing_test_constants import STUB_PRIMARY_MODEL, STUB_PRIMARY_PROVIDER


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class _StubOperationalResolver:
    def resolve(self, settings: object) -> OperationalPrimaryExecutionConfig:
        _ = settings
        return OperationalPrimaryExecutionConfig(
            provider_name=STUB_PRIMARY_PROVIDER,
            model_name=STUB_PRIMARY_MODEL,
            prompt_key="global_v21",
            prompt_version=None,
        )


def _settings_loader() -> object:
    return object()


def test_inventory_aggregate_lifecycle_through_completed() -> None:
    """draft → processing (aisle exists) → in_review (processed) → completed after review clears."""
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    clock = FixedClock(now)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    position_repo = MemoryPositionRepository()
    review_repo = MemoryReviewActionRepository()
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, clock)

    client_repo = MemoryClientRepository()
    client_repo.save(
        Client(
            id="lifecycle-client",
            name="Lifecycle Client",
            status=ClientStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )
    create_inv_uc = CreateInventoryUseCase(
        inv_repo,
        client_repo,
        clock,
        operational_resolver=_StubOperationalResolver(),
        settings_loader=_settings_loader,
    )
    inv = create_inv_uc.execute(
        CreateInventoryCommand(name="Lifecycle inv", client_id="lifecycle-client")
    )
    assert inv.status == InventoryStatus.DRAFT
    assert reconciler.reconcile(inv.id) is False

    supplier_repo = MemoryClientSupplierRepository()
    supplier_repo.save(
        ClientSupplier(
            id="lifecycle-supplier",
            client_id="lifecycle-client",
            name="Lifecycle Supplier",
            status=ClientSupplierStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )
    create_aisle_uc = CreateAisleUseCase(
        inv_repo,
        aisle_repo,
        supplier_repo,
        clock,
        reconciler,
    )
    aisle = create_aisle_uc.execute(
        CreateAisleCommand(
            inventory_id=inv.id,
            code="L1",
            client_supplier_id="lifecycle-supplier",
        )
    )
    inv_refreshed = inv_repo.get_by_id(inv.id)
    assert inv_refreshed is not None
    assert inv_refreshed.status == InventoryStatus.PROCESSING

    a = aisle_repo.get_by_id(aisle.id)
    assert a is not None
    a.mark_assets_uploaded(now)
    aisle_repo.save(a)
    reconciler.reconcile(inv.id)
    assert inv_repo.get_by_id(inv.id).status == InventoryStatus.PROCESSING

    a.mark_queued(now)
    aisle_repo.save(a)
    reconciler.reconcile(inv.id)
    a.mark_processing(now)
    aisle_repo.save(a)
    reconciler.reconcile(inv.id)
    a.mark_processed(now)
    aisle_repo.save(a)
    reconciler.reconcile(inv.id)
    assert inv_repo.get_by_id(inv.id).status == InventoryStatus.IN_REVIEW

    position = Position(
        id="pos-lc-1",
        aisle_id=aisle.id,
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=True,
        primary_evidence_id=None,
        created_at=now,
        updated_at=now,
    )
    position_repo.save(position)

    review_sync = AisleReviewLifecycleSync(aisle_repo, position_repo, clock, reconciler)
    confirm_uc = ConfirmPositionUseCase(
        inv_repo,
        aisle_repo,
        position_repo,
        review_repo,
        clock,
        review_sync,
    )
    confirm_uc.execute(inv.id, aisle.id, position.id, None)

    assert aisle_repo.get_by_id(aisle.id) is not None
    assert aisle_repo.get_by_id(aisle.id).status == AisleStatus.COMPLETED
    assert inv_repo.get_by_id(inv.id).status == InventoryStatus.COMPLETED


def test_backfill_corrects_draft_when_aisle_already_completed() -> None:
    now = datetime(2026, 2, 1, tzinfo=timezone.utc)
    clock = FixedClock(now)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    inv = Inventory("inv-bf-1", "Backfill", InventoryStatus.DRAFT, now, now)
    inv_repo.save(inv)
    aisle_repo.save(
        Aisle("aisle-bf-1", "inv-bf-1", "B1", AisleStatus.COMPLETED, now, now),
    )
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, clock)
    uc = BackfillInventoryStatusesUseCase(inv_repo, reconciler)
    result = uc.execute()
    assert result.inventories_scanned == 1
    assert result.inventories_updated == 1
    assert inv_repo.get_by_id("inv-bf-1") is not None
    assert inv_repo.get_by_id("inv-bf-1").status == InventoryStatus.COMPLETED


def test_backfill_corrects_draft_when_aisle_is_processed() -> None:
    now = datetime(2026, 2, 2, tzinfo=timezone.utc)
    clock = FixedClock(now)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    inv = Inventory("inv-bf-2", "Backfill2", InventoryStatus.DRAFT, now, now)
    inv_repo.save(inv)
    aisle_repo.save(
        Aisle("aisle-bf-2", "inv-bf-2", "B2", AisleStatus.PROCESSED, now, now),
    )
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, clock)
    result = BackfillInventoryStatusesUseCase(inv_repo, reconciler).execute()
    assert result.inventories_updated == 1
    assert inv_repo.get_by_id("inv-bf-2").status == InventoryStatus.IN_REVIEW
