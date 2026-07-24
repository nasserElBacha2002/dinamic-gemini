"""Snapshot + diff helpers for aisle revisions (Phase 8)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from src.domain.aisle_revision.entities import (
    AisleRevisionDiffEntry,
    AisleRevisionDiffKind,
    AisleRevisionItem,
    AisleRevisionItemStatus,
)


@dataclass(frozen=True)
class RevisionSnapshotAsset:
    asset_id: str
    base_result_id: str | None
    base_position_id: str | None
    base_internal_code: str | None
    base_quantity: int | None
    excluded: bool
    #: Position lineage observed at snapshot time; enables compare-and-swap on apply.
    base_position_version_id: str | None = None
    base_position_row_version: int | None = None


@dataclass(frozen=True)
class RevisionSnapshot:
    base_finalization_id: str
    base_finalization_version: int
    base_result_ids: tuple[str, ...]
    base_position_ids: tuple[str, ...]
    base_exclusion_ids: tuple[str, ...]
    asset_ids: tuple[str, ...]
    assets: tuple[RevisionSnapshotAsset, ...]

    def to_json(self) -> str:
        payload = {
            "base_finalization_id": self.base_finalization_id,
            "base_finalization_version": self.base_finalization_version,
            "base_result_ids": list(self.base_result_ids),
            "base_position_ids": list(self.base_position_ids),
            "base_exclusion_ids": list(self.base_exclusion_ids),
            "asset_ids": list(self.asset_ids),
            "assets": [
                {
                    "asset_id": a.asset_id,
                    "base_result_id": a.base_result_id,
                    "base_position_id": a.base_position_id,
                    "base_internal_code": a.base_internal_code,
                    "base_quantity": a.base_quantity,
                    "excluded": a.excluded,
                    "base_position_version_id": a.base_position_version_id,
                    "base_position_row_version": a.base_position_row_version,
                }
                for a in self.assets
            ],
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def parse_revision_snapshot(raw: str) -> RevisionSnapshot:
    data = json.loads(raw or "{}")
    assets = tuple(
        RevisionSnapshotAsset(
            asset_id=str(a.get("asset_id") or ""),
            base_result_id=a.get("base_result_id"),
            base_position_id=a.get("base_position_id"),
            base_internal_code=a.get("base_internal_code"),
            base_quantity=a.get("base_quantity"),
            excluded=bool(a.get("excluded")),
            base_position_version_id=a.get("base_position_version_id"),
            base_position_row_version=(
                int(a["base_position_row_version"])
                if a.get("base_position_row_version") is not None
                else None
            ),
        )
        for a in (data.get("assets") or [])
    )
    return RevisionSnapshot(
        base_finalization_id=str(data.get("base_finalization_id") or ""),
        base_finalization_version=int(data.get("base_finalization_version") or 0),
        base_result_ids=tuple(str(x) for x in (data.get("base_result_ids") or [])),
        base_position_ids=tuple(str(x) for x in (data.get("base_position_ids") or [])),
        base_exclusion_ids=tuple(str(x) for x in (data.get("base_exclusion_ids") or [])),
        asset_ids=tuple(str(x) for x in (data.get("asset_ids") or [])),
        assets=assets,
    )


def canonical_revision_content_hash(
    *,
    revision_id: str,
    inventory_id: str,
    aisle_id: str,
    base_finalization_id: str,
    revision_type: str,
    reason: str,
    snapshot_json: str,
) -> str:
    payload = {
        "revision_id": revision_id,
        "inventory_id": inventory_id,
        "aisle_id": aisle_id,
        "base_finalization_id": base_finalization_id,
        "revision_type": revision_type,
        "reason": reason,
        "snapshot_json": snapshot_json,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def calculate_revision_diff(
    *,
    snapshot: RevisionSnapshot,
    items: Sequence[AisleRevisionItem],
) -> list[AisleRevisionDiffEntry]:
    by_asset = {a.asset_id: a for a in snapshot.assets}
    out: list[AisleRevisionDiffEntry] = []
    for item in items:
        base = by_asset.get(item.asset_id)
        base_code = base.base_internal_code if base else None
        base_qty = base.base_quantity if base else None
        status = item.item_status
        kinds: list[str] = []
        if status == AisleRevisionItemStatus.EXCLUDED.value:
            kinds.append(AisleRevisionDiffKind.EXCLUDED.value)
        elif status == AisleRevisionItemStatus.RESTORED.value:
            kinds.append(AisleRevisionDiffKind.RESTORED.value)
        elif status in (
            AisleRevisionItemStatus.MODIFIED.value,
            AisleRevisionItemStatus.ADOPT_REMOTE.value,
            AisleRevisionItemStatus.ROLLED_BACK.value,
        ):
            if (item.proposed_internal_code or "") != (base_code or ""):
                kinds.append(AisleRevisionDiffKind.CODE_CHANGED.value)
            if item.proposed_quantity != base_qty:
                kinds.append(AisleRevisionDiffKind.QUANTITY_CHANGED.value)
            if not kinds:
                kinds.append(AisleRevisionDiffKind.UNCHANGED.value)
        else:
            kinds.append(AisleRevisionDiffKind.UNCHANGED.value)
        for kind in kinds:
            out.append(
                AisleRevisionDiffEntry(
                    asset_id=item.asset_id,
                    kind=kind,
                    base_internal_code=base_code,
                    proposed_internal_code=item.proposed_internal_code,
                    base_quantity=base_qty,
                    proposed_quantity=item.proposed_quantity,
                    item_status=status,
                    proposal_source=item.proposal_source,
                )
            )
    return out


def canonical_apply_content_hash(
    *,
    revision_id: str,
    base_finalization_id: str,
    items: Sequence[Mapping[str, Any]],
) -> str:
    """Hash the mutation payload of an apply request.

    Deliberately excludes ``apply_id`` and generated ids: the same apply_id retried with the
    same item payload must produce the same hash (replay), while an edited payload must not.
    """
    payload: dict[str, Any] = {
        "revision_id": revision_id,
        "base_finalization_id": base_finalization_id,
        "items": sorted(
            ({str(k): v for k, v in item.items()} for item in items),
            key=lambda entry: str(entry.get("asset_id") or ""),
        ),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
