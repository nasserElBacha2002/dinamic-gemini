"""Build an offline recognition config bundle for one client."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.application.errors import ClientNotFoundError
from src.application.ports.client_supplier_label_profile_repository import (
    ClientSupplierLabelProfileRepository,
)
from src.application.ports.repositories import (
    ClientRepository,
    ClientSupplierRepository,
)
from src.application.ports.supplier_extraction_profile_repository import (
    SupplierExtractionProfileRepository,
)
from src.application.use_cases.inventories.get_inventory_recognition_config import (
    OFFLINE_BUNDLE_SCHEMA_VERSION,
    configuration_for_offline,
)
from src.domain.client_supplier.entities import ClientSupplierStatus
from src.domain.label_profiles.kinds import (
    LabelKind,
    LabelProfileSource,
    effective_label_kind,
)
from src.domain.label_profiles.errors import SupplierLabelProfileNotConfiguredError


@dataclass(frozen=True)
class ClientRecognitionConfigCommand:
    client_id: str


@dataclass(frozen=True)
class OfflineClientSupplierConfig:
    client_supplier_id: str
    name: str
    item_source: str
    position_source: str


@dataclass(frozen=True)
class OfflineClientProfileConfig:
    client_supplier_id: str
    label_kind: str
    source: str
    profile_id: str
    profile_version: int
    configuration_schema_version: int
    recognition_mode: str | None
    semantic_type: str | None
    configuration: dict[str, Any]


@dataclass(frozen=True)
class OfflineClientRecognitionBundle:
    bundle_schema_version: int
    client_id: str
    generated_at: datetime
    suppliers: tuple[OfflineClientSupplierConfig, ...]
    profiles: tuple[OfflineClientProfileConfig, ...]
    bundle_revision: str


def _client_bundle_revision(
    *,
    bundle_schema_version: int,
    client_id: str,
    suppliers: tuple[OfflineClientSupplierConfig, ...],
    profiles: tuple[OfflineClientProfileConfig, ...],
) -> str:
    payload = {
        "bundle_schema_version": bundle_schema_version,
        "client_id": client_id,
        "suppliers": [
            {
                "client_supplier_id": supplier.client_supplier_id,
                "name": supplier.name,
                "item_source": supplier.item_source,
                "position_source": supplier.position_source,
            }
            for supplier in sorted(suppliers, key=lambda row: row.client_supplier_id)
        ],
        "profiles": [
            {
                "client_supplier_id": profile.client_supplier_id,
                "label_kind": profile.label_kind,
                "source": profile.source,
                "profile_id": profile.profile_id,
                "profile_version": profile.profile_version,
                "configuration_schema_version": profile.configuration_schema_version,
                "recognition_mode": profile.recognition_mode,
                "semantic_type": profile.semantic_type,
                "configuration": profile.configuration,
            }
            for profile in sorted(
                profiles,
                key=lambda row: (row.client_supplier_id, row.label_kind, row.profile_id),
            )
        ],
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class GetClientRecognitionConfigUseCase:
    """Aggregate active client suppliers and their effective ITEM/POSITION rules."""

    def __init__(
        self,
        *,
        client_repo: ClientRepository,
        client_supplier_repo: ClientSupplierRepository,
        extraction_profile_repo: SupplierExtractionProfileRepository,
        label_profile_repo: ClientSupplierLabelProfileRepository,
    ) -> None:
        self._client_repo = client_repo
        self._client_supplier_repo = client_supplier_repo
        self._extraction_profile_repo = extraction_profile_repo
        self._label_profile_repo = label_profile_repo

    def execute(
        self, command: ClientRecognitionConfigCommand
    ) -> OfflineClientRecognitionBundle:
        client_id = (command.client_id or "").strip()
        if not client_id or self._client_repo.get_by_id(client_id) is None:
            raise ClientNotFoundError(f"Client not found: {client_id}")

        suppliers = sorted(
            (
                supplier
                for supplier in self._client_supplier_repo.list_by_client(client_id)
                if supplier.client_id == client_id
                and supplier.status is ClientSupplierStatus.ACTIVE
            ),
            key=lambda supplier: supplier.id,
        )

        supplier_configs: list[OfflineClientSupplierConfig] = []
        profiles: list[OfflineClientProfileConfig] = []
        for supplier in suppliers:
            effective_sources: dict[LabelKind, LabelProfileSource] = {}
            for kind in (LabelKind.ITEM, LabelKind.POSITION):
                stored = self._label_profile_repo.get_by_supplier_and_kind(
                    supplier.id, kind
                )
                source = stored.source if stored is not None else LabelProfileSource.DINAMIC
                effective_sources[kind] = source
                if source is LabelProfileSource.DINAMIC:
                    continue

                active = self._extraction_profile_repo.get_active_by_kind(
                    client_id, supplier.id, kind
                )
                if active is None:
                    raise SupplierLabelProfileNotConfiguredError(
                        f"No active supplier extraction profile for {kind.value}",
                        label_kind=kind.value,
                        client_supplier_id=supplier.id,
                    )

                configuration = active.configuration
                profiles.append(
                    OfflineClientProfileConfig(
                        client_supplier_id=supplier.id,
                        label_kind=effective_label_kind(active.label_kind).value,
                        source=LabelProfileSource.SUPPLIER.value,
                        profile_id=active.id,
                        profile_version=int(active.version),
                        configuration_schema_version=int(
                            configuration.configuration_schema_version
                        ),
                        recognition_mode=configuration.recognition_mode.value,
                        semantic_type=configuration.semantic_type,
                        configuration=configuration_for_offline(active),
                    )
                )

            supplier_configs.append(
                OfflineClientSupplierConfig(
                    client_supplier_id=supplier.id,
                    name=supplier.name,
                    item_source=effective_sources[LabelKind.ITEM].value,
                    position_source=effective_sources[LabelKind.POSITION].value,
                )
            )

        supplier_tuple = tuple(supplier_configs)
        profile_tuple = tuple(profiles)
        revision = _client_bundle_revision(
            bundle_schema_version=OFFLINE_BUNDLE_SCHEMA_VERSION,
            client_id=client_id,
            suppliers=supplier_tuple,
            profiles=profile_tuple,
        )
        return OfflineClientRecognitionBundle(
            bundle_schema_version=OFFLINE_BUNDLE_SCHEMA_VERSION,
            client_id=client_id,
            generated_at=datetime.now(timezone.utc),
            suppliers=supplier_tuple,
            profiles=profile_tuple,
            bundle_revision=revision,
        )
