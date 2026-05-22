"""G4 — assign capture session groups to aisles."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.errors import (
    AisleNotFoundForAssignmentError,
    CaptureSessionGroupAlreadyAssignedError,
    CaptureSessionGroupAssignmentNotAllowedError,
    CaptureSessionGroupNotFoundError,
    CaptureSessionNotFoundError,
)
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.use_cases.capture_sessions.assign_capture_session_group_to_existing_aisle import (
    AssignCaptureSessionGroupToExistingAisleUseCase,
)
from src.application.use_cases.aisles.create_aisle import CreateAisleUseCase
from src.application.use_cases.capture_sessions.create_aisle_and_assign_capture_session_group import (
    CreateAisleAndAssignCaptureSessionGroupUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.capture.entities import (
    CaptureSession,
    CaptureSessionGroup,
    CaptureSessionItem,
    CaptureSessionItemAssignmentStatus,
    CaptureSessionItemImportStatus,
    CaptureSessionStatus,
)
from src.domain.client_supplier.entities import ClientSupplier, ClientSupplierStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_capture_session_group_repository import (
    MemoryCaptureSessionGroupRepository,
)
from src.infrastructure.repositories.memory_capture_session_item_repository import (
    MemoryCaptureSessionItemRepository,
)
from src.infrastructure.repositories.memory_capture_session_repository import (
    MemoryCaptureSessionRepository,
)
from src.infrastructure.repositories.memory_client_supplier_repository import (
    MemoryClientSupplierRepository,
)
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository

UTC = timezone.utc


class _Clock:
    def __init__(self, t: datetime) -> None:
        self._t = t

    def now(self) -> datetime:
        return self._t


def _closed_session(inv: str, sid: str) -> CaptureSession:
    t = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
    return CaptureSession(
        id=sid,
        inventory_id=inv,
        aisle_id=None,
        status=CaptureSessionStatus.READY_FOR_REVIEW,
        created_at=t,
        updated_at=t,
        opened_at=t,
        closed_at=t,
        clock_offset_seconds=0,
    )


def _imported_item(item_id: str, session_id: str, group_id: str, t: datetime) -> CaptureSessionItem:
    return CaptureSessionItem(
        id=item_id,
        session_id=session_id,
        staging_storage_key=f"capture/staging/{item_id}",
        import_status=CaptureSessionItemImportStatus.IMPORTED,
        assignment_status=CaptureSessionItemAssignmentStatus.PENDING,
        updated_at=t,
        effective_capture_time=t,
        group_id=group_id,
        original_filename=f"{item_id}.jpg",
    )


@pytest.fixture
def assign_ctx():
    clock = _Clock(datetime(2025, 1, 3, 12, 0, 0, tzinfo=UTC))
    sr = MemoryCaptureSessionRepository()
    ir = MemoryCaptureSessionItemRepository()
    gr = MemoryCaptureSessionGroupRepository(ir)
    ar = MemoryAisleRepository()
    uc = AssignCaptureSessionGroupToExistingAisleUseCase(
        session_repo=sr,
        group_repo=gr,
        aisle_repo=ar,
        clock=clock,
    )
    return sr, ir, gr, ar, uc, clock


def test_assign_to_existing_aisle_ok(assign_ctx) -> None:
    sr, ir, gr, ar, uc, clock = assign_ctx
    inv, sid, gid = "inv-1", "sess-1", "group-1"
    sr.save(_closed_session(inv, sid))
    t0 = datetime(2025, 1, 2, 12, 0, 0, tzinfo=UTC)
    gr.insert(
        CaptureSessionGroup(
            id=gid,
            session_id=sid,
            group_index=1,
            created_at=t0,
            algorithm_version="time_gap_v1",
        )
    )
    ir.save(_imported_item("i1", sid, gid, t0))
    aisle = Aisle(
        id="aisle-1",
        inventory_id=inv,
        code="A-01",
        status=AisleStatus.CREATED,
        created_at=clock._t,
        updated_at=clock._t,
    )
    ar.save(aisle)

    out = uc.execute(inventory_id=inv, session_id=sid, group_id=gid, aisle_id=aisle.id)
    assert len(out) == 1
    assert out[0].assigned_aisle_id == aisle.id
    assert out[0].assignment_status == "assigned_existing"
    assert out[0].assigned_at == clock._t


def test_double_assign_raises(assign_ctx) -> None:
    sr, ir, gr, ar, uc, clock = assign_ctx
    inv, sid, gid = "inv-1", "sess-1", "group-1"
    sr.save(_closed_session(inv, sid))
    t0 = datetime(2025, 1, 2, 12, 0, 0, tzinfo=UTC)
    gr.insert(
        CaptureSessionGroup(
            id=gid,
            session_id=sid,
            group_index=1,
            created_at=t0,
            algorithm_version="time_gap_v1",
        )
    )
    ir.save(_imported_item("i1", sid, gid, t0))
    aisle = Aisle(
        id="aisle-1",
        inventory_id=inv,
        code="A-01",
        status=AisleStatus.CREATED,
        created_at=clock._t,
        updated_at=clock._t,
    )
    ar.save(aisle)
    uc.execute(inventory_id=inv, session_id=sid, group_id=gid, aisle_id=aisle.id)
    with pytest.raises(CaptureSessionGroupAlreadyAssignedError):
        uc.execute(inventory_id=inv, session_id=sid, group_id=gid, aisle_id=aisle.id)


def test_aisle_wrong_inventory_raises(assign_ctx) -> None:
    sr, ir, gr, ar, uc, clock = assign_ctx
    inv, sid, gid = "inv-1", "sess-1", "group-1"
    sr.save(_closed_session(inv, sid))
    t0 = datetime(2025, 1, 2, 12, 0, 0, tzinfo=UTC)
    gr.insert(
        CaptureSessionGroup(
            id=gid,
            session_id=sid,
            group_index=1,
            created_at=t0,
            algorithm_version="time_gap_v1",
        )
    )
    ir.save(_imported_item("i1", sid, gid, t0))
    aisle = Aisle(
        id="aisle-other",
        inventory_id="inv-2",
        code="X",
        status=AisleStatus.CREATED,
        created_at=clock._t,
        updated_at=clock._t,
    )
    ar.save(aisle)
    with pytest.raises(AisleNotFoundForAssignmentError):
        uc.execute(inventory_id=inv, session_id=sid, group_id=gid, aisle_id=aisle.id)


def test_group_not_found_raises(assign_ctx) -> None:
    sr, ir, gr, ar, uc, clock = assign_ctx
    inv, sid = "inv-1", "sess-1"
    sr.save(_closed_session(inv, sid))
    t0 = datetime(2025, 1, 2, 12, 0, 0, tzinfo=UTC)
    gr.insert(
        CaptureSessionGroup(
            id="real-g",
            session_id=sid,
            group_index=1,
            created_at=t0,
            algorithm_version="time_gap_v1",
        )
    )
    ir.save(_imported_item("i1", sid, "real-g", t0))
    aisle = Aisle(
        id="aisle-1",
        inventory_id=inv,
        code="A-01",
        status=AisleStatus.CREATED,
        created_at=clock._t,
        updated_at=clock._t,
    )
    ar.save(aisle)
    with pytest.raises(CaptureSessionGroupNotFoundError):
        uc.execute(inventory_id=inv, session_id=sid, group_id="missing-g", aisle_id=aisle.id)


def test_open_session_raises_assignment_not_allowed(assign_ctx) -> None:
    sr, ir, gr, ar, uc, clock = assign_ctx
    inv, sid, gid = "inv-1", "sess-1", "group-1"
    t = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
    sr.save(
        CaptureSession(
            id=sid,
            inventory_id=inv,
            aisle_id=None,
            status=CaptureSessionStatus.DRAFT,
            created_at=t,
            updated_at=t,
            opened_at=t,
            closed_at=None,
            clock_offset_seconds=0,
        )
    )
    gr.insert(
        CaptureSessionGroup(
            id=gid,
            session_id=sid,
            group_index=1,
            created_at=t,
            algorithm_version="time_gap_v1",
        )
    )
    ir.save(_imported_item("i1", sid, gid, t))
    aisle = Aisle(
        id="aisle-1",
        inventory_id=inv,
        code="A-01",
        status=AisleStatus.CREATED,
        created_at=clock._t,
        updated_at=clock._t,
    )
    ar.save(aisle)
    with pytest.raises(CaptureSessionGroupAssignmentNotAllowedError):
        uc.execute(inventory_id=inv, session_id=sid, group_id=gid, aisle_id=aisle.id)


def test_wrong_inventory_session_raises_not_found(assign_ctx) -> None:
    _, _, _, ar, uc, clock = assign_ctx
    aisle = Aisle(
        id="aisle-1",
        inventory_id="inv-1",
        code="A-01",
        status=AisleStatus.CREATED,
        created_at=clock._t,
        updated_at=clock._t,
    )
    ar.save(aisle)
    with pytest.raises(CaptureSessionNotFoundError):
        uc.execute(inventory_id="inv-1", session_id="no-session", group_id="g", aisle_id=aisle.id)


def test_create_aisle_and_assign_group() -> None:
    clock = _Clock(datetime(2025, 1, 3, 12, 0, 0, tzinfo=UTC))
    sr = MemoryCaptureSessionRepository()
    ir = MemoryCaptureSessionItemRepository()
    gr = MemoryCaptureSessionGroupRepository(ir)
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    supplier_repo = MemoryClientSupplierRepository()
    now = datetime(2025, 1, 1, 9, 0, 0, tzinfo=UTC)
    client_id = "client-1"
    supplier_repo.save(
        ClientSupplier(
            id="sup-1",
            client_id=client_id,
            name="Supplier",
            status=ClientSupplierStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )
    inv = Inventory(
        id="inv-1",
        name="Inv",
        status=InventoryStatus.DRAFT,
        created_at=now,
        updated_at=now,
        client_id=client_id,
    )
    inv_repo.save(inv)
    reconciler = InventoryStatusReconciler(inv_repo, aisle_repo, clock)
    create_aisle = CreateAisleUseCase(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        client_supplier_repo=supplier_repo,
        clock=clock,
        status_reconciler=reconciler,
    )
    uc = CreateAisleAndAssignCaptureSessionGroupUseCase(
        session_repo=sr,
        group_repo=gr,
        create_aisle=create_aisle,
        clock=clock,
    )
    sid, gid = "sess-1", "group-1"
    sr.save(_closed_session("inv-1", sid))
    t0 = datetime(2025, 1, 2, 12, 0, 0, tzinfo=UTC)
    gr.insert(
        CaptureSessionGroup(
            id=gid,
            session_id=sid,
            group_index=1,
            created_at=t0,
            algorithm_version="time_gap_v1",
        )
    )
    ir.save(_imported_item("i1", sid, gid, t0))

    out = uc.execute(
        inventory_id="inv-1",
        session_id=sid,
        group_id=gid,
        aisle_code="NEW-AISLE",
        client_supplier_id="sup-1",
    )
    assert len(out) == 1
    assert out[0].assignment_status == "assigned_new"
    assert out[0].assigned_aisle_id
    created = aisle_repo.get_by_id(out[0].assigned_aisle_id or "")
    assert created is not None
    assert created.code == "NEW-AISLE"
