"""Scope and authority guards for aisle revisions (Phase 8 corrections).

Covers the capabilities use case (which used to answer from feature flags alone, ignoring the
inventory/aisle it was asked about) and server proposal adoption (where the client used to be
trusted for the internal code and quantity).
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from src.application.errors import AisleNotFoundError, InventoryNotFoundError
from src.application.use_cases.aisles.get_aisle_revision_capabilities import (
    GetAisleRevisionCapabilities,
)
from src.application.use_cases.aisles.manage_aisle_revisions import (
    AisleRevisionConflictError,
    CreateAisleRevisionCommand,
    UpdateAisleRevisionItem,
    UpdateAisleRevisionItemCommand,
)
from src.domain.aisle_revision.entities import AisleRevisionProposalSource
from tests.application.services.test_aisle_revision_phase8 import _seed


def _now() -> datetime:
    return datetime(2026, 7, 24, 18, 0, 0, tzinfo=timezone.utc)


def _capabilities(ctx, *, revisions_enabled=True, rollback_enabled=True):
    return GetAisleRevisionCapabilities(
        revisions_enabled=revisions_enabled,
        rollback_enabled=rollback_enabled,
        inventory_repo=ctx["inv_repo"],
        aisle_repo=ctx["aisle_repo"],
        finalization_repo=ctx["fin_repo"],
        revision_repo=ctx["rev_repo"],
    )


def test_capabilities_reject_unknown_inventory():
    ctx = _seed()
    with pytest.raises(InventoryNotFoundError):
        _capabilities(ctx).execute(inventory_id=str(uuid4()), aisle_id=ctx["aisle_id"])


def test_capabilities_reject_aisle_from_another_inventory():
    ctx = _seed()
    other = _seed()
    with pytest.raises(AisleNotFoundError):
        _capabilities(ctx).execute(inventory_id=ctx["inv_id"], aisle_id=other["aisle_id"])


def test_capabilities_disabled_flag_disables_everything():
    ctx = _seed()
    caps = _capabilities(ctx, revisions_enabled=False).execute(
        inventory_id=ctx["inv_id"], aisle_id=ctx["aisle_id"]
    )
    assert caps.aisle_revisions_enabled is False
    assert caps.aisle_rollback_enabled is False
    assert caps.aisle_history_enabled is False


def test_rollback_unavailable_until_a_superseded_finalization_exists():
    ctx = _seed()
    caps = _capabilities(ctx).execute(inventory_id=ctx["inv_id"], aisle_id=ctx["aisle_id"])
    # The aisle is finalized (v1), so it can be revised, but there is nothing to roll back to.
    assert caps.aisle_revisions_enabled is True
    assert caps.aisle_rollback_enabled is False


def test_rollback_available_after_a_revision_published_v2():
    ctx = _seed()
    revision_id = str(uuid4())
    ctx["create"].execute(
        CreateAisleRevisionCommand(
            inventory_id=ctx["inv_id"],
            aisle_id=ctx["aisle_id"],
            revision_id=revision_id,
            revision_type="MANUAL_CORRECTION",
            reason="fix",
            requested_by="op1",
        )
    )
    ctx["update"].execute(
        UpdateAisleRevisionItemCommand(
            inventory_id=ctx["inv_id"],
            aisle_id=ctx["aisle_id"],
            revision_id=revision_id,
            asset_id=ctx["asset_id"],
            actor_id="op1",
            internal_code="ABC",
            quantity=12,
            reason="qty",
        )
    )
    from src.application.use_cases.aisles.apply_aisle_revision import (
        ApplyAisleRevisionCommand,
    )

    ctx["apply"].execute(
        ApplyAisleRevisionCommand(
            inventory_id=ctx["inv_id"],
            aisle_id=ctx["aisle_id"],
            revision_id=revision_id,
            apply_id=str(uuid4()),
            expected_base_finalization_id=ctx["fin_id"],
            applied_by="op1",
        )
    )
    caps = _capabilities(ctx).execute(inventory_id=ctx["inv_id"], aisle_id=ctx["aisle_id"])
    assert caps.aisle_rollback_enabled is True


def test_rollback_unavailable_while_a_revision_is_open():
    ctx = _seed()
    first = str(uuid4())
    ctx["create"].execute(
        CreateAisleRevisionCommand(
            inventory_id=ctx["inv_id"],
            aisle_id=ctx["aisle_id"],
            revision_id=first,
            revision_type="MANUAL_CORRECTION",
            reason="fix",
            requested_by="op1",
        )
    )
    ctx["update"].execute(
        UpdateAisleRevisionItemCommand(
            inventory_id=ctx["inv_id"],
            aisle_id=ctx["aisle_id"],
            revision_id=first,
            asset_id=ctx["asset_id"],
            actor_id="op1",
            internal_code="ABC",
            quantity=12,
            reason="qty",
        )
    )
    from src.application.use_cases.aisles.apply_aisle_revision import (
        ApplyAisleRevisionCommand,
    )

    ctx["apply"].execute(
        ApplyAisleRevisionCommand(
            inventory_id=ctx["inv_id"],
            aisle_id=ctx["aisle_id"],
            revision_id=first,
            apply_id=str(uuid4()),
            expected_base_finalization_id=ctx["fin_id"],
            applied_by="op1",
        )
    )
    ctx["create"].execute(
        CreateAisleRevisionCommand(
            inventory_id=ctx["inv_id"],
            aisle_id=ctx["aisle_id"],
            revision_id=str(uuid4()),
            revision_type="MANUAL_CORRECTION",
            reason="otra",
            requested_by="op1",
        )
    )
    caps = _capabilities(ctx).execute(inventory_id=ctx["inv_id"], aisle_id=ctx["aisle_id"])
    assert caps.aisle_rollback_enabled is False


class _FakeReprocessRepo:
    def __init__(self, *, proposal=None, run=None) -> None:
        self._proposal = proposal
        self._run = run

    def get_proposal(self, proposal_id: str):
        if self._proposal is not None and self._proposal.id == proposal_id:
            return self._proposal
        return None

    def get_run(self, run_id: str):
        if self._run is not None and self._run.id == run_id:
            return self._run
        return None


class _Proposal:
    def __init__(self, *, asset_id: str, internal_code: str | None, quantity: int | None) -> None:
        self.id = "prop-1"
        self.run_id = "run-1"
        self.asset_id = asset_id
        self.internal_code = internal_code
        self.quantity = quantity


class _Run:
    def __init__(self, *, inventory_id: str, aisle_id: str) -> None:
        self.id = "run-1"
        self.inventory_id = inventory_id
        self.aisle_id = aisle_id


def _open_revision(ctx) -> str:
    revision_id = str(uuid4())
    ctx["create"].execute(
        CreateAisleRevisionCommand(
            inventory_id=ctx["inv_id"],
            aisle_id=ctx["aisle_id"],
            revision_id=revision_id,
            revision_type="MANUAL_CORRECTION",
            reason="adoptar propuesta",
            requested_by="op1",
        )
    )
    return revision_id


def _adopt_command(ctx, revision_id: str, **overrides) -> UpdateAisleRevisionItemCommand:
    payload = {
        "inventory_id": ctx["inv_id"],
        "aisle_id": ctx["aisle_id"],
        "revision_id": revision_id,
        "asset_id": ctx["asset_id"],
        "actor_id": "op1",
        "proposal_source": AisleRevisionProposalSource.SERVER_REPROCESS_PROPOSAL.value,
        "proposal_reference_id": "prop-1",
        "reason": "adoptar",
    }
    payload.update(overrides)
    return UpdateAisleRevisionItemCommand(**payload)


def test_server_proposal_values_win_over_client_supplied_code_and_quantity():
    ctx = _seed()
    revision_id = _open_revision(ctx)
    update = UpdateAisleRevisionItem(
        enabled=True,
        revision_repo=ctx["rev_repo"],
        reprocess_repo=_FakeReprocessRepo(
            proposal=_Proposal(asset_id=ctx["asset_id"], internal_code="SERVER", quantity=7),
            run=_Run(inventory_id=ctx["inv_id"], aisle_id=ctx["aisle_id"]),
        ),
    )
    item = update.execute(
        _adopt_command(ctx, revision_id, internal_code="CLIENT-FORGED", quantity=999)
    )
    assert item.proposed_internal_code == "SERVER"
    assert item.proposed_quantity == 7


def test_server_proposal_requires_a_reference_id():
    ctx = _seed()
    revision_id = _open_revision(ctx)
    update = UpdateAisleRevisionItem(
        enabled=True,
        revision_repo=ctx["rev_repo"],
        reprocess_repo=_FakeReprocessRepo(),
    )
    with pytest.raises(AisleRevisionConflictError) as err:
        update.execute(_adopt_command(ctx, revision_id, proposal_reference_id=None))
    assert err.value.error_code == "AISLE_REVISION_INVALID"


def test_unknown_server_proposal_is_rejected():
    ctx = _seed()
    revision_id = _open_revision(ctx)
    update = UpdateAisleRevisionItem(
        enabled=True,
        revision_repo=ctx["rev_repo"],
        reprocess_repo=_FakeReprocessRepo(
            run=_Run(inventory_id=ctx["inv_id"], aisle_id=ctx["aisle_id"])
        ),
    )
    with pytest.raises(AisleRevisionConflictError) as err:
        update.execute(_adopt_command(ctx, revision_id))
    assert err.value.error_code == "AISLE_REVISION_PROPOSAL_NOT_FOUND"


def test_server_proposal_from_another_aisle_is_rejected():
    ctx = _seed()
    other = _seed()
    revision_id = _open_revision(ctx)
    update = UpdateAisleRevisionItem(
        enabled=True,
        revision_repo=ctx["rev_repo"],
        reprocess_repo=_FakeReprocessRepo(
            proposal=_Proposal(asset_id=ctx["asset_id"], internal_code="SERVER", quantity=7),
            run=_Run(inventory_id=other["inv_id"], aisle_id=other["aisle_id"]),
        ),
    )
    with pytest.raises(AisleRevisionConflictError) as err:
        update.execute(_adopt_command(ctx, revision_id))
    assert err.value.error_code == "AISLE_REVISION_PROPOSAL_OUT_OF_SCOPE"


def test_server_proposal_rejected_when_reprocess_repo_is_unavailable():
    ctx = _seed()
    revision_id = _open_revision(ctx)
    update = UpdateAisleRevisionItem(enabled=True, revision_repo=ctx["rev_repo"])
    with pytest.raises(AisleRevisionConflictError) as err:
        update.execute(_adopt_command(ctx, revision_id))
    assert err.value.error_code == "AISLE_REVISION_SERVER_PROPOSAL_UNAVAILABLE"
