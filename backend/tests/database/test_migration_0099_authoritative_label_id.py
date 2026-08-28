"""Smoke + SQL upgrade: migration 0099 additive label_id on authoritative results."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.database.sqlserver import SqlServerClient
from tests.support.sql_integration import sql_server_client_or_skip
from tests.support.sqlserver_test_connection import resolved_sqlserver_connection_string_for_tests

_MIGRATION_DIR = (
    Path(__file__).resolve().parents[2] / "src" / "database" / "migrations" / "versions"
)


def _read(name: str) -> str:
    return (_MIGRATION_DIR / name).read_text(encoding="utf-8")


def test_migration_0099_files_exist_and_are_additive() -> None:
    up = _read("0099_authoritative_local_code_scan_label_id.sql")
    down = _read("0099_authoritative_local_code_scan_label_id.down.sql")
    assert "authoritative_local_code_scan_results" in up
    assert "label_id NVARCHAR(64) NULL" in up
    assert "IX_alcsr_aisle_label" in up
    assert "WHERE label_id IS NOT NULL" in up
    assert "DROP COLUMN label_id" in down
    assert "DROP INDEX IX_alcsr_aisle_label" in down
    assert "DROP TABLE" not in up.split("Formal rollback")[0]


def _apply_0099_batches(client: SqlServerClient) -> None:
    sql = _read("0099_authoritative_local_code_scan_label_id.sql")
    batches: list[str] = []
    buf: list[str] = []
    for line in sql.splitlines():
        if line.strip().upper() == "GO":
            if buf:
                batches.append("\n".join(buf))
                buf = []
        else:
            buf.append(line)
    if buf:
        batches.append("\n".join(buf))
    with client.cursor() as cur:
        for batch in batches:
            if batch.strip():
                cur.execute(batch)


@pytest.mark.integration
def test_migration_0099_upgrade_preserves_historical_row() -> None:
    """Insert historical authoritative row (label_id NULL), apply 0099, verify intact."""
    cs = resolved_sqlserver_connection_string_for_tests()
    if not cs:
        pytest.skip("SQL Server not configured")
    client = sql_server_client_or_skip(cs)
    from src.domain.aisle.entities import Aisle, AisleStatus
    from src.domain.assets.entities import SourceAsset, SourceAssetType
    from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus
    from src.infrastructure.repositories.sql_aisle_repository import SqlAisleRepository
    from src.infrastructure.repositories.sql_inventory_repository import SqlInventoryRepository
    from src.infrastructure.repositories.sql_source_asset_repository import SqlSourceAssetRepository

    now = datetime(2026, 8, 28, 12, 0, 0, tzinfo=timezone.utc)
    inv_id = f"inv-m9-{uuid.uuid4().hex[:8]}"
    aisle_id = f"aisle-m9-{uuid.uuid4().hex[:8]}"
    asset_id = f"asset-m9-{uuid.uuid4().hex[:8]}"
    row_id = f"m9-{uuid.uuid4().hex[:12]}"
    SqlInventoryRepository(client).save(
        Inventory(
            id=inv_id,
            name="m9 upgrade",
            status=InventoryStatus.PROCESSING,
            created_at=now,
            updated_at=now,
            processing_mode=InventoryProcessingMode.TEST,
        )
    )
    SqlAisleRepository(client).save(
        Aisle(
            id=aisle_id,
            inventory_id=inv_id,
            code=f"M9-{uuid.uuid4().hex[:4]}",
            status=AisleStatus.CREATED,
            created_at=now,
            updated_at=now,
        )
    )
    SqlSourceAssetRepository(client).save(
        SourceAsset(
            id=asset_id,
            aisle_id=aisle_id,
            type=SourceAssetType.PHOTO,
            original_filename="m9.jpg",
            storage_path="/tmp/m9.jpg",
            mime_type="image/jpeg",
            uploaded_at=now,
            upload_client_file_id=f"cf-{uuid.uuid4().hex[:8]}",
        )
    )
    sha = "sha256:" + ("a" * 64)
    content_hash = "sha256:" + ("b" * 64)

    with client.cursor() as cur:
        cur.execute(
            """
            IF OBJECT_ID(N'dbo.authoritative_local_code_scan_results', N'U') IS NULL
                SELECT 0 AS ok
            ELSE
                SELECT 1 AS ok
            """
        )
        if cur.fetchone()[0] != 1:
            pytest.skip("authoritative_local_code_scan_results table missing")

        cur.execute(
            """
            INSERT INTO dbo.authoritative_local_code_scan_results (
                id, asset_id, inventory_id, aisle_id, client_file_id,
                result_version, supersedes_result_id, is_current,
                internal_code, quantity, quantity_status, source,
                detected_internal_code, detected_quantity, detected_symbology,
                parser_version, detector_version, prepared_asset_sha256,
                content_hash, confirmed_by, client_confirmed_at,
                server_confirmed_at, server_received_at, confirmed_at,
                applied_job_id, applied_at, row_version, schema_version,
                created_at, updated_at
            ) VALUES (
                ?, ?, ?, ?, ?,
                1, NULL, 1,
                ?, NULL, ?, ?,
                ?, NULL, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                NULL, NULL, 1, ?,
                ?, ?
            )
            """,
            (
                row_id,
                asset_id,
                inv_id,
                aisle_id,
                f"cf-{uuid.uuid4().hex[:8]}",
                "LEGACY-SKU",
                "MISSING",
                "LOCAL_CODE_SCAN",
                "LEGACY-SKU",
                "QR_CODE",
                "1",
                "mlkit",
                sha,
                content_hash,
                "user-test",
                now,
                now,
                now,
                now,
                "1",
                now,
                now,
            ),
        )

    _apply_0099_batches(client)
    _apply_0099_batches(client)

    with client.cursor() as cur:
        cur.execute(
            """
            SELECT internal_code, quantity_status, label_id
            FROM dbo.authoritative_local_code_scan_results
            WHERE id = ?
            """,
            (row_id,),
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "LEGACY-SKU"
        assert row[1] == "MISSING"
        assert row[2] is None
        cur.execute(
            """
            SELECT COL_LENGTH(N'dbo.authoritative_local_code_scan_results', N'label_id')
            """
        )
        col_len = cur.fetchone()[0]
        assert col_len is not None and int(col_len) > 0

        cur.execute(
            """
            DELETE FROM dbo.authoritative_local_code_scan_results WHERE id = ?
            """,
            (row_id,),
        )
        cur.execute("DELETE FROM dbo.source_assets WHERE id = ?", (asset_id,))
        cur.execute("DELETE FROM dbo.aisles WHERE id = ?", (aisle_id,))
        cur.execute("DELETE FROM dbo.inventories WHERE id = ?", (inv_id,))
