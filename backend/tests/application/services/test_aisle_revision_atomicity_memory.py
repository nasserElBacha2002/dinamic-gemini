"""Atomicity tests for ApplyAisleRevision using the in-memory unit of work.

Each test injects a failure at a different point of the write sequence (exclusions →
results → positions → finalization → revision) and asserts the aisle is left exactly as it
was. A partially applied revision would publish an authoritative state nobody confirmed.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest

from src.application.use_cases.aisles.apply_aisle_revision import (
    ApplyAisleRevisionCommand,
)
from src.application.use_cases.aisles.manage_aisle_revisions import (
    CreateAisleRevisionCommand,
    UpdateAisleRevisionItemCommand,
)
from src.domain.aisle_revision.entities import AisleRevisionStatus
from src.domain.positions.entities import PositionStatus
from tests.application.services.test_aisle_revision_phase8 import _seed


def _now() -> datetime:
    return datetime(2026, 7, 24, 18, 0, 0, tzinfo=timezone.utc)


class _InjectedWriteError(RuntimeError):
    """Simulates a mid-transaction failure (deadlock, lost connection, crash)."""


def _fail_on(repo: object, method: str) -> None:
    def _explode(*_args: Any, **_kwargs: Any) -> Any:
        raise _InjectedWriteError(f"injected failure in {method}")

    setattr(repo, method, _explode)


def _open_revision_with_quantity_change(ctx: dict[str, Any], quantity: int = 12) -> str:
    revision_id = str(uuid4())
    ctx["create"].execute(
        CreateAisleRevisionCommand(
            inventory_id=ctx["inv_id"],
            aisle_id=ctx["aisle_id"],
            revision_id=revision_id,
            revision_type="MANUAL_CORRECTION",
            reason="Cantidad incorrecta",
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
            quantity=quantity,
            reason="fix qty",
        )
    )
    return revision_id


def _apply(ctx: dict[str, Any], revision_id: str):
    return ctx["apply"].execute(
        ApplyAisleRevisionCommand(
            inventory_id=ctx["inv_id"],
            aisle_id=ctx["aisle_id"],
            revision_id=revision_id,
            apply_id=str(uuid4()),
            expected_base_finalization_id=ctx["fin_id"],
            applied_by="op1",
        )
    )


def _assert_aisle_untouched(ctx: dict[str, Any], revision_id: str) -> None:
    current_result = ctx["auth_repo"].get_current_for_asset(ctx["asset_id"])
    assert current_result is not None
    assert current_result.quantity == 10
    assert current_result.result_version == 1

    current_fin = ctx["fin_repo"].get_current_for_aisle(ctx["aisle_id"])
    assert current_fin is not None
    assert current_fin.id == ctx["fin_id"]
    assert current_fin.finalization_version == 1

    position = ctx["pos_repo"].get_by_id(ctx["position_id"])
    assert position is not None
    assert position.status == PositionStatus.DETECTED
    assert getattr(position, "corrected_summary_json", None) is None
    assert ctx["rev_repo"].get_current_position_version(ctx["position_id"]) is None

    revision = ctx["rev_repo"].get_revision(revision_id)
    assert revision is not None
    assert revision.status != AisleRevisionStatus.COMPLETED.value
    assert revision.new_finalization_id is None

    assert (
        ctx["fin_repo"].get_current_exclusion(
            inventory_id=ctx["inv_id"],
            aisle_id=ctx["aisle_id"],
            asset_id=ctx["asset_id"],
        )
        is None
    )


def test_failure_writing_result_version_rolls_back_everything():
    ctx = _seed()
    revision_id = _open_revision_with_quantity_change(ctx)
    _fail_on(ctx["auth_repo"], "create_authoritative_version")

    with pytest.raises(_InjectedWriteError):
        _apply(ctx, revision_id)

    _assert_aisle_untouched(ctx, revision_id)


def test_failure_writing_position_version_rolls_back_result_version():
    """The result version was already written when the position write fails."""
    ctx = _seed()
    revision_id = _open_revision_with_quantity_change(ctx)
    _fail_on(ctx["rev_repo"], "save_position_version")

    with pytest.raises(_InjectedWriteError):
        _apply(ctx, revision_id)

    _assert_aisle_untouched(ctx, revision_id)


def test_failure_writing_finalization_rolls_back_results_and_positions():
    """Failure at the last mutation: every earlier write must disappear."""
    ctx = _seed()
    revision_id = _open_revision_with_quantity_change(ctx)
    _fail_on(ctx["fin_repo"], "save_finalization")

    with pytest.raises(_InjectedWriteError):
        _apply(ctx, revision_id)

    _assert_aisle_untouched(ctx, revision_id)


def test_failure_completing_revision_rolls_back_published_finalization():
    """The new finalization was already current when the revision row write fails."""
    ctx = _seed()
    revision_id = _open_revision_with_quantity_change(ctx)
    _fail_on(ctx["rev_repo"], "save_revision")

    with pytest.raises(_InjectedWriteError):
        _apply(ctx, revision_id)

    current_fin = ctx["fin_repo"].get_current_for_aisle(ctx["aisle_id"])
    assert current_fin is not None
    assert current_fin.id == ctx["fin_id"]
    current_result = ctx["auth_repo"].get_current_for_asset(ctx["asset_id"])
    assert current_result is not None
    assert current_result.quantity == 10


def test_aisle_lock_is_released_after_rollback_so_retry_can_proceed():
    """A failed apply must not strand the aisle lock, otherwise retries deadlock forever."""
    ctx = _seed()
    revision_id = _open_revision_with_quantity_change(ctx)
    _fail_on(ctx["fin_repo"], "save_finalization")
    with pytest.raises(_InjectedWriteError):
        _apply(ctx, revision_id)

    now = _now()
    acquired = ctx["rev_repo"].try_acquire_lock(
        inventory_id=ctx["inv_id"],
        aisle_id=ctx["aisle_id"],
        owner_token=str(uuid4()),
        lease_expires_at=now + timedelta(seconds=30),
        now=now,
    )
    assert acquired is True


def test_retry_after_transient_failure_applies_cleanly():
    """After a rolled-back attempt the same revision must still be appliable."""
    ctx = _seed()
    revision_id = _open_revision_with_quantity_change(ctx)
    original_save = ctx["fin_repo"].save_finalization
    _fail_on(ctx["fin_repo"], "save_finalization")

    with pytest.raises(_InjectedWriteError):
        _apply(ctx, revision_id)

    # Transient failure cleared; the retry is a brand new attempt from clean state.
    ctx["fin_repo"].save_finalization = original_save
    applied = _apply(ctx, revision_id)

    assert applied.status == AisleRevisionStatus.COMPLETED.value
    current_fin = ctx["fin_repo"].get_current_for_aisle(ctx["aisle_id"])
    assert current_fin is not None
    assert current_fin.id == applied.new_finalization_id
    assert current_fin.finalization_version == 2
    current_result = ctx["auth_repo"].get_current_for_asset(ctx["asset_id"])
    assert current_result is not None
    assert current_result.quantity == 12
    assert current_result.result_version == 2
