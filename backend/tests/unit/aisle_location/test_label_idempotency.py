"""Unit tests — durable aisle location label idempotency."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.errors import IdempotencyKeyReusedError
from src.application.use_cases.aisle_locations.manage_aisle_locations import (
    IssueAisleLocationLabelCommand,
    IssueAisleLocationLabelUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.aisle_location.entities import AisleLocation, AisleLocationStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.infrastructure.repositories.memory_aisle_location_repository import (
    MemoryAisleLocationLabelRepository,
    MemoryAisleLocationRepository,
)
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_inventory_repository import (
    MemoryInventoryRepository,
)
from tests.support.access_principal_helpers import platform_principal, policy_for


class _FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 7, 17, tzinfo=timezone.utc)


def _setup():
    now = datetime(2026, 7, 17, tzinfo=timezone.utc)
    inv = Inventory(
        id="inv-1",
        name="Inv",
        status=InventoryStatus.DRAFT,
        created_at=now,
        updated_at=now,
        client_id="client-1",
    )
    aisle = Aisle(
        id="aisle-1",
        inventory_id="inv-1",
        code="A1",
        status=AisleStatus.CREATED,
        created_at=now,
        updated_at=now,
        is_active=True,
    )
    location = AisleLocation(
        id="loc-1",
        client_id="client-1",
        aisle_id="aisle-1",
        code="B-01",
        normalized_code="B-01",
        status=AisleLocationStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    loc_repo = MemoryAisleLocationRepository()
    label_repo = MemoryAisleLocationLabelRepository()
    inv_repo.save(inv)
    aisle_repo.save(aisle)
    loc_repo.save(location)
    use_case = IssueAisleLocationLabelUseCase(
        location_repo=loc_repo,
        label_repo=label_repo,
        access_policy=policy_for(inv_repo, aisle_repo),
        clock=_FixedClock(),
    )
    return use_case, label_repo


def test_label_idempotency_same_key_same_hash_returns_existing() -> None:
    use_case, label_repo = _setup()
    principal = platform_principal()
    cmd = IssueAisleLocationLabelCommand(
        location_id="loc-1",
        inventory_id="inv-1",
        principal=principal,
        idempotency_key="label-key-1",
    )
    first = use_case.execute(cmd)
    second = use_case.execute(cmd)
    assert second.id == first.id
    assert first.idempotency_key == "label-key-1"
    assert first.idempotency_request_hash
    assert len(list(label_repo.list_by_location("loc-1"))) == 1


def test_label_idempotency_same_key_different_hash_conflicts() -> None:
    use_case, label_repo = _setup()
    principal = platform_principal()
    first = use_case.execute(
        IssueAisleLocationLabelCommand(
            location_id="loc-1",
            inventory_id="inv-1",
            principal=principal,
            idempotency_key="label-key-1",
        )
    )
    # Simulate a prior durable row with the same key but a different fingerprint.
    first.idempotency_request_hash = "0" * 64
    label_repo.save(first)
    with pytest.raises(IdempotencyKeyReusedError):
        use_case.execute(
            IssueAisleLocationLabelCommand(
                location_id="loc-1",
                inventory_id="inv-1",
                principal=principal,
                idempotency_key="label-key-1",
            )
        )
