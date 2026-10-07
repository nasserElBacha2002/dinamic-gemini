"""Build a downloadable offline package for Raspberry scanner configuration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.application.errors import ClientNotFoundError
from src.application.ports.repositories import ClientRepository
from src.application.use_cases.clients.get_raspberry_recognition_config import (
    GetRaspberryRecognitionConfigUseCase,
    OfflineRaspberryRecognitionBundle,
    raspberry_bundle_revision,
)
from src.application.use_cases.inventories.get_inventory_recognition_config import (
    OFFLINE_BUNDLE_SCHEMA_VERSION,
    GetInventoryRecognitionConfigCommand,
    GetInventoryRecognitionConfigUseCase,
    OfflineRecognitionBundle,
)
from src.application.use_cases.inventories.list_raspberry_inventories import (
    ListRaspberryInventoriesCommand,
    ListRaspberryInventoriesUseCase,
)
from src.application.use_cases.raspberry.offline_package_constants import (
    RASPBERRY_OFFLINE_PACKAGE_SCHEMA_VERSION,
)
from src.domain.client.entities import ClientStatus


@dataclass(frozen=True)
class ExportRaspberryOfflinePackageCommand:
    client_id: str | None = None


@dataclass(frozen=True)
class ExportRaspberryOfflinePackageResult:
    package_schema_version: int
    generated_at: datetime
    recognition: object
    inventories: tuple[object, ...]
    inventory_recognition_configs: tuple[OfflineRecognitionBundle, ...]


class ExportRaspberryOfflinePackageUseCase:
    def __init__(
        self,
        *,
        client_repo: ClientRepository,
        raspberry_recognition_use_case: GetRaspberryRecognitionConfigUseCase,
        list_inventories_use_case: ListRaspberryInventoriesUseCase,
        inventory_recognition_use_case: GetInventoryRecognitionConfigUseCase,
    ) -> None:
        self._client_repo = client_repo
        self._raspberry_recognition_use_case = raspberry_recognition_use_case
        self._list_inventories_use_case = list_inventories_use_case
        self._inventory_recognition_use_case = inventory_recognition_use_case

    def execute(
        self,
        command: ExportRaspberryOfflinePackageCommand,
    ) -> ExportRaspberryOfflinePackageResult:
        scoped_client = (command.client_id or "").strip() or None
        if scoped_client and self._client_repo.get_by_id(scoped_client) is None:
            raise ClientNotFoundError(f"Client not found: {scoped_client}")

        recognition = self._raspberry_recognition_use_case.execute()
        if scoped_client is not None:
            recognition_clients = tuple(
                client
                for client in recognition.clients
                if client.client_id == scoped_client
            )
            recognition = OfflineRaspberryRecognitionBundle(
                bundle_schema_version=recognition.bundle_schema_version,
                generated_at=recognition.generated_at,
                clients=recognition_clients,
                bundle_revision=raspberry_bundle_revision(
                    bundle_schema_version=OFFLINE_BUNDLE_SCHEMA_VERSION,
                    clients=recognition_clients,
                ),
            )

        inventory_rows: list[object] = []
        inventory_bundles: list[OfflineRecognitionBundle] = []

        client_ids = (
            [scoped_client]
            if scoped_client
            else [
                client.id
                for client in self._client_repo.list_all()
                if client.status is ClientStatus.ACTIVE
            ]
        )

        for client_id in sorted(client_ids):
            inventories = self._list_inventories_use_case.execute(
                ListRaspberryInventoriesCommand(client_id=client_id)
            )
            for inventory in inventories:
                inventory_rows.append(inventory)
                bundle = self._inventory_recognition_use_case.execute(
                    GetInventoryRecognitionConfigCommand(
                        inventory_id=inventory.id,
                    )
                )
                inventory_bundles.append(bundle)

        return ExportRaspberryOfflinePackageResult(
            package_schema_version=RASPBERRY_OFFLINE_PACKAGE_SCHEMA_VERSION,
            generated_at=datetime.now(timezone.utc),
            recognition=recognition,
            inventories=tuple(inventory_rows),
            inventory_recognition_configs=tuple(inventory_bundles),
        )
