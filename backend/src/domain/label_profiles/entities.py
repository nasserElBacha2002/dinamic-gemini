"""Entities for client-supplier label profile configuration (Phase 1)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource


@dataclass
class ClientSupplierLabelProfile:
    """Per-supplier source selection for one label kind (ITEM or POSITION).

    Virtual DINAMIC defaults (no persisted row) use ``id=""`` and null timestamps.
    """

    id: str
    client_supplier_id: str
    label_kind: LabelKind
    source: LabelProfileSource
    created_at: datetime | None = None
    updated_at: datetime | None = None


def virtual_dinamic_label_profile(
    client_supplier_id: str, label_kind: LabelKind
) -> ClientSupplierLabelProfile:
    """Non-persisted inherited DINAMIC — absence of row means default (Phase 1)."""
    return ClientSupplierLabelProfile(
        id="",
        client_supplier_id=client_supplier_id,
        label_kind=label_kind,
        source=LabelProfileSource.DINAMIC,
        created_at=None,
        updated_at=None,
    )


@dataclass(frozen=True)
class ResolvedLabelProfile:
    """Effective profile decision for one label kind at job start."""

    label_kind: LabelKind
    source: LabelProfileSource
    client_supplier_id: str | None
    profile_config_id: str | None = None
    resolution_source: str = "DEFAULT"
    extraction_profile_id: str | None = None
    extraction_profile_version: int | None = None
    supplier_prompt_config_id: str | None = None
    supplier_prompt_config_version: int | None = None

    def to_snapshot_dict(self) -> dict[str, Any]:
        return {
            "label_kind": self.label_kind.value,
            "source": self.source.value,
            "client_supplier_id": self.client_supplier_id,
            "profile_config_id": self.profile_config_id,
            "resolution_source": self.resolution_source,
            "extraction_profile_id": self.extraction_profile_id,
            "extraction_profile_version": self.extraction_profile_version,
            "supplier_prompt_config_id": self.supplier_prompt_config_id,
            "supplier_prompt_config_version": self.supplier_prompt_config_version,
        }


@dataclass(frozen=True)
class ResolvedLabelProfiles:
    """Both ITEM and POSITION effective profiles for one processing context."""

    item: ResolvedLabelProfile
    position: ResolvedLabelProfile

    def to_snapshot_dict(self) -> dict[str, Any]:
        return {
            "snapshot_version": 1,
            "item": self.item.to_snapshot_dict(),
            "position": self.position.to_snapshot_dict(),
        }

    @classmethod
    def from_snapshot_dict(cls, raw: dict[str, Any] | None) -> ResolvedLabelProfiles | None:
        if not isinstance(raw, dict):
            return None
        item_raw = raw.get("item")
        position_raw = raw.get("position")
        if not isinstance(item_raw, dict) or not isinstance(position_raw, dict):
            return None
        return cls(
            item=_profile_from_dict(item_raw, LabelKind.ITEM),
            position=_profile_from_dict(position_raw, LabelKind.POSITION),
        )


def _profile_from_dict(data: dict[str, Any], default_kind: LabelKind) -> ResolvedLabelProfile:
    kind_raw = data.get("label_kind") or default_kind.value
    source_raw = data.get("source") or LabelProfileSource.DINAMIC.value
    return ResolvedLabelProfile(
        label_kind=LabelKind(str(kind_raw).strip().upper()),
        source=LabelProfileSource(str(source_raw).strip().upper()),
        client_supplier_id=(str(data["client_supplier_id"]).strip() or None)
        if data.get("client_supplier_id")
        else None,
        profile_config_id=(str(data["profile_config_id"]).strip() or None)
        if data.get("profile_config_id")
        else None,
        resolution_source=str(data.get("resolution_source") or "DEFAULT"),
        extraction_profile_id=(str(data["extraction_profile_id"]).strip() or None)
        if data.get("extraction_profile_id")
        else None,
        extraction_profile_version=int(data["extraction_profile_version"])
        if data.get("extraction_profile_version") is not None
        else None,
        supplier_prompt_config_id=(str(data["supplier_prompt_config_id"]).strip() or None)
        if data.get("supplier_prompt_config_id")
        else None,
        supplier_prompt_config_version=int(data["supplier_prompt_config_version"])
        if data.get("supplier_prompt_config_version") is not None
        else None,
    )
