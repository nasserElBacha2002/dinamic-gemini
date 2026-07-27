"""Unit tests for the pure aisle revision mutation planner (Phase 8 corrections)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.services.aisle_revision_mutation_planner import (
    PLAN_ERROR_EMPTY,
    PLAN_ERROR_INVALID,
    PLAN_ERROR_POSITION_MISSING,
    PLAN_ERROR_POSITION_SCOPE_MISMATCH,
    PLAN_ERROR_POSITION_VERSION_CONFLICT,
    PLAN_ERROR_REVISION_STALE,
    RESULT_VERSION_ASSIGNED_BY_REPOSITORY,
    AisleRevisionMutationPlanner,
    AisleRevisionPlanError,
    AisleRevisionPlanInput,
)
from src.application.services.aisle_revision_snapshot import (
    RevisionSnapshot,
    RevisionSnapshotAsset,
)
from src.domain.aisle_revision.entities import (
    AisleRevision,
    AisleRevisionItem,
    AisleRevisionItemStatus,
    AisleRevisionStatus,
    PositionVersion,
)
from src.domain.authoritative_aisle_finalization.entities import (
    AuthoritativeAisleExcludedAsset,
    AuthoritativeAisleFinalization,
    AuthoritativeFinalizationItemStatus,
    AuthoritativeFinalizationStatus,
)
from src.domain.authoritative_local_code_scan.entities import (
    AuthoritativeLocalCodeScanResult,
    AuthoritativeQuantityStatus,
    AuthoritativeResultSource,
)
from src.domain.positions.entities import Position, PositionStatus

INV = "inv-1"
AISLE = "aisle-1"
FIN = "fin-1"
NOW = datetime(2026, 7, 24, 18, 0, 0, tzinfo=timezone.utc)


def _revision() -> AisleRevision:
    return AisleRevision(
        id="rev-1",
        inventory_id=INV,
        aisle_id=AISLE,
        base_finalization_id=FIN,
        new_finalization_id=None,
        revision_type="MANUAL_CORRECTION",
        status=AisleRevisionStatus.OPEN.value,
        reason="corrección",
        requested_by="op1",
        requested_at=NOW,
        started_at=NOW,
        completed_at=None,
        canceled_at=None,
        failed_at=None,
        failure_code=None,
        failure_message=None,
        apply_id=None,
        snapshot_json="{}",
        content_hash="ch",
        row_version=1,
        created_at=NOW,
        updated_at=NOW,
    )


def _item(
    *,
    asset_id: str,
    item_status: str,
    code: str | None = "ABC",
    quantity: int | None = 10,
    position_id: str | None = "pos-1",
    result_id: str | None = "res-1",
    exclusion_state: str | None = "KEEP",
    base_position_version_id: str | None = None,
    base_position_row_version: int | None = None,
) -> AisleRevisionItem:
    return AisleRevisionItem(
        id=f"item-{asset_id}",
        revision_id="rev-1",
        asset_id=asset_id,
        base_result_id=result_id,
        base_position_id=position_id,
        proposed_internal_code=code,
        proposed_quantity=quantity,
        proposed_exclusion_state=exclusion_state,
        proposal_source="MANUAL",
        proposal_reference_id=None,
        change_reason="motivo",
        item_status=item_status,
        created_at=NOW,
        updated_at=NOW,
        base_position_version_id=base_position_version_id,
        base_position_row_version=base_position_row_version,
    )


def _snapshot_asset(
    *,
    asset_id: str,
    code: str | None = "ABC",
    quantity: int | None = 10,
    position_id: str | None = "pos-1",
    result_id: str | None = "res-1",
    excluded: bool = False,
    base_position_version_id: str | None = None,
) -> RevisionSnapshotAsset:
    return RevisionSnapshotAsset(
        asset_id=asset_id,
        base_result_id=result_id,
        base_position_id=position_id,
        base_internal_code=code,
        base_quantity=quantity,
        excluded=excluded,
        base_position_version_id=base_position_version_id,
    )


def _snapshot(*assets: RevisionSnapshotAsset) -> RevisionSnapshot:
    return RevisionSnapshot(
        base_finalization_id=FIN,
        base_finalization_version=1,
        base_result_ids=tuple(a.base_result_id for a in assets if a.base_result_id),
        base_position_ids=tuple(a.base_position_id for a in assets if a.base_position_id),
        base_exclusion_ids=(),
        asset_ids=tuple(a.asset_id for a in assets),
        assets=assets,
    )


def _finalization() -> AuthoritativeAisleFinalization:
    return AuthoritativeAisleFinalization(
        id=FIN,
        inventory_id=INV,
        aisle_id=AISLE,
        capture_session_id=None,
        finalization_version=1,
        status=AuthoritativeFinalizationStatus.COMPLETED_BY_LOCAL_AUTHORITY.value,
        total_assets=1,
        applied_assets=1,
        excluded_assets=0,
        position_count=1,
        expected_asset_count=1,
        content_hash="fh",
        confirmed_by="op1",
        confirmed_at=NOW,
        completed_at=NOW,
        is_current=True,
        row_version=1,
        created_at=NOW,
        updated_at=NOW,
    )


def _result(*, result_id: str, asset_id: str, code: str = "ABC", quantity: int | None = 10):
    return AuthoritativeLocalCodeScanResult(
        id=result_id,
        asset_id=asset_id,
        inventory_id=INV,
        aisle_id=AISLE,
        client_file_id=asset_id,
        result_version=1,
        supersedes_result_id=None,
        is_current=True,
        internal_code=code,
        quantity=quantity,
        quantity_status=AuthoritativeQuantityStatus.PRESENT.value,
        source=AuthoritativeResultSource.LOCAL_CODE_SCAN.value,
        detected_internal_code=code,
        detected_quantity=quantity,
        detected_symbology=None,
        parser_version="1",
        detector_version="1",
        prepared_asset_sha256="sha",
        content_hash="ch",
        confirmed_by="op1",
        client_confirmed_at=None,
        server_confirmed_at=NOW,
        server_received_at=NOW,
        confirmed_at=NOW,
        applied_job_id="job-1",
        applied_at=NOW,
        row_version=3,
        schema_version="1",
        created_at=NOW,
        updated_at=NOW,
    )


def _position(*, position_id: str = "pos-1", aisle_id: str = AISLE) -> Position:
    return Position(
        id=position_id,
        aisle_id=aisle_id,
        status=PositionStatus.DETECTED,
        confidence=1.0,
        needs_review=False,
        primary_evidence_id=None,
        created_at=NOW,
        updated_at=NOW,
        detected_summary_json={"source_asset_id": "a1", "internal_code": "ABC", "quantity": 10},
    )


def _position_version(*, version_id: str, position_id: str = "pos-1") -> PositionVersion:
    return PositionVersion(
        id=version_id,
        position_id=position_id,
        version=4,
        aisle_id=AISLE,
        asset_id="a1",
        internal_code="ABC",
        quantity=10,
        result_id="res-1",
        is_current=True,
        supersedes_position_version_id=None,
        revision_id=None,
        revision_item_id=None,
        created_by="op1",
        created_at=NOW,
        content_hash="pvh",
    )


def _exclusion(*, asset_id: str) -> AuthoritativeAisleExcludedAsset:
    return AuthoritativeAisleExcludedAsset(
        id=f"excl-{asset_id}",
        inventory_id=INV,
        aisle_id=AISLE,
        asset_id=asset_id,
        reason="USER_EXCLUDED",
        excluded_by="op1",
        excluded_at=NOW,
        is_current=True,
        created_at=NOW,
        updated_at=NOW,
    )


def _plan_input(
    *,
    items,
    assets,
    current_finalization=None,
    results=None,
    positions=None,
    position_versions=None,
    max_position_versions=None,
    exclusions=None,
    expected_base: str = FIN,
) -> AisleRevisionPlanInput:
    return AisleRevisionPlanInput(
        revision=_revision(),
        items=tuple(items),
        snapshot=_snapshot(*assets),
        expected_base_finalization_id=expected_base,
        current_finalization=(
            _finalization() if current_finalization is None else current_finalization
        ),
        next_finalization_version=2,
        current_result_by_asset=results or {},
        position_by_id=positions if positions is not None else {"pos-1": _position()},
        current_position_version_by_id=position_versions or {},
        max_position_version_by_id=max_position_versions or {"pos-1": 4},
        current_exclusion_by_asset=exclusions or {},
        applied_by="op1",
        now=NOW,
    )


def _planner() -> AisleRevisionMutationPlanner:
    counter = {"n": 0}

    def ids() -> str:
        counter["n"] += 1
        return f"id-{counter['n']}"

    return AisleRevisionMutationPlanner(id_factory=ids)


def test_modified_item_plans_result_and_position_version_without_hardcoded_version():
    plan = _planner().plan(
        _plan_input(
            items=[
                _item(
                    asset_id="a1", item_status=AisleRevisionItemStatus.MODIFIED.value, quantity=12
                )
            ],
            assets=[_snapshot_asset(asset_id="a1")],
            results={"a1": _result(result_id="res-1", asset_id="a1")},
        )
    )
    assert len(plan.results_to_version) == 1
    result_op = plan.results_to_version[0]
    # The repository derives the authoritative next version under lock.
    assert result_op.new_result.result_version == RESULT_VERSION_ASSIGNED_BY_REPOSITORY
    assert result_op.expected_current_id == "res-1"
    assert result_op.expected_row_version == 3
    assert result_op.new_result.quantity == 12

    assert len(plan.positions_to_version) == 1
    position_op = plan.positions_to_version[0]
    assert position_op.position_version.version == 5
    assert position_op.position_version.result_id == result_op.new_result.id
    assert position_op.corrected_summary["quantity"] == 12

    assert plan.applied_count == 1
    assert plan.excluded_count == 0
    assert plan.finalization_items[0].item_status == (
        AuthoritativeFinalizationItemStatus.CONFIRMED_AND_APPLIED.value
    )
    assert plan.finalization_items[0].position_id == "pos-1"


def test_unchanged_item_publishes_without_new_result_version():
    plan = _planner().plan(
        _plan_input(
            items=[
                _item(
                    asset_id="a1", item_status=AisleRevisionItemStatus.MODIFIED.value, quantity=99
                ),
                _item(
                    asset_id="a2",
                    item_status=AisleRevisionItemStatus.UNCHANGED.value,
                    position_id="pos-2",
                    result_id="res-2",
                ),
            ],
            assets=[
                _snapshot_asset(asset_id="a1"),
                _snapshot_asset(asset_id="a2", position_id="pos-2", result_id="res-2"),
            ],
            results={
                "a1": _result(result_id="res-1", asset_id="a1"),
                "a2": _result(result_id="res-2", asset_id="a2"),
            },
            positions={"pos-1": _position(), "pos-2": _position(position_id="pos-2")},
            max_position_versions={"pos-1": 4, "pos-2": 0},
        )
    )
    assert {op.asset_id for op in plan.results_to_version} == {"a1"}
    unchanged = next(fi for fi in plan.finalization_items if fi.asset_id == "a2")
    assert unchanged.authoritative_result_id == "res-2"
    assert plan.applied_count == 2
    assert plan.changed_count == 1


def test_exclude_plans_exclusion_supersede_and_position_deactivation():
    plan = _planner().plan(
        _plan_input(
            items=[
                _item(
                    asset_id="a1",
                    item_status=AisleRevisionItemStatus.EXCLUDED.value,
                    exclusion_state="EXCLUDE",
                ),
                _item(
                    asset_id="a2",
                    item_status=AisleRevisionItemStatus.UNCHANGED.value,
                    position_id="pos-2",
                    result_id="res-2",
                ),
            ],
            assets=[
                _snapshot_asset(asset_id="a1"),
                _snapshot_asset(asset_id="a2", position_id="pos-2", result_id="res-2"),
            ],
            results={
                "a1": _result(result_id="res-1", asset_id="a1"),
                "a2": _result(result_id="res-2", asset_id="a2"),
            },
            positions={"pos-1": _position(), "pos-2": _position(position_id="pos-2")},
            max_position_versions={"pos-1": 4, "pos-2": 0},
            exclusions={"a1": _exclusion(asset_id="a1")},
        )
    )
    assert [op.asset_id for op in plan.exclusions_to_create] == ["a1"]
    assert plan.exclusions_to_supersede == ("a1",)
    assert [op.position_id for op in plan.positions_to_deactivate] == ["pos-1"]
    excluded_item = next(fi for fi in plan.finalization_items if fi.asset_id == "a1")
    assert excluded_item.item_status == AuthoritativeFinalizationItemStatus.EXCLUDED.value
    assert excluded_item.position_id is None
    assert excluded_item.authoritative_result_id == "res-1"
    assert plan.excluded_count == 1
    assert plan.applied_count == 1


def test_restore_supersedes_exclusion_and_republishes_result():
    plan = _planner().plan(
        _plan_input(
            items=[
                _item(
                    asset_id="a1",
                    item_status=AisleRevisionItemStatus.RESTORED.value,
                    exclusion_state="RESTORE",
                )
            ],
            assets=[_snapshot_asset(asset_id="a1", excluded=True)],
            results={"a1": _result(result_id="res-1", asset_id="a1")},
            exclusions={"a1": _exclusion(asset_id="a1")},
        )
    )
    assert plan.exclusions_to_supersede == ("a1",)
    assert plan.exclusions_to_create == ()
    # RESTORED always republishes so the new finalization points at a live result version.
    assert len(plan.results_to_version) == 1
    assert plan.finalization_items[0].item_status == (
        AuthoritativeFinalizationItemStatus.CONFIRMED_AND_APPLIED.value
    )
    assert plan.finalization_items[0].position_id == "pos-1"


def test_confirmed_item_without_position_is_rejected():
    with pytest.raises(AisleRevisionPlanError) as err:
        _planner().plan(
            _plan_input(
                items=[
                    _item(
                        asset_id="a1",
                        item_status=AisleRevisionItemStatus.MODIFIED.value,
                        position_id=None,
                        result_id=None,
                        quantity=12,
                    )
                ],
                assets=[_snapshot_asset(asset_id="a1", position_id=None, result_id=None)],
                results={"a1": None},
                positions={},
            )
        )
    assert err.value.error_code == PLAN_ERROR_POSITION_MISSING


def test_missing_position_row_is_rejected():
    with pytest.raises(AisleRevisionPlanError) as err:
        _planner().plan(
            _plan_input(
                items=[
                    _item(
                        asset_id="a1",
                        item_status=AisleRevisionItemStatus.MODIFIED.value,
                        quantity=12,
                    )
                ],
                assets=[_snapshot_asset(asset_id="a1")],
                results={"a1": _result(result_id="res-1", asset_id="a1")},
                positions={"pos-1": None},
            )
        )
    assert err.value.error_code == PLAN_ERROR_POSITION_MISSING


def test_position_in_another_aisle_is_rejected():
    with pytest.raises(AisleRevisionPlanError) as err:
        _planner().plan(
            _plan_input(
                items=[
                    _item(
                        asset_id="a1",
                        item_status=AisleRevisionItemStatus.MODIFIED.value,
                        quantity=12,
                    )
                ],
                assets=[_snapshot_asset(asset_id="a1")],
                results={"a1": _result(result_id="res-1", asset_id="a1")},
                positions={"pos-1": _position(aisle_id="other-aisle")},
            )
        )
    assert err.value.error_code == PLAN_ERROR_POSITION_SCOPE_MISMATCH


def test_position_version_compare_and_swap_conflict():
    with pytest.raises(AisleRevisionPlanError) as err:
        _planner().plan(
            _plan_input(
                items=[
                    _item(
                        asset_id="a1",
                        item_status=AisleRevisionItemStatus.MODIFIED.value,
                        quantity=12,
                        base_position_version_id="pv-old",
                    )
                ],
                assets=[_snapshot_asset(asset_id="a1", base_position_version_id="pv-old")],
                results={"a1": _result(result_id="res-1", asset_id="a1")},
                position_versions={"pos-1": _position_version(version_id="pv-new")},
            )
        )
    assert err.value.error_code == PLAN_ERROR_POSITION_VERSION_CONFLICT


def test_position_version_compare_and_swap_passes_when_unchanged():
    plan = _planner().plan(
        _plan_input(
            items=[
                _item(
                    asset_id="a1",
                    item_status=AisleRevisionItemStatus.MODIFIED.value,
                    quantity=12,
                    base_position_version_id="pv-current",
                )
            ],
            assets=[_snapshot_asset(asset_id="a1", base_position_version_id="pv-current")],
            results={"a1": _result(result_id="res-1", asset_id="a1")},
            position_versions={"pos-1": _position_version(version_id="pv-current")},
        )
    )
    assert plan.positions_to_version[0].position_version.supersedes_position_version_id == (
        "pv-current"
    )


def test_stale_when_expected_base_does_not_match():
    with pytest.raises(AisleRevisionPlanError) as err:
        _planner().plan(
            _plan_input(
                items=[_item(asset_id="a1", item_status=AisleRevisionItemStatus.MODIFIED.value)],
                assets=[_snapshot_asset(asset_id="a1")],
                expected_base="other-fin",
            )
        )
    assert err.value.error_code == PLAN_ERROR_REVISION_STALE


def test_stale_when_base_result_superseded_elsewhere():
    with pytest.raises(AisleRevisionPlanError) as err:
        _planner().plan(
            _plan_input(
                items=[
                    _item(
                        asset_id="a1",
                        item_status=AisleRevisionItemStatus.MODIFIED.value,
                        quantity=12,
                    )
                ],
                assets=[_snapshot_asset(asset_id="a1")],
                results={"a1": _result(result_id="res-other", asset_id="a1")},
            )
        )
    assert err.value.error_code == PLAN_ERROR_REVISION_STALE


def test_empty_revision_is_rejected():
    with pytest.raises(AisleRevisionPlanError) as err:
        _planner().plan(
            _plan_input(
                items=[_item(asset_id="a1", item_status=AisleRevisionItemStatus.UNCHANGED.value)],
                assets=[_snapshot_asset(asset_id="a1")],
                results={"a1": _result(result_id="res-1", asset_id="a1")},
            )
        )
    assert err.value.error_code == PLAN_ERROR_EMPTY


def test_excluding_every_asset_is_rejected():
    with pytest.raises(AisleRevisionPlanError) as err:
        _planner().plan(
            _plan_input(
                items=[
                    _item(
                        asset_id="a1",
                        item_status=AisleRevisionItemStatus.EXCLUDED.value,
                        exclusion_state="EXCLUDE",
                    )
                ],
                assets=[_snapshot_asset(asset_id="a1")],
                results={"a1": _result(result_id="res-1", asset_id="a1")},
            )
        )
    assert err.value.error_code == PLAN_ERROR_INVALID


def test_apply_content_hash_is_stable_and_payload_sensitive():
    revision = _revision()
    base = [
        _item(asset_id="a2", item_status=AisleRevisionItemStatus.MODIFIED.value, quantity=12),
        _item(asset_id="a1", item_status=AisleRevisionItemStatus.UNCHANGED.value),
    ]
    reordered = list(reversed(base))
    hash_a = AisleRevisionMutationPlanner.apply_content_hash(revision=revision, items=base)
    hash_b = AisleRevisionMutationPlanner.apply_content_hash(revision=revision, items=reordered)
    assert hash_a == hash_b

    edited = [
        _item(asset_id="a2", item_status=AisleRevisionItemStatus.MODIFIED.value, quantity=13),
        _item(asset_id="a1", item_status=AisleRevisionItemStatus.UNCHANGED.value),
    ]
    assert (
        AisleRevisionMutationPlanner.apply_content_hash(revision=revision, items=edited) != hash_a
    )


def test_plan_hash_matches_standalone_hash():
    items = [_item(asset_id="a1", item_status=AisleRevisionItemStatus.MODIFIED.value, quantity=12)]
    plan = _planner().plan(
        _plan_input(
            items=items,
            assets=[_snapshot_asset(asset_id="a1")],
            results={"a1": _result(result_id="res-1", asset_id="a1")},
        )
    )
    assert plan.apply_content_hash == AisleRevisionMutationPlanner.apply_content_hash(
        revision=_revision(), items=items
    )
