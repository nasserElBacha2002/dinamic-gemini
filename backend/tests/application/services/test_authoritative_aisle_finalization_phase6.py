"""Unit tests for EvaluateAuthoritativeAisleReadiness and FinalizeAuthoritativeAisle."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pytest

from src.application.services.evaluate_authoritative_aisle_readiness import (
    EvaluateAuthoritativeAisleReadiness,
)
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.use_cases.aisles.finalize_authoritative_aisle import (
    AuthoritativeFinalizationConflictError,
    AuthoritativeFinalizationNotReadyError,
    FinalizeAuthoritativeAisle,
    FinalizeAuthoritativeAisleCommand,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.authoritative_aisle_finalization.entities import (
    AuthoritativeAisleReadinessStatus,
)
from src.domain.authoritative_local_code_scan.entities import AuthoritativeLocalCodeScanResult
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.infrastructure.repositories.memory_authoritative_aisle_finalization_repository import (
    MemoryAuthoritativeAisleFinalizationRepository,
)
from src.infrastructure.repositories.memory_authoritative_local_code_scan_repository import (
    MemoryAuthoritativeLocalCodeScanRepository,
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

    def list_by_inventory(self, inventory_id: str):
        return [a for a in self.aisles.values() if a.inventory_id == inventory_id]


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


def _asset(aid: str, aisle_id: str = "a1") -> SourceAsset:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return SourceAsset(
        id=aid,
        aisle_id=aisle_id,
        type=SourceAssetType.PHOTO,
        original_filename=f"{aid}.jpg",
        storage_path=f"/tmp/{aid}.jpg",
        mime_type="image/jpeg",
        uploaded_at=now,
    )


def _auth_row(
    *,
    rid: str,
    asset_id: str,
    applied: bool,
    code: str = "SKU1",
) -> AuthoritativeLocalCodeScanResult:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
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
        applied_job_id="j1" if applied else None,
        applied_at=now if applied else None,
        row_version=1,
        schema_version="1",
        created_at=now,
        updated_at=now,
    )


def _aisle() -> Aisle:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return Aisle(
        id="a1",
        inventory_id="i1",
        code="A1",
        status=AisleStatus.ASSETS_UPLOADED,
        created_at=now,
        updated_at=now,
    )


def _inventory() -> Inventory:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return Inventory(
        id="i1",
        name="Inv",
        status=InventoryStatus.PROCESSING,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def harness() -> dict[str, Any]:
    now = datetime(2026, 7, 1, tzinfo=timezone.utc)
    auth = MemoryAuthoritativeLocalCodeScanRepository()
    fin = MemoryAuthoritativeAisleFinalizationRepository()
    assets = _MemAssetRepo([_asset("p1"), _asset("p2")])
    aisle_repo = _MemAisleRepo({"a1": _aisle()})
    inv_repo = _MemInvRepo({"i1": _inventory()})
    clock = _FixedClock(now)
    readiness = EvaluateAuthoritativeAisleReadiness(
        asset_repo=assets,
        authoritative_repo=auth,
        finalization_repo=fin,
        position_repo=None,
        enabled=True,
    )
    finalize = FinalizeAuthoritativeAisle(
        aisle_repo=aisle_repo,
        inventory_repo=inv_repo,
        asset_repo=assets,
        authoritative_repo=auth,
        finalization_repo=fin,
        readiness=readiness,
        status_reconciler=InventoryStatusReconciler(inv_repo, aisle_repo, clock),
        clock=clock,
        position_repo=None,
        enabled=True,
    )
    return {
        "auth": auth,
        "fin": fin,
        "readiness": readiness,
        "finalize": finalize,
        "aisle_repo": aisle_repo,
        "now": now,
    }


def test_readiness_not_ready_when_pending_confirmation(harness):
    result = harness["readiness"].execute(inventory_id="i1", aisle_id="a1")
    assert result.status == AuthoritativeAisleReadinessStatus.NOT_READY
    assert "PENDING_CONFIRMATION" in result.reasons
    assert result.pending_images == 2


def test_readiness_pending_final_apply(harness):
    auth = harness["auth"]
    auth.create_authoritative_version(
        new_result=_auth_row(rid="r1", asset_id="p1", applied=False),
        expected_current_id=None,
        expected_row_version=None,
    )
    auth.create_authoritative_version(
        new_result=_auth_row(rid="r2", asset_id="p2", applied=False),
        expected_current_id=None,
        expected_row_version=None,
    )
    result = harness["readiness"].execute(inventory_id="i1", aisle_id="a1")
    assert result.status == AuthoritativeAisleReadinessStatus.NOT_READY
    assert "PENDING_FINAL_APPLY" in result.reasons


def test_readiness_ready_when_all_applied(harness):
    auth = harness["auth"]
    auth.create_authoritative_version(
        new_result=_auth_row(rid="r1", asset_id="p1", applied=True),
        expected_current_id=None,
        expected_row_version=None,
    )
    auth.create_authoritative_version(
        new_result=_auth_row(rid="r2", asset_id="p2", applied=True, code="SKU2"),
        expected_current_id=None,
        expected_row_version=None,
    )
    result = harness["readiness"].execute(inventory_id="i1", aisle_id="a1")
    assert result.status == AuthoritativeAisleReadinessStatus.READY
    assert result.can_apply is True
    assert result.can_finalize is True
    assert result.applied_images == 2
    assert result.unique_codes == 2


def test_readiness_can_apply_before_finalize(harness):
    auth = harness["auth"]
    auth.create_authoritative_version(
        new_result=_auth_row(rid="r1", asset_id="p1", applied=False),
        expected_current_id=None,
        expected_row_version=None,
    )
    auth.create_authoritative_version(
        new_result=_auth_row(rid="r2", asset_id="p2", applied=False),
        expected_current_id=None,
        expected_row_version=None,
    )
    result = harness["readiness"].execute(inventory_id="i1", aisle_id="a1")
    assert result.can_apply is True
    assert result.can_finalize is False
    assert result.status == AuthoritativeAisleReadinessStatus.NOT_READY
    assert "PENDING_FINAL_APPLY" in result.reasons


def test_finalize_success_and_idempotent_replay(harness):
    auth = harness["auth"]
    auth.create_authoritative_version(
        new_result=_auth_row(rid="r1", asset_id="p1", applied=True),
        expected_current_id=None,
        expected_row_version=None,
    )
    auth.create_authoritative_version(
        new_result=_auth_row(rid="r2", asset_id="p2", applied=True),
        expected_current_id=None,
        expected_row_version=None,
    )
    cmd = FinalizeAuthoritativeAisleCommand(
        inventory_id="i1",
        aisle_id="a1",
        finalization_id="fin-1",
        expected_asset_count=2,
        client_session_id="sess-1",
        confirmed_by_user_id="user-1",
    )
    first = harness["finalize"].execute(cmd)
    assert first.status == "COMPLETED_BY_LOCAL_AUTHORITY"
    assert first.idempotent_replay is False
    assert harness["aisle_repo"].get_by_id("a1").status == AisleStatus.COMPLETED

    second = harness["finalize"].execute(cmd)
    assert second.idempotent_replay is True
    assert second.finalization_id == "fin-1"


def test_finalize_rejects_when_not_ready(harness):
    cmd = FinalizeAuthoritativeAisleCommand(
        inventory_id="i1",
        aisle_id="a1",
        finalization_id="fin-x",
        expected_asset_count=2,
        client_session_id=None,
        confirmed_by_user_id="user-1",
    )
    with pytest.raises(AuthoritativeFinalizationNotReadyError):
        harness["finalize"].execute(cmd)


def test_finalize_rejects_second_distinct_finalization(harness):
    auth = harness["auth"]
    auth.create_authoritative_version(
        new_result=_auth_row(rid="r1", asset_id="p1", applied=True),
        expected_current_id=None,
        expected_row_version=None,
    )
    auth.create_authoritative_version(
        new_result=_auth_row(rid="r2", asset_id="p2", applied=True),
        expected_current_id=None,
        expected_row_version=None,
    )
    harness["finalize"].execute(
        FinalizeAuthoritativeAisleCommand(
            inventory_id="i1",
            aisle_id="a1",
            finalization_id="fin-1",
            expected_asset_count=2,
            client_session_id=None,
            confirmed_by_user_id="user-1",
        )
    )
    with pytest.raises(AuthoritativeFinalizationConflictError):
        harness["finalize"].execute(
            FinalizeAuthoritativeAisleCommand(
                inventory_id="i1",
                aisle_id="a1",
                finalization_id="fin-2",
                expected_asset_count=2,
                client_session_id=None,
                confirmed_by_user_id="user-1",
            )
        )
