"""Build offline recognition config bundle for one inventory (mobile sync)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.application.errors import InventoryNotFoundError
from src.application.ports.client_supplier_label_profile_repository import (
    ClientSupplierLabelProfileRepository,
)
from src.application.ports.repositories import AisleRepository, InventoryRepository
from src.application.ports.supplier_extraction_profile_repository import (
    SupplierExtractionProfileRepository,
)
from src.domain.client_supplier.extraction_profile import (
    ExtractionProfileStatus,
    SupplierExtractionProfile,
)
from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource, effective_label_kind


OFFLINE_BUNDLE_SCHEMA_VERSION = 1


def configuration_for_offline(profile: SupplierExtractionProfile) -> dict[str, Any]:
    """Strip AI/visual blobs; keep deterministic validation config for mobile CODE_SCAN."""
    raw = profile.configuration.to_public_dict()
    keep_keys = {
        "configuration_schema_version",
        "recognition_mode",
        "semantic_type",
        "deterministic",
        "required_fields",
        "quantity_rules",
        "validation_rules",
        "accepted_barcode_formats",
        "custom_payload_pattern",
        "aliases",
    }
    slim: dict[str, Any] = {k: raw[k] for k in keep_keys if k in raw}
    # Quantity: only presence/required flags — not OCR alias lists for offline scan.
    qty = slim.get("quantity_rules")
    if isinstance(qty, dict):
        slim["quantity_rules"] = {
            "required": bool(qty.get("required")),
            "expected_presence": qty.get("expected_presence"),
            "minimum": qty.get("minimum"),
            "maximum": qty.get("maximum"),
            "allow_decimals": qty.get("allow_decimals"),
            "allow_negative": qty.get("allow_negative"),
            "missing_quantity_action": qty.get("missing_quantity_action"),
        }
    # Drop visual detection rules entirely for offline CODE_SCAN.
    slim.pop("label_detection_rules", None)
    slim.pop("internal_code_sources", None)
    slim.pop("additional_fields", None)
    slim.pop("valid_examples", None)
    slim.pop("invalid_examples", None)
    return slim


@dataclass(frozen=True)
class GetInventoryRecognitionConfigCommand:
    inventory_id: str


@dataclass(frozen=True)
class OfflineAisleConfig:
    aisle_id: str
    aisle_code: str | None
    client_supplier_id: str | None
    item_profile_source_override: str | None
    position_profile_source_override: str | None
    effective_item_source: str
    effective_position_source: str


@dataclass(frozen=True)
class OfflineProfileConfig:
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
class OfflineRecognitionBundle:
    bundle_schema_version: int
    inventory_id: str
    client_id: str
    generated_at: datetime
    aisles: tuple[OfflineAisleConfig, ...]
    profiles: tuple[OfflineProfileConfig, ...]
    bundle_revision: str


class GetInventoryRecognitionConfigUseCase:
    """Aggregate aisle→supplier mappings + active SUPPLIER extraction profiles."""

    def __init__(
        self,
        *,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        extraction_profile_repo: SupplierExtractionProfileRepository,
        label_profile_repo: ClientSupplierLabelProfileRepository,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._extraction_profile_repo = extraction_profile_repo
        self._label_profile_repo = label_profile_repo

    def execute(
        self, command: GetInventoryRecognitionConfigCommand
    ) -> OfflineRecognitionBundle:
        inventory = self._inventory_repo.get_by_id(command.inventory_id)
        if inventory is None:
            raise InventoryNotFoundError(f"Inventory not found: {command.inventory_id}")

        aisles = list(self._aisle_repo.list_by_inventory(command.inventory_id))
        supplier_ids = sorted(
            {
                (a.client_supplier_id or "").strip()
                for a in aisles
                if (a.client_supplier_id or "").strip()
            }
        )

        aisle_dtos: list[OfflineAisleConfig] = []
        for aisle in aisles:
            supplier_id = (aisle.client_supplier_id or "").strip() or None
            item_eff = self._effective_source(
                supplier_id=supplier_id,
                label_kind=LabelKind.ITEM,
                override=aisle.item_profile_source_override,
            )
            pos_eff = self._effective_source(
                supplier_id=supplier_id,
                label_kind=LabelKind.POSITION,
                override=aisle.position_profile_source_override,
            )
            aisle_dtos.append(
                OfflineAisleConfig(
                    aisle_id=aisle.id,
                    aisle_code=getattr(aisle, "code", None),
                    client_supplier_id=supplier_id,
                    item_profile_source_override=(
                        aisle.item_profile_source_override.value
                        if aisle.item_profile_source_override
                        else None
                    ),
                    position_profile_source_override=(
                        aisle.position_profile_source_override.value
                        if aisle.position_profile_source_override
                        else None
                    ),
                    effective_item_source=item_eff.value,
                    effective_position_source=pos_eff.value,
                )
            )

        profiles: list[OfflineProfileConfig] = []
        for supplier_id in supplier_ids:
            listed = list(
                self._extraction_profile_repo.list_by_supplier(
                    inventory.client_id, supplier_id
                )
            )
            for kind in (LabelKind.ITEM, LabelKind.POSITION):
                active = _pick_active(listed, kind)
                if active is None:
                    continue
                cfg = active.configuration
                profiles.append(
                    OfflineProfileConfig(
                        client_supplier_id=supplier_id,
                        label_kind=effective_label_kind(active.label_kind).value,
                        source=LabelProfileSource.SUPPLIER.value,
                        profile_id=active.id,
                        profile_version=int(active.version),
                        configuration_schema_version=int(
                            cfg.configuration_schema_version
                        ),
                        recognition_mode=cfg.recognition_mode.value,
                        semantic_type=cfg.semantic_type,
                        configuration=configuration_for_offline(active),
                    )
                )

        now = datetime.now(timezone.utc)
        revision = (
            f"{inventory.id}:{len(aisle_dtos)}:{len(profiles)}:"
            f"{'-'.join(f'{p.profile_id}@{p.profile_version}' for p in profiles)}"
        )
        return OfflineRecognitionBundle(
            bundle_schema_version=OFFLINE_BUNDLE_SCHEMA_VERSION,
            inventory_id=inventory.id,
            client_id=inventory.client_id,
            generated_at=now,
            aisles=tuple(aisle_dtos),
            profiles=tuple(profiles),
            bundle_revision=revision,
        )

    def _effective_source(
        self,
        *,
        supplier_id: str | None,
        label_kind: LabelKind,
        override: LabelProfileSource | None,
    ) -> LabelProfileSource:
        if override is not None:
            return override
        if not supplier_id:
            return LabelProfileSource.DINAMIC
        stored = self._label_profile_repo.get_by_supplier_and_kind(
            supplier_id, label_kind
        )
        if stored is not None:
            return stored.source
        return LabelProfileSource.DINAMIC


def _pick_active(
    profiles: list[SupplierExtractionProfile], kind: LabelKind
) -> SupplierExtractionProfile | None:
    best: SupplierExtractionProfile | None = None
    best_version = -1
    for profile in profiles:
        if profile.status is not ExtractionProfileStatus.ACTIVE:
            continue
        if effective_label_kind(profile.label_kind) is not kind:
            continue
        if int(profile.version) > best_version:
            best = profile
            best_version = int(profile.version)
    return best
