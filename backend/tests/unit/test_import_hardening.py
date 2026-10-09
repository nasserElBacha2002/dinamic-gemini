"""Phase 4 — inventory write policy and import confirm hardening."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.application.use_cases.inventories.manage_local_csv_import import (
    ConfirmLocalCsvImport,
    PreviewLocalCsvImport,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.inventory.write_policy import (
    WRITABLE_INVENTORY_STATUSES,
    InventoryNotWritableError,
    InventoryWriteDenialCode,
    is_inventory_status_writable,
    require_inventory_writable,
)
from src.domain.local_csv_import.entities import LocalCsvImport
from src.domain.local_csv_import.errors import LocalCsvImportError
from src.domain.local_csv_import.statuses import (
    LOCAL_CSV_IMPORT_STATUS_CONFIRMED,
    LOCAL_CSV_IMPORT_STATUS_MATERIALIZATION_FAILED,
    LOCAL_CSV_IMPORT_STATUS_MATERIALIZING,
)
from src.infrastructure.repositories.local_csv_inventory_result_writer import (
    MemoryLocalCsvInventoryResultWriter,
)
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_local_csv_import_repository import (
    MemoryLocalCsvImportRepository,
)
from tests.unit.test_local_csv_import import FixedClock, _csv_bytes

NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)


def test_writable_inventory_statuses_match_phase3() -> None:
    assert {s.value for s in WRITABLE_INVENTORY_STATUSES} == {
        "draft",
        "processing",
        "in_review",
    }
    assert is_inventory_status_writable(InventoryStatus.DRAFT)
    assert not is_inventory_status_writable(InventoryStatus.COMPLETED)


def test_require_inventory_writable_rejects_completed() -> None:
    inventory = Inventory(
        id="inv-1",
        name="Done",
        status=InventoryStatus.COMPLETED,
        created_at=NOW,
        updated_at=NOW,
    )
    with pytest.raises(InventoryNotWritableError) as exc:
        require_inventory_writable(inventory)
    assert exc.value.code == InventoryWriteDenialCode.INVENTORY_CLOSED.value


def test_finalize_on_cursor_rejects_closed_inventory() -> None:
    """Finalize must re-check inventory writability inside the confirmation path."""
    inventory_repo = MemoryInventoryRepository()
    inventory_repo.save(
        Inventory(
            id="inventory-1",
            name="Inventory",
            status=InventoryStatus.COMPLETED,
            created_at=NOW,
            updated_at=NOW,
            client_id="client-1",
        )
    )
    import_repo = MemoryLocalCsvImportRepository()
    import_repo.save(
        LocalCsvImport(
            id="imp-1",
            export_id="export-1",
            schema_version="1.1",
            inventory_id="inventory-1",
            device_id="device-1",
            exported_at=NOW,
            status=LOCAL_CSV_IMPORT_STATUS_MATERIALIZING,
            content_hash="hash",
            total_rows=1,
            valid_rows=1,
            rejected_rows=0,
            duplicate_rows=0,
            created_at=NOW,
            updated_at=NOW,
            materialization_owner="owner-a",
            fencing_version=1,
        )
    )

    def _checker(_cur, inventory_id: str) -> None:
        require_inventory_writable(
            inventory_repo.get_by_id(inventory_id),
            inventory_id=inventory_id,
        )

    with pytest.raises(InventoryNotWritableError) as exc:
        import_repo.finalize_import_confirmation_on_cursor(
            MagicMock(),
            import_id="imp-1",
            clock_now=lambda: NOW,
            require_inventory_writable_on_cursor=_checker,
        )
    assert exc.value.code == InventoryWriteDenialCode.INVENTORY_CLOSED.value
    stuck = import_repo.get_by_id("imp-1")
    assert stuck is not None
    assert stuck.status == LOCAL_CSV_IMPORT_STATUS_MATERIALIZING


def test_confirm_rejects_closed_inventory() -> None:
    inventory_repo = MemoryInventoryRepository()
    inventory_repo.save(
        Inventory(
            id="inventory-1",
            name="Inventory",
            status=InventoryStatus.COMPLETED,
            created_at=NOW,
            updated_at=NOW,
            client_id="client-1",
        )
    )
    aisle_repo = MemoryAisleRepository()
    aisle_repo.save(
        Aisle(
            id="aisle-1",
            inventory_id="inventory-1",
            code="A",
            status=AisleStatus.CREATED,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    # Preview requires writable — stage while draft then close.
    inventory_repo.save(
        Inventory(
            id="inventory-1",
            name="Inventory",
            status=InventoryStatus.DRAFT,
            created_at=NOW,
            updated_at=NOW,
            client_id="client-1",
        )
    )
    import_repo = MemoryLocalCsvImportRepository()
    preview = PreviewLocalCsvImport(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        import_repo=import_repo,
        clock=FixedClock(),
        enabled=True,
    )
    staged = preview.execute(inventory_id="inventory-1", content=_csv_bytes())
    inventory_repo.save(
        Inventory(
            id="inventory-1",
            name="Inventory",
            status=InventoryStatus.COMPLETED,
            created_at=NOW,
            updated_at=NOW,
            client_id="client-1",
        )
    )
    confirm = ConfirmLocalCsvImport(
        import_repo=import_repo,
        result_writer=MemoryLocalCsvInventoryResultWriter(),
        clock=FixedClock(),
        enabled=True,
        inventory_repo=inventory_repo,
    )
    with pytest.raises(LocalCsvImportError) as exc:
        confirm.execute(
            inventory_id="inventory-1",
            export_id=staged.export_id,
            confirmed_by_user_id="user-1",
        )
    assert exc.value.code == "INVENTORY_CLOSED"


def test_confirm_finalizes_only_after_materialize() -> None:
    inventory_repo = MemoryInventoryRepository()
    inventory_repo.save(
        Inventory(
            id="inventory-1",
            name="Inventory",
            status=InventoryStatus.DRAFT,
            created_at=NOW,
            updated_at=NOW,
            client_id="client-1",
        )
    )
    aisle_repo = MemoryAisleRepository()
    aisle_repo.save(
        Aisle(
            id="aisle-1",
            inventory_id="inventory-1",
            code="A",
            status=AisleStatus.CREATED,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    import_repo = MemoryLocalCsvImportRepository()
    materializer = MagicMock()
    order: list[str] = []

    class _Writer(MemoryLocalCsvInventoryResultWriter):
        def apply_import(self, **kwargs):
            order.append("apply")
            assert materializer.materialize.call_count == 0
            return super().apply_import(**kwargs)

    def _materialize(*_a, **_k):
        order.append("materialize")
        # While materializing, header must not be CONFIRMED yet.
        claimed = import_repo.get_by_export_id(
            inventory_id="inventory-1", export_id=staged.export_id
        )
        assert claimed is not None
        assert claimed.status == LOCAL_CSV_IMPORT_STATUS_MATERIALIZING
        return 1

    materializer.materialize.side_effect = _materialize
    writer = _Writer()
    preview = PreviewLocalCsvImport(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        import_repo=import_repo,
        clock=FixedClock(),
        enabled=True,
    )
    staged = preview.execute(inventory_id="inventory-1", content=_csv_bytes())
    confirm = ConfirmLocalCsvImport(
        import_repo=import_repo,
        result_writer=writer,
        clock=FixedClock(),
        enabled=True,
        position_materializer=materializer,
        inventory_repo=inventory_repo,
    )
    confirmed, duplicate = confirm.execute(
        inventory_id="inventory-1",
        export_id=staged.export_id,
        confirmed_by_user_id="user-1",
    )
    assert duplicate is False
    assert confirmed.status == LOCAL_CSV_IMPORT_STATUS_CONFIRMED
    assert order == ["apply", "materialize"]
    materializer.materialize.assert_called_once()


def test_materialization_failure_does_not_confirm() -> None:
    inventory_repo = MemoryInventoryRepository()
    inventory_repo.save(
        Inventory(
            id="inventory-1",
            name="Inventory",
            status=InventoryStatus.DRAFT,
            created_at=NOW,
            updated_at=NOW,
            client_id="client-1",
        )
    )
    aisle_repo = MemoryAisleRepository()
    aisle_repo.save(
        Aisle(
            id="aisle-1",
            inventory_id="inventory-1",
            code="A",
            status=AisleStatus.CREATED,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    import_repo = MemoryLocalCsvImportRepository()
    materializer = MagicMock()
    materializer.materialize.side_effect = RuntimeError("boom")
    preview = PreviewLocalCsvImport(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        import_repo=import_repo,
        clock=FixedClock(),
        enabled=True,
    )
    staged = preview.execute(inventory_id="inventory-1", content=_csv_bytes())
    confirm = ConfirmLocalCsvImport(
        import_repo=import_repo,
        result_writer=MemoryLocalCsvInventoryResultWriter(),
        clock=FixedClock(),
        enabled=True,
        position_materializer=materializer,
        inventory_repo=inventory_repo,
    )
    with pytest.raises(LocalCsvImportError) as exc:
        confirm.execute(
            inventory_id="inventory-1",
            export_id=staged.export_id,
            confirmed_by_user_id="user-1",
        )
    assert exc.value.code == "LOCAL_CSV_MATERIALIZATION_FAILED"
    failed = import_repo.get_by_export_id(
        inventory_id="inventory-1", export_id=staged.export_id
    )
    assert failed is not None
    assert failed.status == LOCAL_CSV_IMPORT_STATUS_MATERIALIZATION_FAILED
    assert failed.last_error_code == "LOCAL_CSV_MATERIALIZATION_FAILED"
