"""Resolve inventory/aisle UUIDs for a captured aisle code from durable local config."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class InventoryContextError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class ResolvedInventoryAisle:
    inventory_id: str
    aisle_id: str
    aisle_code: str


@dataclass(frozen=True)
class InventoryOperationalConfig:
    inventory_id: str
    aisles: tuple[tuple[str, str], ...]  # (aisle_code, aisle_id)

    @classmethod
    def from_dict(cls, data: Any) -> InventoryOperationalConfig:
        if not isinstance(data, dict):
            raise InventoryContextError(
                "INVENTORY_CONTEXT_INVALID",
                "inventory context must be a JSON object",
            )
        inventory_id = str(data.get("inventory_id") or "").strip()
        if not inventory_id:
            raise InventoryContextError(
                "INVENTORY_CONTEXT_INVALID",
                "inventory_id is required",
            )
        raw_aisles = data.get("aisles")
        if not isinstance(raw_aisles, list) or not raw_aisles:
            raise InventoryContextError(
                "INVENTORY_CONTEXT_INVALID",
                "aisles must be a non-empty array",
            )
        pairs: list[tuple[str, str]] = []
        seen_codes: set[str] = set()
        for row in raw_aisles:
            if not isinstance(row, dict):
                raise InventoryContextError(
                    "INVENTORY_CONTEXT_INVALID",
                    "aisle entry must be an object",
                )
            aisle_id = str(row.get("aisle_id") or "").strip()
            aisle_code = str(row.get("aisle_code") or "").strip()
            if not aisle_id or not aisle_code:
                raise InventoryContextError(
                    "INVENTORY_CONTEXT_INVALID",
                    "each aisle requires aisle_id and aisle_code",
                )
            normalized = aisle_code.casefold()
            if normalized in seen_codes:
                raise InventoryContextError(
                    "INVENTORY_CONTEXT_INVALID",
                    f"duplicate aisle_code in context: {aisle_code}",
                )
            seen_codes.add(normalized)
            pairs.append((aisle_code, aisle_id))
        return cls(inventory_id=inventory_id, aisles=tuple(pairs))

    def resolve_aisle(self, aisle_code: str) -> ResolvedInventoryAisle:
        target = aisle_code.strip()
        if not target:
            raise InventoryContextError("AISLE_CODE_REQUIRED", "aisle_code is required")
        for code, aisle_id in self.aisles:
            if code == target:
                return ResolvedInventoryAisle(
                    inventory_id=self.inventory_id,
                    aisle_id=aisle_id,
                    aisle_code=code,
                )
        raise InventoryContextError(
            "AISLE_NOT_IN_INVENTORY_CONTEXT",
            f"aisle_code {target!r} is not configured for inventory {self.inventory_id}",
        )


def inventory_context_path_from_environment() -> Path:
    raw = (
        os.environ.get("DINAMIC_INVENTORY_CONTEXT_PATH")
        or os.environ.get("DINAMIC_INVENTORY_CONFIG_PATH")
        or ""
    ).strip()
    if not raw:
        raise InventoryContextError(
            "INVENTORY_CONTEXT_NOT_CONFIGURED",
            "DINAMIC_INVENTORY_CONTEXT_PATH is required to bind captures to inventory/aisle UUIDs",
        )
    return Path(raw)


def load_inventory_operational_config(path: Path | None = None) -> InventoryOperationalConfig:
    config_path = path or inventory_context_path_from_environment()
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise InventoryContextError(
            "INVENTORY_CONTEXT_NOT_FOUND",
            f"inventory context file not found: {config_path}",
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise InventoryContextError(
            "INVENTORY_CONTEXT_UNREADABLE",
            f"cannot read inventory context: {exc}",
        ) from exc
    return InventoryOperationalConfig.from_dict(raw)


def resolve_inventory_aisle_for_capture(
    aisle_code: str,
    *,
    config: InventoryOperationalConfig | None = None,
) -> ResolvedInventoryAisle:
    operational = config or load_inventory_operational_config()
    return operational.resolve_aisle(aisle_code)
