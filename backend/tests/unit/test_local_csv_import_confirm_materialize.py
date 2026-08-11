"""Regression: CSV confirm materializes positions only after confirm TX."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.application.use_cases.inventories.manage_local_csv_import import (
    ConfirmLocalCsvImport,
    PreviewLocalCsvImport,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
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


class _TrackingWriter(MemoryLocalCsvInventoryResultWriter):
    def __init__(self, materializer: MagicMock) -> None:
        super().__init__()
        self._materializer = materializer

    def apply_import(self, **kwargs):
        assert self._materializer.materialize.call_count == 0
        return super().apply_import(**kwargs)


def test_confirm_materializes_positions_only_after_apply_import() -> None:
    inventory_repo = MemoryInventoryRepository()
    inventory_repo.save(
        Inventory(
            id="inventory-1",
            name="Inventory",
            status=InventoryStatus.DRAFT,
            created_at=NOW,
            updated_at=NOW,
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
    materializer.materialize.return_value = None
    writer = _TrackingWriter(materializer)
    preview = PreviewLocalCsvImport(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        import_repo=import_repo,
        clock=FixedClock(),
        enabled=True,
    )
    confirm = ConfirmLocalCsvImport(
        import_repo=import_repo,
        result_writer=writer,
        clock=FixedClock(),
        enabled=True,
        position_materializer=materializer,
    )

    staged = preview.execute(inventory_id="inventory-1", content=_csv_bytes())
    confirmed, duplicate = confirm.execute(
        inventory_id="inventory-1",
        export_id=staged.export_id,
        confirmed_by_user_id="user-1",
    )

    assert confirmed.status == "CONFIRMED"
    assert duplicate is False
    materializer.materialize.assert_called_once()
