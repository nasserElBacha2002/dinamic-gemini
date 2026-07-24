"""Phase 7 server reprocess unit tests — proposals never overwrite current authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pytest

from src.application.services.server_reprocess_difference import (
    classify_server_reprocess_difference,
)
from src.application.use_cases.aisles.adopt_server_reprocess_proposals import (
    AdoptItemCommand,
    AdoptServerReprocessCommand,
    AdoptServerReprocessProposals,
    ServerReprocessStaleProposalError,
)
from src.application.use_cases.aisles.create_server_reprocess_run import (
    CreateServerReprocessCommand,
    CreateServerReprocessRun,
    ServerReprocessInvalidScopeError,
    ServerReprocessRequestConflictError,
)
from src.application.use_cases.aisles.execute_server_reprocess_run import (
    CancelServerReprocessRun,
    ExecuteServerReprocessRun,
)
from src.application.use_cases.aisles.list_server_reprocess_proposals import (
    ListServerReprocessProposals,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.authoritative_local_code_scan.entities import AuthoritativeLocalCodeScanResult
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.server_reprocess.entities import (
    RemoteProposalInput,
    ServerReprocessDifferenceType,
    ServerReprocessRunAsset,
)
from src.infrastructure.repositories.memory_authoritative_local_code_scan_repository import (
    MemoryAuthoritativeLocalCodeScanRepository,
)
from src.infrastructure.repositories.memory_server_reprocess_repository import (
    MemoryServerReprocessRepository,
)


class _FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


@dataclass
class _MemAisleRepo:
    aisles: dict[str, Aisle]

    def get_by_id(self, aisle_id: str) -> Aisle | None:
        return self.aisles.get(aisle_id)

    def save(self, aisle: Aisle) -> None:
        self.aisles[aisle.id] = aisle


@dataclass
class _MemInvRepo:
    inventories: dict[str, Inventory]

    def get_by_id(self, inventory_id: str) -> Inventory | None:
        return self.inventories.get(inventory_id)

    def save(self, inv: Inventory) -> None:
        self.inventories[inv.id] = inv


@dataclass
class _MemAssetRepo:
    assets: list[SourceAsset]

    def list_by_aisle(self, aisle_id: str):
        return [a for a in self.assets if a.aisle_id == aisle_id]


def _now() -> datetime:
    return datetime(2026, 7, 1, tzinfo=timezone.utc)


def _asset(aid: str) -> SourceAsset:
    now = _now()
    return SourceAsset(
        id=aid,
        aisle_id="a1",
        type=SourceAssetType.PHOTO,
        original_filename=f"{aid}.jpg",
        storage_path=f"/tmp/{aid}.jpg",
        mime_type="image/jpeg",
        uploaded_at=now,
    )


def _auth_row(*, rid: str, asset_id: str, code: str = "SKU1") -> AuthoritativeLocalCodeScanResult:
    now = _now()
    return AuthoritativeLocalCodeScanResult(
        id=rid,
        asset_id=asset_id,
        inventory_id="i1",
        aisle_id="a1",
        client_file_id=f"cf-{asset_id}",
        result_version=1,
        supersedes_result_id=None,
        is_current=True,
        internal_code=code,
        quantity=1,
        quantity_status="PRESENT",
        source="LOCAL_CODE_SCAN",
        detected_internal_code=code,
        detected_quantity=1,
        detected_symbology="EAN_13",
        parser_version="1",
        detector_version="1",
        prepared_asset_sha256="sha",
        content_hash=f"hash-{rid}",
        confirmed_by="u1",
        client_confirmed_at=now,
        server_confirmed_at=now,
        server_received_at=now,
        confirmed_at=now,
        applied_job_id="j1",
        applied_at=now,
        row_version=1,
        schema_version="1",
        created_at=now,
        updated_at=now,
    )


def _aisle() -> Aisle:
    now = _now()
    return Aisle(
        id="a1",
        inventory_id="i1",
        code="A1",
        status=AisleStatus.COMPLETED,
        created_at=now,
        updated_at=now,
    )


def _inventory() -> Inventory:
    now = _now()
    return Inventory(
        id="i1",
        name="Inv",
        status=InventoryStatus.PROCESSING,
        created_at=now,
        updated_at=now,
    )


def _harness(*, with_auth: bool = True):
    auth = MemoryAuthoritativeLocalCodeScanRepository()
    if with_auth:
        for aid, rid, code in (("p1", "r1", "SKU1"), ("p2", "r2", "SKU2")):
            auth.create_authoritative_version(
                new_result=_auth_row(rid=rid, asset_id=aid, code=code),
                expected_current_id=None,
                expected_row_version=None,
            )
    repo = MemoryServerReprocessRepository()
    create = CreateServerReprocessRun(
        enabled=True,
        inventory_repo=_MemInvRepo({"i1": _inventory()}),
        aisle_repo=_MemAisleRepo({"a1": _aisle()}),
        asset_repo=_MemAssetRepo([_asset("p1"), _asset("p2"), _asset("p3")]),
        reprocess_repo=repo,
        authoritative_repo=auth if with_auth else None,
        clock=_FixedClock(_now()),
    )
    execute = ExecuteServerReprocessRun(reprocess_repo=repo, clock=_FixedClock(_now()))
    adopt = AdoptServerReprocessProposals(
        enabled=True,
        reprocess_repo=repo,
        authoritative_repo=auth if with_auth else None,
        clock=_FixedClock(_now()),
    )
    listing = ListServerReprocessProposals(reprocess_repo=repo)
    cancel = CancelServerReprocessRun(reprocess_repo=repo, clock=_FixedClock(_now()))
    return create, execute, adopt, listing, cancel, repo, auth


def test_classify_same_and_code_changed():
    snap = ServerReprocessRunAsset(
        id="x",
        run_id="run",
        asset_id="p1",
        asset_hash="h",
        previous_result_id="r1",
        previous_position_id="pos1",
        previous_internal_code="SKU1",
        previous_quantity=1.0,
        previous_resolved=True,
        created_at=_now(),
    )
    same = classify_server_reprocess_difference(
        snapshot_asset=snap,
        remote=RemoteProposalInput(
            asset_id="p1", internal_code="SKU1", quantity=1.0, resolved=True
        ),
    )
    assert same == ServerReprocessDifferenceType.SAME_RESULT
    changed = classify_server_reprocess_difference(
        snapshot_asset=snap,
        remote=RemoteProposalInput(
            asset_id="p1", internal_code="SKU9", quantity=1.0, resolved=True
        ),
    )
    assert changed == ServerReprocessDifferenceType.CODE_CHANGED


def test_classify_global_batch_not_comparable():
    snap = ServerReprocessRunAsset(
        id="x",
        run_id="run",
        asset_id="p1",
        asset_hash=None,
        previous_result_id="r1",
        previous_position_id=None,
        previous_internal_code="SKU1",
        previous_quantity=1.0,
        previous_resolved=True,
        created_at=_now(),
    )
    diff = classify_server_reprocess_difference(
        snapshot_asset=snap,
        remote=RemoteProposalInput(
            asset_id="p1",
            internal_code="SKU9",
            resolved=True,
            global_batch_unmapped=True,
        ),
    )
    assert diff == ServerReprocessDifferenceType.NOT_COMPARABLE_GLOBAL_BATCH


def test_create_full_aisle_snapshot_and_idempotent_request():
    create, *_rest = _harness()
    cmd = CreateServerReprocessCommand(
        inventory_id="i1",
        aisle_id="a1",
        request_id="req-1",
        scope_type="FULL_AISLE",
        asset_ids=(),
        processing_mode="CODE_SCAN",
        reason="USER_REQUESTED_REPROCESS",
        requested_by="u1",
    )
    first = create.execute(cmd)
    assert first.replayed is False
    assert first.run.has_prior_authority is True
    assert first.run.run_type == "SERVER_REPROCESS"
    assert len(first.run.snapshot_json["asset_ids"]) == 3

    second = create.execute(cmd)
    assert second.replayed is True
    assert second.run.id == first.run.id


def test_create_request_id_conflict_on_different_payload():
    create, *_ = _harness()
    create.execute(
        CreateServerReprocessCommand(
            inventory_id="i1",
            aisle_id="a1",
            request_id="req-2",
            scope_type="FULL_AISLE",
            asset_ids=(),
            processing_mode="CODE_SCAN",
            reason="USER_REQUESTED_REPROCESS",
            requested_by="u1",
        )
    )
    with pytest.raises(ServerReprocessRequestConflictError):
        create.execute(
            CreateServerReprocessCommand(
                inventory_id="i1",
                aisle_id="a1",
                request_id="req-2",
                scope_type="SELECTED_ASSETS",
                asset_ids=("p1",),
                processing_mode="CODE_SCAN",
                reason="USER_REQUESTED_REPROCESS",
                requested_by="u1",
            )
        )


def test_selected_assets_invalid_raises():
    create, *_ = _harness()
    with pytest.raises(ServerReprocessInvalidScopeError):
        create.execute(
            CreateServerReprocessCommand(
                inventory_id="i1",
                aisle_id="a1",
                request_id="req-bad",
                scope_type="SELECTED_ASSETS",
                asset_ids=("missing",),
                processing_mode="CODE_SCAN",
                reason="USER_REQUESTED_REPROCESS",
                requested_by="u1",
            )
        )


def test_proposals_do_not_mutate_current_authority():
    create, execute, _adopt, listing, _cancel, _repo, auth = _harness()
    before = auth.get_current_for_asset("p1")
    assert before is not None
    before_code = before.internal_code

    created = create.execute(
        CreateServerReprocessCommand(
            inventory_id="i1",
            aisle_id="a1",
            request_id="req-prop",
            scope_type="SELECTED_ASSETS",
            asset_ids=("p1",),
            processing_mode="CODE_SCAN",
            reason="USER_REQUESTED_REPROCESS",
            requested_by="u1",
        )
    )
    execute.complete_with_remote_results(
        run_id=created.run.id,
        remote_results=[
            RemoteProposalInput(
                asset_id="p1",
                remote_result_id="remote-1",
                internal_code="NEW_SKU",
                    quantity=1.0,
                resolved=True,
                source="CODE_SCAN",
            )
        ],
    )
    after = auth.get_current_for_asset("p1")
    assert after is not None
    assert after.internal_code == before_code
    assert after.id == before.id

    detail = listing.execute(run_id=created.run.id)
    assert detail.summary.total == 1
    assert detail.items[0].difference_type == "CODE_CHANGED"
    assert detail.items[0].status == "PROPOSED"


def test_partial_adoption_creates_new_version_keeps_others():
    create, execute, adopt, _listing, _cancel, _repo, auth = _harness()
    created = create.execute(
        CreateServerReprocessCommand(
            inventory_id="i1",
            aisle_id="a1",
            request_id="req-adopt",
            scope_type="SELECTED_ASSETS",
            asset_ids=("p1", "p2"),
            processing_mode="CODE_SCAN",
            reason="USER_REQUESTED_REPROCESS",
            requested_by="u1",
        )
    )
    _run, proposals = execute.complete_with_remote_results(
        run_id=created.run.id,
        remote_results=[
            RemoteProposalInput(
                asset_id="p1", internal_code="NEW1", quantity=1, resolved=True
            ),
            RemoteProposalInput(
                asset_id="p2", internal_code="NEW2", quantity=1, resolved=True
            ),
        ],
    )
    p1 = next(p for p in proposals if p.asset_id == "p1")
    p2 = next(p for p in proposals if p.asset_id == "p2")

    result = adopt.execute(
        AdoptServerReprocessCommand(
            inventory_id="i1",
            aisle_id="a1",
            run_id=created.run.id,
            adoption_id="adop-1",
            adopted_by="u1",
            items=(
                AdoptItemCommand(proposal_id=p1.id, action="ADOPT"),
                AdoptItemCommand(proposal_id=p2.id, action="KEEP_CURRENT"),
            ),
        )
    )
    assert result.adoption.adopted_count == 1
    assert result.adoption.kept_count == 1
    assert auth.get_current_for_asset("p1").internal_code == "NEW1"
    assert auth.get_current_for_asset("p1").supersedes_result_id == "r1"
    assert auth.get_current_for_asset("p2").internal_code == "SKU2"


def test_stale_proposal_blocks_adoption():
    create, execute, adopt, _listing, _cancel, _repo, auth = _harness()
    created = create.execute(
        CreateServerReprocessCommand(
            inventory_id="i1",
            aisle_id="a1",
            request_id="req-stale",
            scope_type="SELECTED_ASSETS",
            asset_ids=("p1",),
            processing_mode="CODE_SCAN",
            reason="USER_REQUESTED_REPROCESS",
            requested_by="u1",
        )
    )
    _run, proposals = execute.complete_with_remote_results(
        run_id=created.run.id,
        remote_results=[
            RemoteProposalInput(
                asset_id="p1", internal_code="NEW1", quantity=1, resolved=True
            )
        ],
    )
    # Change current authority after proposal
    current = auth.get_current_for_asset("p1")
    assert current is not None
    auth.create_authoritative_version(
        new_result=_auth_row(rid="r1b", asset_id="p1", code="OTHER"),
        expected_current_id=current.id,
        expected_row_version=current.row_version,
    )
    with pytest.raises(ServerReprocessStaleProposalError):
        adopt.execute(
            AdoptServerReprocessCommand(
                inventory_id="i1",
                aisle_id="a1",
                run_id=created.run.id,
                adoption_id="adop-stale",
                adopted_by="u1",
                items=(AdoptItemCommand(proposal_id=proposals[0].id, action="ADOPT"),),
            )
        )


def test_cancel_run_preserves_authority():
    create, _execute, _adopt, _listing, cancel, _repo, auth = _harness()
    created = create.execute(
        CreateServerReprocessCommand(
            inventory_id="i1",
            aisle_id="a1",
            request_id="req-cancel",
            scope_type="FULL_AISLE",
            asset_ids=(),
            processing_mode="CODE_SCAN",
            reason="USER_REQUESTED_REPROCESS",
            requested_by="u1",
        )
    )
    canceled = cancel.execute(run_id=created.run.id)
    assert canceled.status == "CANCELED"
    assert auth.get_current_for_asset("p1").internal_code == "SKU1"


def test_upload_only_without_prior_is_initial_server_processing():
    create, *_ = _harness(with_auth=False)
    result = create.execute(
        CreateServerReprocessCommand(
            inventory_id="i1",
            aisle_id="a1",
            request_id="req-initial",
            scope_type="FULL_AISLE",
            asset_ids=(),
            processing_mode="CODE_SCAN",
            reason="USER_REQUESTED_REPROCESS",
            requested_by="u1",
        )
    )
    assert result.initial_server_processing is True
    assert result.run.run_type == "INITIAL_SERVER_PROCESSING"
    assert result.run.has_prior_authority is False


def test_adoption_idempotent_replay():
    create, execute, adopt, *_rest = _harness()
    created = create.execute(
        CreateServerReprocessCommand(
            inventory_id="i1",
            aisle_id="a1",
            request_id="req-replay",
            scope_type="SELECTED_ASSETS",
            asset_ids=("p1",),
            processing_mode="CODE_SCAN",
            reason="USER_REQUESTED_REPROCESS",
            requested_by="u1",
        )
    )
    _run, proposals = execute.complete_with_remote_results(
        run_id=created.run.id,
        remote_results=[
            RemoteProposalInput(
                asset_id="p1", internal_code="NEW1", quantity=1, resolved=True
            )
        ],
    )
    cmd = AdoptServerReprocessCommand(
        inventory_id="i1",
        aisle_id="a1",
        run_id=created.run.id,
        adoption_id="adop-replay",
        adopted_by="u1",
        items=(AdoptItemCommand(proposal_id=proposals[0].id, action="ADOPT"),),
    )
    first = adopt.execute(cmd)
    second = adopt.execute(cmd)
    assert first.replayed is False
    assert second.replayed is True
    assert second.adoption.id == first.adoption.id
    assert first.adoption.content_hash


def test_adoption_id_content_hash_conflict():
    create, execute, adopt, *_rest = _harness()
    created = create.execute(
        CreateServerReprocessCommand(
            inventory_id="i1",
            aisle_id="a1",
            request_id="req-hash",
            scope_type="SELECTED_ASSETS",
            asset_ids=("p1", "p2"),
            processing_mode="CODE_SCAN",
            reason="USER_REQUESTED_REPROCESS",
            requested_by="u1",
        )
    )
    _run, proposals = execute.complete_with_remote_results(
        run_id=created.run.id,
        remote_results=[
            RemoteProposalInput(
                asset_id="p1", internal_code="NEW1", quantity=1, resolved=True
            ),
            RemoteProposalInput(
                asset_id="p2", internal_code="NEW2", quantity=1, resolved=True
            ),
        ],
    )
    p1 = next(p for p in proposals if p.asset_id == "p1")
    p2 = next(p for p in proposals if p.asset_id == "p2")
    adopt.execute(
        AdoptServerReprocessCommand(
            inventory_id="i1",
            aisle_id="a1",
            run_id=created.run.id,
            adoption_id="adop-hash",
            adopted_by="u1",
            items=(AdoptItemCommand(proposal_id=p1.id, action="ADOPT"),),
        )
    )
    from src.application.use_cases.aisles.adopt_server_reprocess_proposals import (
        ServerReprocessAdoptionConflictError,
    )

    with pytest.raises(ServerReprocessAdoptionConflictError):
        adopt.execute(
            AdoptServerReprocessCommand(
                inventory_id="i1",
                aisle_id="a1",
                run_id=created.run.id,
                adoption_id="adop-hash",
                adopted_by="u1",
                items=(AdoptItemCommand(proposal_id=p2.id, action="KEEP_CURRENT"),),
            )
        )


def test_proposal_sink_does_not_require_persister():
    from src.application.services.server_reprocess_proposal_sink import (
        ServerReprocessProposalResultSink,
    )
    from src.domain.image_processing.contracts import (
        ImageProcessingResult,
        ImageResultStatus,
    )

    sink = ServerReprocessProposalResultSink()
    sink.accept(
        ImageProcessingResult(
            job_id="j1",
            asset_id="p1",
            status=ImageResultStatus.RESOLVED_INTERNAL,
            processing_mode="CODE_SCAN",
            internal_code="SKU9",
            quantity=2,
            resolved_by="CODE_SCAN",
        )
    )
    assert sink.as_remote_inputs()[0].internal_code == "SKU9"
    assert sink.as_remote_inputs()[0].resolved is True
