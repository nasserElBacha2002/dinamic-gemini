"""SQL integration tests for capture session repositories (skipped without SQL Server)."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest

from src.application.errors import CaptureSessionDuplicateItemContentError, OpenCaptureSessionExistsError
from src.database.sqlserver import SqlServerClient, now_utc
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.capture.entities import (
    CaptureSession,
    CaptureSessionItem,
    CaptureSessionItemAssignmentStatus,
    CaptureSessionItemImportStatus,
    CaptureSessionStatus,
)
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus
from src.infrastructure.repositories.sql_aisle_repository import SqlAisleRepository
from src.infrastructure.repositories.sql_capture_session_item_repository import SqlCaptureSessionItemRepository
from src.infrastructure.repositories.sql_capture_session_repository import SqlCaptureSessionRepository
from src.infrastructure.repositories.sql_inventory_repository import SqlInventoryRepository


def _connection_string() -> str:
    raw = (os.getenv("SQLSERVER_CONNECTION_STRING") or "").strip()
    if raw:
        return raw
    server = (os.getenv("SQLSERVER_SERVER") or "").strip()
    database = (os.getenv("SQLSERVER_DATABASE") or "").strip()
    uid = (os.getenv("SQLSERVER_UID") or "").strip()
    pwd = (os.getenv("SQLSERVER_PWD") or "").strip()
    if server and database and uid and pwd:
        driver = (os.getenv("SQLSERVER_DRIVER") or "").strip()
        if not driver:
            try:
                import pyodbc

                for d in pyodbc.drivers():
                    if "SQL Server" in d:
                        driver = d
                        break
            except Exception:
                pass
        if driver:
            return f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};UID={uid};PWD={pwd};TrustServerCertificate=yes"
    return ""


@pytest.fixture(scope="module")
def sql_client():
    cs = _connection_string()
    if not cs:
        pytest.skip("SQL Server not configured (set SQLSERVER_CONNECTION_STRING or server/database/uid/pwd)")
    return SqlServerClient(cs)


@pytest.fixture
def inv_repo(sql_client):
    return SqlInventoryRepository(sql_client)


@pytest.fixture
def aisle_repo(sql_client):
    return SqlAisleRepository(sql_client)


@pytest.fixture
def session_repo(sql_client):
    return SqlCaptureSessionRepository(sql_client)


@pytest.fixture
def item_repo(sql_client):
    return SqlCaptureSessionItemRepository(sql_client)


def _require_one_open_per_aisle_index(sql_client: SqlServerClient) -> None:
    """Concurrency test needs migration 0018 applied on the target database."""
    with sql_client.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM sys.indexes
            WHERE name = 'UQ_capture_sessions_one_open_per_aisle'
              AND object_id = OBJECT_ID('capture_sessions')
            """
        )
        if cur.fetchone() is None:
            pytest.skip(
                "Index UQ_capture_sessions_one_open_per_aisle missing; apply migration 0018 to run this test"
            )


def _save_inv_aisle(
    inv_repo: SqlInventoryRepository,
    aisle_repo: SqlAisleRepository,
    inv_id: str,
    aisle_id: str,
) -> None:
    t = now_utc()
    inv_repo.save(
        Inventory(
            id=inv_id,
            name=f"cap-sql-{inv_id[:8]}",
            status=InventoryStatus.DRAFT,
            created_at=t,
            updated_at=t,
            processing_mode=InventoryProcessingMode.TEST,
        )
    )
    aisle_repo.save(
        Aisle(
            id=aisle_id,
            inventory_id=inv_id,
            code=f"CAP-{aisle_id[:6]}",
            status=AisleStatus.CREATED,
            created_at=t,
            updated_at=t,
        )
    )


def test_sql_capture_session_save_and_get_by_id(
    inv_repo: SqlInventoryRepository,
    aisle_repo: SqlAisleRepository,
    session_repo: SqlCaptureSessionRepository,
) -> None:
    suffix = uuid.uuid4().hex[:10]
    inv_id = f"cap-inv-{suffix}"
    aisle_id = f"cap-aisle-{suffix}"
    _save_inv_aisle(inv_repo, aisle_repo, inv_id, aisle_id)
    t = now_utc()
    sid = f"cap-sess-{suffix}"
    s = CaptureSession(
        id=sid,
        inventory_id=inv_id,
        aisle_id=aisle_id,
        status=CaptureSessionStatus.DRAFT,
        created_at=t,
        updated_at=t,
        opened_at=t,
        closed_at=None,
    )
    session_repo.save(s)
    loaded = session_repo.get_by_id(sid)
    assert loaded is not None
    assert loaded.id == sid
    assert loaded.inventory_id == inv_id
    assert loaded.status == CaptureSessionStatus.DRAFT


def test_sql_open_session_count_and_close(
    inv_repo: SqlInventoryRepository,
    aisle_repo: SqlAisleRepository,
    session_repo: SqlCaptureSessionRepository,
) -> None:
    suffix = uuid.uuid4().hex[:10]
    inv_id = f"cap-inv2-{suffix}"
    aisle_id = f"cap-aisle2-{suffix}"
    _save_inv_aisle(inv_repo, aisle_repo, inv_id, aisle_id)
    t = now_utc()
    s1 = CaptureSession(
        id=f"cap-s1-{suffix}",
        inventory_id=inv_id,
        aisle_id=aisle_id,
        status=CaptureSessionStatus.DRAFT,
        created_at=t,
        updated_at=t,
        opened_at=t,
        closed_at=None,
    )
    session_repo.save(s1)
    assert session_repo.count_open_sessions_for_aisle(inv_id, aisle_id) == 1
    s1.status = CaptureSessionStatus.CANCELLED
    s1.closed_at = t
    s1.updated_at = t
    session_repo.save(s1)
    assert session_repo.count_open_sessions_for_aisle(inv_id, aisle_id) == 0


def test_sql_second_open_session_same_aisle_raises(
    sql_client: SqlServerClient,
    inv_repo: SqlInventoryRepository,
    aisle_repo: SqlAisleRepository,
    session_repo: SqlCaptureSessionRepository,
) -> None:
    _require_one_open_per_aisle_index(sql_client)
    suffix = uuid.uuid4().hex[:10]
    inv_id = f"cap-inv3-{suffix}"
    aisle_id = f"cap-aisle3-{suffix}"
    _save_inv_aisle(inv_repo, aisle_repo, inv_id, aisle_id)
    t = now_utc()
    session_repo.save(
        CaptureSession(
            id=f"cap-open-a-{suffix}",
            inventory_id=inv_id,
            aisle_id=aisle_id,
            status=CaptureSessionStatus.DRAFT,
            created_at=t,
            updated_at=t,
            opened_at=t,
            closed_at=None,
        )
    )
    s2 = CaptureSession(
        id=f"cap-open-b-{suffix}",
        inventory_id=inv_id,
        aisle_id=aisle_id,
        status=CaptureSessionStatus.DRAFT,
        created_at=t,
        updated_at=t,
        opened_at=t,
        closed_at=None,
    )
    with pytest.raises(OpenCaptureSessionExistsError):
        session_repo.save(s2)


def test_sql_duplicate_item_content_hash(
    inv_repo: SqlInventoryRepository,
    aisle_repo: SqlAisleRepository,
    session_repo: SqlCaptureSessionRepository,
    item_repo: SqlCaptureSessionItemRepository,
) -> None:
    suffix = uuid.uuid4().hex[:10]
    inv_id = f"cap-inv4-{suffix}"
    aisle_id = f"cap-aisle4-{suffix}"
    _save_inv_aisle(inv_repo, aisle_repo, inv_id, aisle_id)
    t = now_utc()
    sid = f"cap-sess4-{suffix}"
    session_repo.save(
        CaptureSession(
            id=sid,
            inventory_id=inv_id,
            aisle_id=aisle_id,
            status=CaptureSessionStatus.IMPORTING,
            created_at=t,
            updated_at=t,
            opened_at=t,
            closed_at=None,
        )
    )
    h = "deadbeef" * 8
    item_repo.save(
        CaptureSessionItem(
            id=f"cap-item-a-{suffix}",
            session_id=sid,
            staging_storage_key=f"capture/staging/{suffix}/a.bin",
            import_status=CaptureSessionItemImportStatus.IMPORTED,
            assignment_status=CaptureSessionItemAssignmentStatus.PENDING,
            updated_at=t,
            content_hash=h,
        )
    )
    with pytest.raises(CaptureSessionDuplicateItemContentError):
        item_repo.save(
            CaptureSessionItem(
                id=f"cap-item-b-{suffix}",
                session_id=sid,
                staging_storage_key=f"capture/staging/{suffix}/b.bin",
                import_status=CaptureSessionItemImportStatus.IMPORTED,
                assignment_status=CaptureSessionItemAssignmentStatus.PENDING,
                updated_at=t,
                content_hash=h,
            )
        )


def test_sql_list_sessions_pagination(
    inv_repo: SqlInventoryRepository,
    aisle_repo: SqlAisleRepository,
    session_repo: SqlCaptureSessionRepository,
) -> None:
    suffix = uuid.uuid4().hex[:10]
    inv_id = f"cap-inv5-{suffix}"
    t = now_utc()
    inv_repo.save(
        Inventory(
            id=inv_id,
            name=f"cap-sql-pg-{suffix[:8]}",
            status=InventoryStatus.DRAFT,
            created_at=t,
            updated_at=t,
            processing_mode=InventoryProcessingMode.TEST,
        )
    )
    for i in range(3):
        aid = f"cap-a5-{suffix}-{i}"
        aisle_repo.save(
            Aisle(
                id=aid,
                inventory_id=inv_id,
                code=f"P{i}-{suffix}",
                status=AisleStatus.CREATED,
                created_at=t,
                updated_at=t,
            )
        )
        session_repo.save(
            CaptureSession(
                id=f"cap-s5-{suffix}-{i}",
                inventory_id=inv_id,
                aisle_id=aid,
                status=CaptureSessionStatus.CANCELLED,
                created_at=datetime(2026, 1, i + 1, 12, 0, 0, tzinfo=timezone.utc),
                updated_at=t,
                opened_at=t,
                closed_at=t,
            )
        )
    page1, total = session_repo.list_by_inventory(inv_id, page=1, page_size=2)
    assert total == 3
    assert len(page1) == 2
    page2, total2 = session_repo.list_by_inventory(inv_id, page=2, page_size=2)
    assert total2 == 3
    assert len(page2) == 1
