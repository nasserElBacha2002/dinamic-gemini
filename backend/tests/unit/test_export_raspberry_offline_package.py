"""Export offline package aggregates recognition + inventories."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.application.use_cases.raspberry.export_raspberry_offline_package import (
    ExportRaspberryOfflinePackageCommand,
    ExportRaspberryOfflinePackageUseCase,
)
from src.domain.client.entities import Client, ClientStatus
from src.domain.inventory.entities import Inventory, InventoryStatus


def _now() -> datetime:
    return datetime.now(timezone.utc)


def test_export_scoped_to_one_client() -> None:
    client_repo = MagicMock()
    client_repo.get_by_id.return_value = Client(
        id="client-a",
        name="A",
        status=ClientStatus.ACTIVE,
        created_at=_now(),
        updated_at=_now(),
    )
    raspberry_bundle = MagicMock()
    raspberry_bundle.bundle_schema_version = 1
    raspberry_bundle.generated_at = _now()
    raspberry_bundle.clients = []
    raspberry_bundle.bundle_revision = "rev"
    raspberry_uc = MagicMock()
    raspberry_uc.execute.return_value = raspberry_bundle

    inventory = Inventory(
        id="inv-1",
        name="Warehouse",
        status=InventoryStatus.DRAFT,
        created_at=_now(),
        updated_at=_now(),
        client_id="client-a",
    )
    list_uc = MagicMock()
    list_uc.execute.return_value = (inventory,)

    inv_bundle = MagicMock()
    inv_recognition_uc = MagicMock()
    inv_recognition_uc.execute.return_value = inv_bundle

    use_case = ExportRaspberryOfflinePackageUseCase(
        client_repo=client_repo,
        raspberry_recognition_use_case=raspberry_uc,
        list_inventories_use_case=list_uc,
        inventory_recognition_use_case=inv_recognition_uc,
    )
    result = use_case.execute(
        ExportRaspberryOfflinePackageCommand(client_id="client-a")
    )
    assert result.package_schema_version == 1
    assert len(result.inventories) == 1
    assert len(result.inventory_recognition_configs) == 1
    list_uc.execute.assert_called_once()
