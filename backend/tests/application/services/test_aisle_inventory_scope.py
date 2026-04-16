"""Phase 8 — require_aisle_scoped_to_inventory error semantics."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.errors import AisleNotFoundError
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.domain.aisle.entities import Aisle, AisleStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository

UTC = timezone.utc


def _repo_with_aisle(*, inv: str, aisle_id: str = "a1") -> MemoryAisleRepository:
    now = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)
    r = MemoryAisleRepository()
    r.save(Aisle(aisle_id, inv, "C1", AisleStatus.CREATED, now, now))
    return r


def test_strict_missing_aisle_message() -> None:
    repo = MemoryAisleRepository()
    with pytest.raises(AisleNotFoundError, match="Aisle not found: missing"):
        require_aisle_scoped_to_inventory(
            repo,
            inventory_id="inv-1",
            aisle_id="missing",
            detail_style="strict",
        )


def test_strict_wrong_inventory_message() -> None:
    repo = _repo_with_aisle(inv="other-inv")
    with pytest.raises(AisleNotFoundError, match="does not belong to inventory"):
        require_aisle_scoped_to_inventory(
            repo,
            inventory_id="inv-1",
            aisle_id="a1",
            detail_style="strict",
        )


def test_strict_returns_aisle_when_valid() -> None:
    repo = _repo_with_aisle(inv="inv-1")
    got = require_aisle_scoped_to_inventory(
        repo,
        inventory_id="inv-1",
        aisle_id="a1",
        detail_style="strict",
    )
    assert got.id == "a1"
    assert got.inventory_id == "inv-1"


def test_merged_missing_uses_single_detail_message() -> None:
    repo = MemoryAisleRepository()
    with pytest.raises(AisleNotFoundError) as ei:
        require_aisle_scoped_to_inventory(
            repo,
            inventory_id="inv-1",
            aisle_id="ghost",
            detail_style="merged",
        )
    assert ei.value.args[0] == "Aisle ghost does not belong to inventory inv-1"


def test_merged_wrong_inventory_same_message() -> None:
    repo = _repo_with_aisle(inv="other")
    with pytest.raises(AisleNotFoundError) as ei:
        require_aisle_scoped_to_inventory(
            repo,
            inventory_id="inv-1",
            aisle_id="a1",
            detail_style="merged",
        )
    assert ei.value.args[0] == "Aisle a1 does not belong to inventory inv-1"
