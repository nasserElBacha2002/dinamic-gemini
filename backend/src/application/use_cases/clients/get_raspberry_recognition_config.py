"""Build a global offline recognition config bundle for Raspberry devices."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from src.application.ports.repositories import ClientRepository
from src.application.use_cases.clients.get_client_recognition_config import (
    ClientRecognitionConfigCommand,
    GetClientRecognitionConfigUseCase,
    OfflineClientRecognitionBundle,
)
from src.application.use_cases.inventories.get_inventory_recognition_config import (
    OFFLINE_BUNDLE_SCHEMA_VERSION,
)
from src.domain.client.entities import ClientStatus


@dataclass(frozen=True)
class OfflineRaspberryClientConfig:
    client_id: str
    name: str
    recognition: OfflineClientRecognitionBundle


@dataclass(frozen=True)
class OfflineRaspberryRecognitionBundle:
    bundle_schema_version: int
    generated_at: datetime
    clients: tuple[OfflineRaspberryClientConfig, ...]
    bundle_revision: str


def raspberry_bundle_revision(
    *,
    bundle_schema_version: int,
    clients: tuple[OfflineRaspberryClientConfig, ...],
) -> str:
    payload = {
        "bundle_schema_version": bundle_schema_version,
        "clients": [
            {
                "client_id": client.client_id,
                "name": client.name,
                "bundle_revision": client.recognition.bundle_revision,
            }
            for client in sorted(
                clients,
                key=lambda row: row.client_id,
            )
        ],
    }

    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )

    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


class GetRaspberryRecognitionConfigUseCase:
    """Aggregate recognition configuration for all active clients."""

    def __init__(
        self,
        *,
        client_repo: ClientRepository,
        client_recognition_use_case: GetClientRecognitionConfigUseCase,
    ) -> None:
        self._client_repo = client_repo
        self._client_recognition_use_case = client_recognition_use_case

    def execute(self) -> OfflineRaspberryRecognitionBundle:
        clients = sorted(
            (
                client
                for client in self._client_repo.list_all()
                if client.status is ClientStatus.ACTIVE
            ),
            key=lambda client: client.id,
        )

        client_configs: list[OfflineRaspberryClientConfig] = []

        for client in clients:
            recognition = self._client_recognition_use_case.execute(
                ClientRecognitionConfigCommand(
                    client_id=client.id,
                )
            )

            client_configs.append(
                OfflineRaspberryClientConfig(
                    client_id=client.id,
                    name=client.name,
                    recognition=recognition,
                )
            )

        client_tuple = tuple(client_configs)

        revision = raspberry_bundle_revision(
            bundle_schema_version=OFFLINE_BUNDLE_SCHEMA_VERSION,
            clients=client_tuple,
        )

        return OfflineRaspberryRecognitionBundle(
            bundle_schema_version=OFFLINE_BUNDLE_SCHEMA_VERSION,
            generated_at=datetime.now(timezone.utc),
            clients=client_tuple,
            bundle_revision=revision,
        )
