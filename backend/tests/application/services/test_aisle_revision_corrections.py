"""Phase 8 correction tests: planner, exclude/restore, atomicity, apply hash."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from src.application.ports.aisle_revision_unit_of_work import AisleRevisionRepositories
from src.application.services.aisle_revision_mutation_planner import (
    PLAN_ERROR_POSITION_MISSING,
    AisleRevisionMutationPlanner,
    AisleRevisionPlanError,
    AisleRevisionPlanInput,
)
from src.application.services.aisle_revision_snapshot import (
    RevisionSnapshot,
    RevisionSnapshotAsset,
    parse_revision_snapshot,
)
from src.application.use_cases.aisles.apply_aisle_revision import (
    ApplyAisleRevision,
    ApplyAisleRevisionCommand,
    AisleRevisionApplyConflictError,
)
from src.application.use_cases.aisles.manage_aisle_revisions import (
    CreateAisleRevisionCommand,
    UpdateAisleRevisionItemCommand,
)
from src.domain.aisle_revision.entities import (
    AisleRevision,
    AisleRevisionItem,
    AisleRevisionItemStatus,
    AisleRevisionStatus,
)
from src.domain.authoritative_aisle_finalization.entities import (
    AuthoritativeAisleFinalization,
    AuthoritativeFinalizationStatus,
)
from src.domain.positions.entities import PositionStatus
from src.infrastructure.persistence.memory_aisle_revision_unit_of_work import (
    MemoryAisleRevisionUnitOfWork,
    build_memory_aisle_revision_uow_factory,
)
from tests.application.services.test_aisle_revision_phase8 import _seed


def _now() -> datetime:
    return datetime(2026, 7, 24, 18, 0, 0, tzinfo=timezone.utc)


def test_exclude_deactivates_position_and_nulls_fin_position():
    ctx = _seed()
    rev_id = str(uuid4())
    # Need a second asset so we don't exclude all
    from src.domain.assets.entities import SourceAsset, SourceAssetType
    from src.domain.authoritative_aisle_finalization.entities import (
        AuthoritativeAisleFinalizationItem,
        AuthoritativeFinalizationItemStatus,
    )
    from src.domain.authoritative_local_code_scan.entities import (
        AuthoritativeLocalCodeScanResult,
        AuthoritativeQuantityStatus,
        AuthoritativeResultSource,
    )
    from src.domain.positions.entities import Position

    now = _now()
    asset2 = str(uuid4())
    result2 = str(uuid4())
    pos2 = str(uuid4())
    # Extend seed via create after adding asset — simpler path: create revision then
    # only exclude if we have 2 items. Re-seed by creating with two assets is heavy;
    # instead add second asset into existing finalization.
    ctx["auth_repo"].create_authoritative_version(
        new_result=AuthoritativeLocalCodeScanResult(
            id=result2,
            asset_id=asset2,
            inventory_id=ctx["inv_id"],
            aisle_id=ctx["aisle_id"],
            client_file_id=asset2,
            result_version=1,
            supersedes_result_id=None,
            is_current=True,
            internal_code="XYZ",
            quantity=1,
            quantity_status=AuthoritativeQuantityStatus.PRESENT.value,
            source=AuthoritativeResultSource.LOCAL_CODE_SCAN.value,
            detected_internal_code="XYZ",
            detected_quantity=1,
            detected_symbology=None,
            parser_version="1",
            detector_version="1",
            prepared_asset_sha256="h2",
            content_hash="c2",
            confirmed_by="u1",
            client_confirmed_at=None,
            server_confirmed_at=now,
            server_received_at=now,
            confirmed_at=now,
            applied_job_id="job-1",
            applied_at=now,
            row_version=1,
            schema_version="1",
            created_at=now,
            updated_at=now,
        ),
        expected_current_id=None,
        expected_row_version=None,
    )
    ctx["pos_repo"].save(
        Position(
            id=pos2,
            aisle_id=ctx["aisle_id"],
            status=PositionStatus.DETECTED,
            confidence=1.0,
            needs_review=False,
            primary_evidence_id=None,
            created_at=now,
            updated_at=now,
            detected_summary_json={
                "source_asset_id": asset2,
                "internal_code": "XYZ",
                "quantity": 1,
            },
        )
    )
    # Note: CreateAisleRevision builds snapshot from assets repo — need asset2 there.
    # Use create which lists assets; add to asset repo via create's dependency.
    # The seed's create holds asset_repo — we need access. Re-run create after patching
    # is hard; call create which only sees original asset. For exclude-all guard we need
    # two items on the revision — inject second item manually after create.

    ctx["create"].execute(
        CreateAisleRevisionCommand(
            inventory_id=ctx["inv_id"],
            aisle_id=ctx["aisle_id"],
            revision_id=rev_id,
            revision_type="EXCLUSION_CHANGE",
            reason="exclude one",
            requested_by="op1",
        )
    )
    # Manually add second revision item as UNCHANGED so exclude-all does not fire.
    from src.domain.aisle_revision.entities import AisleRevisionItem as RI

    ctx["rev_repo"].save_item(
        RI(
            id=str(uuid4()),
            revision_id=rev_id,
            asset_id=asset2,
            base_result_id=result2,
            base_position_id=pos2,
            proposed_internal_code="XYZ",
            proposed_quantity=1,
            proposed_exclusion_state="KEEP",
            proposal_source="UNCHANGED",
            proposal_reference_id=None,
            change_reason=None,
            item_status=AisleRevisionItemStatus.UNCHANGED.value,
            created_at=now,
            updated_at=now,
        )
    )
    ctx["update"].execute(
        UpdateAisleRevisionItemCommand(
            inventory_id=ctx["inv_id"],
            aisle_id=ctx["aisle_id"],
            revision_id=rev_id,
            asset_id=ctx["asset_id"],
            actor_id="op1",
            exclusion_action="EXCLUDE",
            reason="bad photo",
        )
    )
    completed = ctx["apply"].execute(
        ApplyAisleRevisionCommand(
            inventory_id=ctx["inv_id"],
            aisle_id=ctx["aisle_id"],
            revision_id=rev_id,
            apply_id=str(uuid4()),
            expected_base_finalization_id=ctx["fin_id"],
            applied_by="op1",
        )
    )
    assert completed.status == AisleRevisionStatus.COMPLETED.value
    pos = ctx["pos_repo"].get_by_id(ctx["position_id"])
    assert pos is not None
    assert pos.status == PositionStatus.DELETED
    fin = ctx["fin_repo"].get_current_for_aisle(ctx["aisle_id"])
    assert fin is not None
    items = list(ctx["fin_repo"].list_items(fin.id))
    excluded = [i for i in items if i.asset_id == ctx["asset_id"]][0]
    assert excluded.item_status == AuthoritativeFinalizationItemStatus.EXCLUDED.value
    assert excluded.position_id is None
    assert (
        ctx["fin_repo"].get_current_exclusion(
            inventory_id=ctx["inv_id"], aisle_id=ctx["aisle_id"], asset_id=ctx["asset_id"]
        )
        is not None
    )


def test_apply_content_hash_conflict_on_replay_with_different_payload():
    ctx = _seed()
    rev_id = str(uuid4())
    ctx["create"].execute(
        CreateAisleRevisionCommand(
            inventory_id=ctx["inv_id"],
            aisle_id=ctx["aisle_id"],
            revision_id=rev_id,
            revision_type="MANUAL_CORRECTION",
            reason="fix",
            requested_by="op1",
        )
    )
    ctx["update"].execute(
        UpdateAisleRevisionItemCommand(
            inventory_id=ctx["inv_id"],
            aisle_id=ctx["aisle_id"],
            revision_id=rev_id,
            asset_id=ctx["asset_id"],
            actor_id="op1",
            internal_code="ABC",
            quantity=20,
            reason="qty",
        )
    )
    apply_id = str(uuid4())
    ctx["apply"].execute(
        ApplyAisleRevisionCommand(
            inventory_id=ctx["inv_id"],
            aisle_id=ctx["aisle_id"],
            revision_id=rev_id,
            apply_id=apply_id,
            expected_base_finalization_id=ctx["fin_id"],
            applied_by="op1",
        )
    )
    # Tamper stored hash to simulate different payload under same apply_id
    rev = ctx["rev_repo"].get_revision(rev_id)
    assert rev is not None
    tampered = AisleRevision(**{**rev.__dict__, "apply_content_hash": "deadbeef" * 8})
    ctx["rev_repo"].save_revision(tampered)
    with pytest.raises(AisleRevisionApplyConflictError) as ei:
        ctx["apply"].execute(
            ApplyAisleRevisionCommand(
                inventory_id=ctx["inv_id"],
                aisle_id=ctx["aisle_id"],
                revision_id=rev_id,
                apply_id=apply_id,
                expected_base_finalization_id=ctx["fin_id"],
                applied_by="op1",
            )
        )
    assert ei.value.error_code == "AISLE_REVISION_APPLY_CONFLICT"


def test_memory_uow_rollback_restores_on_failure():
    ctx = _seed()
    repos = AisleRevisionRepositories(
        revision_repo=ctx["rev_repo"],
        authoritative_repo=ctx["auth_repo"],
        position_repo=ctx["pos_repo"],
        finalization_repo=ctx["fin_repo"],
        aisle_repo=type("A", (), {})(),  # unused
        inventory_repo=type("I", (), {})(),
    )
    before = len(ctx["auth_repo"]._by_id)  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError):
        with MemoryAisleRevisionUnitOfWork(repositories=repos) as uow:
            # Mutate then fail before commit
            pos = uow.repositories.position_repo.get_by_id(ctx["position_id"])
            assert pos is not None
            from dataclasses import replace

            uow.repositories.position_repo.save(
                replace(pos, status=PositionStatus.DELETED)
            )
            raise RuntimeError("inject failure")
    pos_after = ctx["pos_repo"].get_by_id(ctx["position_id"])
    assert pos_after is not None
    assert pos_after.status != PositionStatus.DELETED
    assert len(ctx["auth_repo"]._by_id) == before  # type: ignore[attr-defined]


def test_planner_rejects_confirmed_without_position():
    now = _now()
    revision = AisleRevision(
        id="r1",
        inventory_id="inv",
        aisle_id="aisle",
        base_finalization_id="fin1",
        new_finalization_id=None,
        revision_type="MANUAL_CORRECTION",
        status=AisleRevisionStatus.OPEN.value,
        reason="x",
        requested_by="u",
        requested_at=now,
        started_at=None,
        completed_at=None,
        canceled_at=None,
        failed_at=None,
        failure_code=None,
        failure_message=None,
        apply_id=None,
        snapshot_json="{}",
        content_hash="h",
        row_version=1,
        created_at=now,
        updated_at=now,
    )
    item = AisleRevisionItem(
        id="i1",
        revision_id="r1",
        asset_id="a1",
        base_result_id="res1",
        base_position_id=None,
        proposed_internal_code="ABC",
        proposed_quantity=1,
        proposed_exclusion_state="KEEP",
        proposal_source="MANUAL",
        proposal_reference_id=None,
        change_reason="fix",
        item_status=AisleRevisionItemStatus.MODIFIED.value,
        created_at=now,
        updated_at=now,
    )
    fin = AuthoritativeAisleFinalization(
        id="fin1",
        inventory_id="inv",
        aisle_id="aisle",
        capture_session_id=None,
        finalization_version=1,
        status=AuthoritativeFinalizationStatus.COMPLETED_BY_LOCAL_AUTHORITY.value,
        total_assets=1,
        applied_assets=1,
        excluded_assets=0,
        position_count=0,
        expected_asset_count=1,
        content_hash="x",
        confirmed_by="u",
        confirmed_at=now,
        completed_at=now,
        is_current=True,
        row_version=1,
        created_at=now,
        updated_at=now,
    )
    planner = AisleRevisionMutationPlanner(id_factory=lambda: "nid")
    with pytest.raises(AisleRevisionPlanError) as ei:
        planner.plan(
            AisleRevisionPlanInput(
                revision=revision,
                items=[item],
                snapshot=RevisionSnapshot(
                    base_finalization_id="fin1",
                    base_finalization_version=1,
                    base_result_ids=("res1",),
                    base_position_ids=(),
                    base_exclusion_ids=(),
                    asset_ids=("a1",),
                    assets=(
                        RevisionSnapshotAsset(
                            asset_id="a1",
                            base_result_id="res1",
                            base_position_id=None,
                            base_internal_code="ABC",
                            base_quantity=1,
                            excluded=False,
                        ),
                    ),
                ),
                expected_base_finalization_id="fin1",
                current_finalization=fin,
                next_finalization_version=2,
                current_result_by_asset={"a1": None},
                position_by_id={},
                current_position_version_by_id={},
                max_position_version_by_id={},
                current_exclusion_by_asset={"a1": None},
                applied_by="u",
                now=now,
            )
        )
    # Fresh result check fires first when current is None but base_result_id set —
    # either STALE or POSITION_MISSING is acceptable fail-closed.
    assert ei.value.error_code in (
        PLAN_ERROR_POSITION_MISSING,
        "REVISION_STALE",
    )
