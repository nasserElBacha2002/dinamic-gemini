"""SQL Server integration tests for mobile_preliminary_detections (Phase 4)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from src.application.ports.mobile_preliminary_detection_repository import (
    PreliminaryUniqueViolationError,
)
from src.domain.mobile_preliminary_detections.entities import MobilePreliminaryDetection
from src.infrastructure.repositories.sql_mobile_preliminary_detection_repository import (
    SqlMobilePreliminaryDetectionRepository,
)
from tests.support.sql_integration import sql_server_client_or_skip
from tests.support.sqlserver_test_connection import resolved_sqlserver_connection_string_for_tests


@pytest.fixture(scope="module")
def sql_client():
    return sql_server_client_or_skip(resolved_sqlserver_connection_string_for_tests())


@pytest.fixture(scope="module")
def ensure_table(sql_client):
    with sql_client.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_NAME = 'mobile_preliminary_detections'
            """
        )
        if cur.fetchone() is None:
            pytest.skip("mobile_preliminary_detections not migrated yet")
    return sql_client


def _row(**over) -> MobilePreliminaryDetection:
    now = datetime.now(timezone.utc)
    base = dict(
        id=str(uuid.uuid4()),
        draft_id=str(uuid.uuid4()),
        inventory_id="00000000-0000-0000-0000-000000000001",
        aisle_id="00000000-0000-0000-0000-000000000002",
        asset_id="00000000-0000-0000-0000-000000000003",
        client_file_id=str(uuid.uuid4()),
        status="RESOLVED",
        internal_code="T1",
        quantity=1,
        quantity_status="PRESENT",
        detected_format="PIPE",
        detected_symbology="QR_CODE",
        candidate_count=1,
        parser_version="1.1.0",
        detector_version="mlkit-1",
        prepared_asset_sha256="sha256:" + ("c" * 64),
        payload_hash="sha256:" + ("d" * 64),
        processing_ms=10,
        detected_at=now,
        received_at=now,
        expires_at=now + timedelta(days=90),
        validation_status="VALIDATED",
        validation_error_code=None,
        schema_version="1",
        created_at=now,
        updated_at=now,
    )
    base.update(over)
    return MobilePreliminaryDetection(**base)


def test_table_has_unique_constraints(ensure_table):
    client = ensure_table
    with client.cursor() as cur:
        cur.execute(
            """
            SELECT name FROM sys.key_constraints
            WHERE parent_object_id = OBJECT_ID('mobile_preliminary_detections')
              AND type = 'UQ'
            """
        )
        names = {r[0].lower() for r in cur.fetchall()}
    assert "uq_mpd_draft_id" in names
    assert "uq_mpd_client_versions_hash" in names


def test_insert_duplicate_draft_id_raises_typed(ensure_table):
    """Requires existing inventory/aisle/asset FKs — skip if seed rows absent."""
    client = ensure_table
    repo = SqlMobilePreliminaryDetectionRepository(client)
    # Probe FK parents; skip if not present in this DB
    with client.cursor() as cur:
        cur.execute("SELECT TOP 1 id FROM inventories")
        inv = cur.fetchone()
        cur.execute("SELECT TOP 1 id, inventory_id FROM aisles")
        aisle = cur.fetchone()
        cur.execute("SELECT TOP 1 id, aisle_id FROM source_assets")
        asset = cur.fetchone()
    if not inv or not aisle or not asset:
        pytest.skip("No seed inventory/aisle/asset for FK insert")

    draft_id = str(uuid.uuid4())
    client_file = str(uuid.uuid4())
    sha = "sha256:" + uuid.uuid4().hex + uuid.uuid4().hex[:32]
    # pad sha to 64 hex after prefix
    sha = "sha256:" + ("e" * 64)
    row = _row(
        draft_id=draft_id,
        inventory_id=str(inv[0]),
        aisle_id=str(aisle[0]),
        asset_id=str(asset[0]),
        client_file_id=client_file,
        prepared_asset_sha256=sha,
    )
    try:
        repo.insert(row)
        with pytest.raises(PreliminaryUniqueViolationError) as exc:
            repo.insert(
                _row(
                    draft_id=draft_id,
                    inventory_id=str(inv[0]),
                    aisle_id=str(aisle[0]),
                    asset_id=str(asset[0]),
                    client_file_id=str(uuid.uuid4()),
                    prepared_asset_sha256="sha256:" + ("f" * 64),
                )
            )
        assert exc.value.constraint == "draft_id"
    finally:
        with client.cursor() as cur:
            cur.execute(
                "DELETE FROM mobile_preliminary_detections WHERE draft_id = ?",
                (draft_id,),
            )


def test_delete_expired(ensure_table):
    client = ensure_table
    repo = SqlMobilePreliminaryDetectionRepository(client)
    with client.cursor() as cur:
        cur.execute("SELECT TOP 1 id FROM inventories")
        inv = cur.fetchone()
        cur.execute("SELECT TOP 1 id FROM aisles")
        aisle = cur.fetchone()
        cur.execute("SELECT TOP 1 id FROM source_assets")
        asset = cur.fetchone()
    if not inv or not aisle or not asset:
        pytest.skip("No seed inventory/aisle/asset for FK insert")

    draft_id = str(uuid.uuid4())
    past = datetime(2020, 1, 1, tzinfo=timezone.utc)
    row = _row(
        draft_id=draft_id,
        inventory_id=str(inv[0]),
        aisle_id=str(aisle[0]),
        asset_id=str(asset[0]),
        client_file_id=str(uuid.uuid4()),
        prepared_asset_sha256="sha256:" + ("1" * 64),
        received_at=past,
        expires_at=past,
        created_at=past,
        updated_at=past,
    )
    try:
        repo.insert(row)
        deleted = repo.delete_expired(now=datetime.now(timezone.utc), limit=10)
        assert deleted >= 1
        assert repo.get_by_draft_id(draft_id) is None
    finally:
        with client.cursor() as cur:
            cur.execute(
                "DELETE FROM mobile_preliminary_detections WHERE draft_id = ?",
                (draft_id,),
            )
