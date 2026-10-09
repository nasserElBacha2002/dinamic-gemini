"""Unit tests — transactional replace for aisle location labels."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.services.positioning_label_signing import (
    PositioningLabelSigningConfig,
    PositioningLabelSigningService,
)
from src.application.use_cases.aisle_locations.manage_aisle_locations import (
    IssueAisleLocationLabelCommand,
    IssueAisleLocationLabelUseCase,
)
from src.application.use_cases.aisle_locations.render_aisle_location_labels import (
    ReplaceAisleLocationLabelCommand,
    ReplaceAisleLocationLabelUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.aisle_location.entities import AisleLocation, AisleLocationStatus
from src.domain.aisle_location.label_entities import AisleLocationLabelStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.infrastructure.persistence.sql_aisle_location_label_replace_uow import (
    MemoryAisleLocationLabelReplaceUnitOfWork,
)
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
        public_identifier="loc_pub_replace_1",
    )
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    loc_repo = MemoryAisleLocationRepository()
    label_repo = MemoryAisleLocationLabelRepository()
    inv_repo.save(inv)
    aisle_repo.save(aisle)
    loc_repo.save(location)
    signing = PositioningLabelSigningService(
        PositioningLabelSigningConfig(secret="unit-test-secret-ok", key_version=1, required=True)
    )
    issue = IssueAisleLocationLabelUseCase(
        location_repo=loc_repo,
        label_repo=label_repo,
        access_policy=policy_for(inv_repo, aisle_repo),
        clock=_FixedClock(),
        signing=signing,
    )
    replace = ReplaceAisleLocationLabelUseCase(
        location_repo=loc_repo,
        label_repo=label_repo,
        replace_uow=MemoryAisleLocationLabelReplaceUnitOfWork(label_repo),
        access_policy=policy_for(inv_repo, aisle_repo),
        clock=_FixedClock(),
        signing=signing,
    )
    return issue, replace, label_repo, location


def test_replace_marks_old_replaced_with_replaced_at_and_one_active() -> None:
    issue, replace, label_repo, location = _setup()
    principal = platform_principal()
    old = issue.execute(
        IssueAisleLocationLabelCommand(
            location_id=location.id,
            inventory_id="inv-1",
            principal=principal,
        )
    )
    new = replace.execute(
        ReplaceAisleLocationLabelCommand(
            inventory_id="inv-1",
            label_id=old.id,
            principal=principal,
            idempotency_key="replace-key-1",
        )
    )
    assert new.id != old.id
    assert new.payload["position_id"] == "loc_pub_replace_1"
    assert new.payload["position_id"] != location.id
    assert "signature" in new.payload
    refreshed_old = label_repo.get_by_id(old.id)
    assert refreshed_old is not None
    assert refreshed_old.status == AisleLocationLabelStatus.REPLACED
    assert refreshed_old.replaced_by_label_id == new.id
    assert refreshed_old.replaced_at is not None
    assert refreshed_old.invalidated_at is None
    active = list(label_repo.list_by_location(location.id, status="ACTIVE"))
    assert len(active) == 1
    assert active[0].id == new.id


def test_replace_idempotent_retry_same_key() -> None:
    issue, replace, label_repo, location = _setup()
    principal = platform_principal()
    old = issue.execute(
        IssueAisleLocationLabelCommand(
            location_id=location.id,
            inventory_id="inv-1",
            principal=principal,
        )
    )
    first = replace.execute(
        ReplaceAisleLocationLabelCommand(
            inventory_id="inv-1",
            label_id=old.id,
            principal=principal,
            idempotency_key="replace-key-2",
        )
    )
    second = replace.execute(
        ReplaceAisleLocationLabelCommand(
            inventory_id="inv-1",
            label_id=old.id,
            principal=principal,
            idempotency_key="replace-key-2",
        )
    )
    assert first.id == second.id
    active = list(label_repo.list_by_location(location.id, status="ACTIVE"))
    assert len(active) == 1
