"""Phase 8 aisle revision unit tests (memory repositories)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from src.application.ports.aisle_revision_unit_of_work import AisleRevisionRepositories
from src.application.use_cases.aisles.apply_aisle_revision import (
    AisleRevisionStaleError,
    ApplyAisleRevision,
    ApplyAisleRevisionCommand,
    CreateRollbackCommand,
    CreateRollbackRevision,
)
from src.application.use_cases.aisles.manage_aisle_revisions import (
    CreateAisleRevision,
    CreateAisleRevisionCommand,
    UpdateAisleRevisionItem,
    UpdateAisleRevisionItemCommand,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.aisle_revision.entities import AisleRevisionStatus
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.authoritative_aisle_finalization.entities import (
    AuthoritativeAisleFinalization,
    AuthoritativeAisleFinalizationItem,
    AuthoritativeFinalizationItemStatus,
    AuthoritativeFinalizationStatus,
)
from src.domain.authoritative_local_code_scan.entities import (
    AuthoritativeLocalCodeScanResult,
    AuthoritativeQuantityStatus,
    AuthoritativeResultSource,
)
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.positions.entities import Position, PositionStatus
from src.infrastructure.persistence.memory_aisle_revision_unit_of_work import (
    build_memory_aisle_revision_uow_factory,
)
from src.infrastructure.repositories.memory_aisle_revision_repository import (
    MemoryAisleRevisionRepository,
)
from src.infrastructure.repositories.memory_authoritative_aisle_finalization_repository import (
    MemoryAuthoritativeAisleFinalizationRepository,
)
from src.infrastructure.repositories.memory_authoritative_local_code_scan_repository import (
    MemoryAuthoritativeLocalCodeScanRepository,
)


class _MemInventory:
    def __init__(self) -> None:
        self._rows: dict[str, Inventory] = {}

    def get_by_id(self, inventory_id: str):
        return self._rows.get(inventory_id)

    def save(self, inventory: Inventory) -> None:
        self._rows[inventory.id] = inventory


class _MemAisle:
    def __init__(self) -> None:
        self._rows: dict[str, Aisle] = {}

    def get_by_id(self, aisle_id: str):
        return self._rows.get(aisle_id)

    def save(self, aisle: Aisle) -> None:
        self._rows[aisle.id] = aisle


class _MemAsset:
    def __init__(self) -> None:
        self._rows: list[SourceAsset] = []

    def list_by_aisle(self, aisle_id: str):
        return [a for a in self._rows if a.aisle_id == aisle_id]

    def save(self, asset: SourceAsset) -> None:
        self._rows.append(asset)


class _MemPosition:
    def __init__(self) -> None:
        self._rows: dict[str, Position] = {}

    def list_by_aisle(self, aisle_id: str):
        return [p for p in self._rows.values() if p.aisle_id == aisle_id]

    def get_by_id(self, position_id: str):
        return self._rows.get(position_id)

    def save(self, position: Position) -> None:
        self._rows[position.id] = position


def _now() -> datetime:
    return datetime(2026, 7, 24, 18, 0, 0, tzinfo=timezone.utc)


def _seed():
    now = _now()
    inv_id = str(uuid4())
    aisle_id = str(uuid4())
    asset_id = str(uuid4())
    result_id = str(uuid4())
    position_id = str(uuid4())
    fin_id = str(uuid4())

    inv_repo = _MemInventory()
    aisle_repo = _MemAisle()
    asset_repo = _MemAsset()
    pos_repo = _MemPosition()
    auth_repo = MemoryAuthoritativeLocalCodeScanRepository()
    fin_repo = MemoryAuthoritativeAisleFinalizationRepository()
    rev_repo = MemoryAisleRevisionRepository()

    inv_repo.save(
        Inventory(
            id=inv_id,
            name="test",
            status=InventoryStatus.IN_REVIEW,
            created_at=now,
            updated_at=now,
        )
    )
    aisle_repo.save(
        Aisle(
            id=aisle_id,
            inventory_id=inv_id,
            code="A1",
            status=AisleStatus.COMPLETED,
            created_at=now,
            updated_at=now,
            is_active=True,
        )
    )
    asset_repo.save(
        SourceAsset(
            id=asset_id,
            aisle_id=aisle_id,
            type=SourceAssetType.PHOTO,
            original_filename="a.jpg",
            storage_path="x",
            mime_type="image/jpeg",
            uploaded_at=now,
        )
    )
    result = AuthoritativeLocalCodeScanResult(
        id=result_id,
        asset_id=asset_id,
        inventory_id=inv_id,
        aisle_id=aisle_id,
        client_file_id=asset_id,
        result_version=1,
        supersedes_result_id=None,
        is_current=True,
        internal_code="ABC",
        quantity=10,
        quantity_status=AuthoritativeQuantityStatus.PRESENT.value,
        source=AuthoritativeResultSource.LOCAL_CODE_SCAN.value,
        detected_internal_code="ABC",
        detected_quantity=10,
        detected_symbology=None,
        parser_version="1",
        detector_version="1",
        prepared_asset_sha256="hash",
        content_hash="ch",
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
    )
    auth_repo.create_authoritative_version(
        new_result=result, expected_current_id=None, expected_row_version=None
    )
    pos_repo.save(
        Position(
            id=position_id,
            aisle_id=aisle_id,
            status=PositionStatus.DETECTED,
            confidence=1.0,
            needs_review=False,
            primary_evidence_id=None,
            created_at=now,
            updated_at=now,
            detected_summary_json={
                "source_asset_id": asset_id,
                "internal_code": "ABC",
                "quantity": 10,
            },
        )
    )
    fin = AuthoritativeAisleFinalization(
        id=fin_id,
        inventory_id=inv_id,
        aisle_id=aisle_id,
        capture_session_id=None,
        finalization_version=1,
        status=AuthoritativeFinalizationStatus.COMPLETED_BY_LOCAL_AUTHORITY.value,
        total_assets=1,
        applied_assets=1,
        excluded_assets=0,
        position_count=1,
        expected_asset_count=1,
        content_hash="finhash",
        confirmed_by="u1",
        confirmed_at=now,
        completed_at=now,
        is_current=True,
        row_version=1,
        created_at=now,
        updated_at=now,
    )
    fin_repo.save_finalization(
        finalization=fin,
        items=[
            AuthoritativeAisleFinalizationItem(
                id=str(uuid4()),
                finalization_id=fin_id,
                asset_id=asset_id,
                authoritative_result_id=result_id,
                position_id=position_id,
                item_status=AuthoritativeFinalizationItemStatus.CONFIRMED_AND_APPLIED.value,
                created_at=now,
            )
        ],
        supersede_current=False,
    )

    create = CreateAisleRevision(
        enabled=True,
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        finalization_repo=fin_repo,
        authoritative_repo=auth_repo,
        position_repo=pos_repo,
        revision_repo=rev_repo,
    )
    update = UpdateAisleRevisionItem(enabled=True, revision_repo=rev_repo)
    uow_factory = build_memory_aisle_revision_uow_factory(
        AisleRevisionRepositories(
            revision_repo=rev_repo,
            authoritative_repo=auth_repo,
            position_repo=pos_repo,
            finalization_repo=fin_repo,
            aisle_repo=aisle_repo,
            inventory_repo=inv_repo,
        )
    )
    apply = ApplyAisleRevision(
        enabled=True,
        uow_factory=uow_factory,
        revision_repo=rev_repo,
        finalization_repo=fin_repo,
        authoritative_repo=auth_repo,
        position_repo=pos_repo,
    )
    return {
        "inv_id": inv_id,
        "aisle_id": aisle_id,
        "asset_id": asset_id,
        "fin_id": fin_id,
        "position_id": position_id,
        "create": create,
        "update": update,
        "apply": apply,
        "fin_repo": fin_repo,
        "auth_repo": auth_repo,
        "rev_repo": rev_repo,
        "pos_repo": pos_repo,
        "inv_repo": inv_repo,
        "aisle_repo": aisle_repo,
        "asset_repo": asset_repo,
        "uow_factory": uow_factory,
    }


def test_create_edit_apply_creates_new_finalization_and_result_version():
    ctx = _seed()
    rev_id = str(uuid4())
    revision, replayed = ctx["create"].execute(
        CreateAisleRevisionCommand(
            inventory_id=ctx["inv_id"],
            aisle_id=ctx["aisle_id"],
            revision_id=rev_id,
            revision_type="MANUAL_CORRECTION",
            reason="Cantidad incorrecta",
            requested_by="op1",
        )
    )
    assert replayed is False
    assert revision.status == AisleRevisionStatus.OPEN.value

    ctx["update"].execute(
        UpdateAisleRevisionItemCommand(
            inventory_id=ctx["inv_id"],
            aisle_id=ctx["aisle_id"],
            revision_id=rev_id,
            asset_id=ctx["asset_id"],
            actor_id="op1",
            internal_code="ABC",
            quantity=12,
            reason="fix qty",
        )
    )

    applied = ctx["apply"].execute(
        ApplyAisleRevisionCommand(
            inventory_id=ctx["inv_id"],
            aisle_id=ctx["aisle_id"],
            revision_id=rev_id,
            apply_id=str(uuid4()),
            expected_base_finalization_id=ctx["fin_id"],
            applied_by="op1",
        )
    )
    assert applied.status == AisleRevisionStatus.COMPLETED.value
    assert applied.new_finalization_id is not None

    current_fin = ctx["fin_repo"].get_current_for_aisle(ctx["aisle_id"])
    assert current_fin is not None
    assert current_fin.id == applied.new_finalization_id
    assert current_fin.finalization_version == 2
    assert current_fin.supersedes_finalization_id == ctx["fin_id"]

    current_res = ctx["auth_repo"].get_current_for_asset(ctx["asset_id"])
    assert current_res is not None
    assert current_res.quantity == 12
    assert current_res.result_version == 2


def test_apply_stale_when_base_finalization_changed():
    ctx = _seed()
    rev_id = str(uuid4())
    ctx["create"].execute(
        CreateAisleRevisionCommand(
            inventory_id=ctx["inv_id"],
            aisle_id=ctx["aisle_id"],
            revision_id=rev_id,
            revision_type="MANUAL_CORRECTION",
            reason="edit",
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
            quantity=11,
            reason="x",
        )
    )
    # Simulate another device applying a new finalization
    now = _now()
    other = AuthoritativeAisleFinalization(
        id=str(uuid4()),
        inventory_id=ctx["inv_id"],
        aisle_id=ctx["aisle_id"],
        capture_session_id=None,
        finalization_version=2,
        status=AuthoritativeFinalizationStatus.COMPLETED_BY_LOCAL_AUTHORITY.value,
        total_assets=1,
        applied_assets=1,
        excluded_assets=0,
        position_count=1,
        expected_asset_count=1,
        content_hash="other",
        confirmed_by="other",
        confirmed_at=now,
        completed_at=now,
        is_current=True,
        row_version=1,
        created_at=now,
        updated_at=now,
        supersedes_finalization_id=ctx["fin_id"],
    )
    ctx["fin_repo"].save_finalization(finalization=other, items=[], supersede_current=True)

    with pytest.raises(AisleRevisionStaleError):
        ctx["apply"].execute(
            ApplyAisleRevisionCommand(
                inventory_id=ctx["inv_id"],
                aisle_id=ctx["aisle_id"],
                revision_id=rev_id,
                apply_id=str(uuid4()),
                expected_base_finalization_id=ctx["fin_id"],
                applied_by="op1",
            )
        )


def test_idempotent_create_replay():
    ctx = _seed()
    rev_id = str(uuid4())
    cmd = CreateAisleRevisionCommand(
        inventory_id=ctx["inv_id"],
        aisle_id=ctx["aisle_id"],
        revision_id=rev_id,
        revision_type="MANUAL_CORRECTION",
        reason="same",
        requested_by="op1",
    )
    first, r1 = ctx["create"].execute(cmd)
    second, r2 = ctx["create"].execute(cmd)
    assert r1 is False
    assert r2 is True
    assert first.id == second.id


def test_rollback_creates_new_version_not_reactivating_old():
    ctx = _seed()
    # First correction -> v2
    rev_id = str(uuid4())
    ctx["create"].execute(
        CreateAisleRevisionCommand(
            inventory_id=ctx["inv_id"],
            aisle_id=ctx["aisle_id"],
            revision_id=rev_id,
            revision_type="MANUAL_CORRECTION",
            reason="bad fix",
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
            quantity=99,
            reason="oops",
        )
    )
    ctx["apply"].execute(
        ApplyAisleRevisionCommand(
            inventory_id=ctx["inv_id"],
            aisle_id=ctx["aisle_id"],
            revision_id=rev_id,
            apply_id=str(uuid4()),
            expected_base_finalization_id=ctx["fin_id"],
            applied_by="op1",
        )
    )
    v2 = ctx["fin_repo"].get_current_for_aisle(ctx["aisle_id"])
    assert v2 is not None
    assert v2.finalization_version == 2

    rollback = CreateRollbackRevision(
        enabled=True,
        create_revision=ctx["create"],
        apply_revision=ctx["apply"],
        finalization_repo=ctx["fin_repo"],
        revision_repo=ctx["rev_repo"],
        authoritative_repo=ctx["auth_repo"],
        update_item=ctx["update"],
    )
    rolled = rollback.execute(
        CreateRollbackCommand(
            inventory_id=ctx["inv_id"],
            aisle_id=ctx["aisle_id"],
            rollback_id=str(uuid4()),
            target_finalization_id=ctx["fin_id"],
            reason="Revertir corrección incorrecta",
            requested_by="op1",
            apply_immediately=True,
        )
    )
    assert rolled.status == AisleRevisionStatus.COMPLETED.value
    v3 = ctx["fin_repo"].get_current_for_aisle(ctx["aisle_id"])
    assert v3 is not None
    assert v3.finalization_version == 3
    assert v3.id != ctx["fin_id"]
    # v1 remains historical (not reactivated)
    v1 = ctx["fin_repo"].get_by_id(ctx["fin_id"])
    assert v1 is not None
    assert v1.is_current is False

    current_res = ctx["auth_repo"].get_current_for_asset(ctx["asset_id"])
    assert current_res is not None
    assert current_res.quantity == 10
