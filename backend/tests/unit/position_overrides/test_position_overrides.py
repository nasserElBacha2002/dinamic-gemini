from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from src.application.dto.access_principal import AccessPrincipal
from src.application.position_override_errors import (
    PositionOverrideConflictError,
    PositionOverrideFeatureDisabledError,
    PositionOverrideInvalidActionError,
)
from src.application.services.inventory_access_policy import InventoryAccessPolicy
from src.application.services.position_overrides.effective_position_reader import (
    EffectivePositionReader,
)
from src.application.services.position_reconciliation.published_assignment_read_model import (
    PositionReadAvailability,
    PublishedPositionAssignmentView,
    PublishedPositionRef,
)
from src.application.use_cases.position_overrides.manage import (
    ManagePositionOverrideUseCase,
    PositionOverrideCommand,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.client_position_label.entities import (
    ClientPositionLabel,
    ClientPositionLabelStatus,
)
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
from src.domain.position_overrides.entities import (
    EffectivePositionSource,
    ManualProductPositionOverride,
    PositionOverrideAction,
    PositionOverrideReasonCode,
)
from src.domain.positions.entities import Position, PositionStatus
from src.domain.products.entities import ProductRecord
from src.infrastructure.repositories.memory_manual_position_override_repository import (
    MemoryManualPositionOverrideRepository,
)

NOW = datetime(2026, 8, 3, tzinfo=timezone.utc)


class DictRepo:
    def __init__(self, *rows):
        self.rows = {row.id: row for row in rows}

    def get_by_id(self, row_id):
        return self.rows.get(row_id)


class AutomaticReader:
    def __init__(self, view):
        self.view = view

    def load_for_job(self, job_id, *, result_ids=None):
        return {result_id: replace(self.view, result_id=result_id) for result_id in result_ids or []}


def automatic_view(position_id="auto", name="A-01", reconciliation_id="recon-1"):
    return PublishedPositionAssignmentView(
        result_id="result-1",
        availability=PositionReadAvailability.AVAILABLE,
        position=PublishedPositionRef(id=position_id, name=name),
        assignment_status="ASSIGNED_AUTOMATIC",
        assignment_reason="SEQUENTIAL",
        assignment_source="AUTOMATIC",
        reconciliation_id=reconciliation_id,
        reconciliation_version="1.0.0",
        reconciliation_status="COMPLETED",
        sequence_number=1,
        source_asset_id="asset-1",
        assigned_at=NOW,
    )


def label(label_id="label-b", name="B-01"):
    return ClientPositionLabel(
        id=label_id,
        client_id="client-1",
        public_identifier=f"pub-{label_id}",
        name=name,
        normalized_name=name,
        status=ClientPositionLabelStatus.ACTIVE,
        payload_version=1,
        canonical_payload={},
        created_at=NOW,
        updated_at=NOW,
    )


def principal():
    return AccessPrincipal(
        actor_id="user-1",
        client_id="client-1",
        roles=frozenset({"company_admin"}),
        is_platform=False,
    )


def command(
    *,
    action=PositionOverrideAction.CHANGE_POSITION,
    expected=0,
    key="key-1",
    reason=PositionOverrideReasonCode.WRONG_POSITION_DETECTED,
    reason_text=None,
):
    return PositionOverrideCommand(
        inventory_id="inventory-1",
        job_id="job-1",
        result_id="result-1",
        action=action,
        position_label_id=(
            "label-b"
            if action
            in (PositionOverrideAction.ASSIGN_POSITION, PositionOverrideAction.CHANGE_POSITION)
            else None
        ),
        reason_code=reason,
        reason_text=reason_text,
        expected_effective_version=expected,
        idempotency_key=key,
        principal=principal(),
    )


@pytest.fixture
def setup():
    inventory = Inventory(
        id="inventory-1",
        name="Inventory",
        status=InventoryStatus.PROCESSING,
        created_at=NOW,
        updated_at=NOW,
        client_id="client-1",
    )
    aisle = Aisle(
        id="aisle-1",
        inventory_id=inventory.id,
        code="A",
        status=AisleStatus.PROCESSED,
        created_at=NOW,
        updated_at=NOW,
    )
    job = Job(
        id="job-1",
        target_type="aisle",
        target_id=aisle.id,
        job_type="process",
        status=JobStatus.SUCCEEDED,
        payload_json={},
        created_at=NOW,
        updated_at=NOW,
    )
    position = Position(
        id="position-1",
        aisle_id=aisle.id,
        status=PositionStatus.DETECTED,
        confidence=1.0,
        needs_review=False,
        primary_evidence_id=None,
        created_at=NOW,
        updated_at=NOW,
        job_id=job.id,
    )
    product = ProductRecord(
        id="result-1",
        position_id=position.id,
        sku="SKU",
        detected_quantity=1,
        confidence=1.0,
        created_at=NOW,
        updated_at=NOW,
    )
    inventory_repo = DictRepo(inventory)
    label_repo = DictRepo(label())
    override_repo = MemoryManualPositionOverrideRepository()
    effective_reader = EffectivePositionReader(
        automatic_reader=AutomaticReader(automatic_view()),
        override_repo=override_repo,
        label_repo=label_repo,
    )

    def manager(enabled=True):
        return ManagePositionOverrideUseCase(
            inventory_repo=inventory_repo,
            aisle_repo=DictRepo(aisle),
            job_repo=DictRepo(job),
            position_repo=DictRepo(position),
            product_repo=DictRepo(product),
            label_repo=label_repo,
            override_repo=override_repo,
            effective_reader=effective_reader,
            access_policy=InventoryAccessPolicy(inventory_repo),
            writes_enabled=enabled,
        )

    return manager, override_repo, effective_reader


def test_effective_reader_manual_priority_and_automatic_change_warning(setup):
    _, repo, _ = setup
    manual = ManualProductPositionOverride(
        id="override-1",
        client_id="client-1",
        inventory_id="inventory-1",
        aisle_id="aisle-1",
        job_id="job-1",
        result_id="result-1",
        source_asset_id="asset-1",
        automatic_assignment_id=None,
        automatic_reconciliation_id="recon-0",
        previous_effective_position_label_id="auto",
        new_position_label_id="label-b",
        new_position_name_snapshot="B-01",
        override_action=PositionOverrideAction.CHANGE_POSITION,
        reason_code=PositionOverrideReasonCode.PRODUCT_MOVED,
        reason_text=None,
        created_by_user_id="user-1",
        created_by_role="company_admin",
        idempotency_key="manual-key",
        version=1,
        is_active=True,
        superseded_override_id=None,
        created_at=NOW,
        updated_at=NOW,
    )
    repo.insert_revision_atomically(manual, expected_active_version=0)
    reader = EffectivePositionReader(
        automatic_reader=AutomaticReader(automatic_view(reconciliation_id="recon-2")),
        override_repo=repo,
        label_repo=DictRepo(label()),
    )
    view = reader.load_for_job("job-1", result_ids=["result-1"])["result-1"]
    assert view.effective_source is EffectivePositionSource.MANUAL
    assert view.effective_position.name == "B-01"
    assert "AUTOMATIC_CHANGED_AFTER_OVERRIDE" in view.warnings


def test_assign_change_remove_and_restore(setup):
    manager, repo, _ = setup
    created = manager().execute(command(action=PositionOverrideAction.ASSIGN_POSITION))
    assert created.effective.effective_position.name == "B-01"
    changed = manager().execute(
        command(action=PositionOverrideAction.CHANGE_POSITION, expected=1, key="key-2")
    )
    assert changed.revision.version == 2
    removed = manager().execute(
        command(action=PositionOverrideAction.REMOVE_POSITION, expected=2, key="key-3")
    )
    assert removed.effective.effective_status == "UNASSIGNED_MANUAL"
    restored = manager().execute(
        command(action=PositionOverrideAction.RESTORE_AUTOMATIC, expected=3, key="key-4")
    )
    assert restored.effective.effective_source is EffectivePositionSource.AUTOMATIC
    assert repo.get_active("job-1", "result-1") is None
    assert len(repo.list_history("job-1", "result-1")) == 4


def test_version_conflict(setup):
    manager, _, _ = setup
    manager().execute(command())
    with pytest.raises(PositionOverrideConflictError):
        manager().execute(command(expected=0, key="key-2"))


def test_idempotency_returns_same_revision(setup):
    manager, repo, _ = setup
    first = manager().execute(command())
    second = manager().execute(command())
    assert second.revision.id == first.revision.id
    assert len(repo.list_history("job-1", "result-1")) == 1


def test_other_requires_reason_text(setup):
    manager, _, _ = setup
    with pytest.raises(PositionOverrideInvalidActionError):
        manager().execute(
            command(reason=PositionOverrideReasonCode.OTHER, reason_text=" ")
        )


def test_feature_flag_blocks_writes(setup):
    manager, _, _ = setup
    with pytest.raises(PositionOverrideFeatureDisabledError):
        manager(enabled=False).execute(command())
