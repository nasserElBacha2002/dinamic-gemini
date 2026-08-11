"""Catalog-backed assertions that critical DB uniqueness objects exist (SQL Server)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pyodbc
import pytest

from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus
from src.infrastructure.repositories.sql_aisle_repository import SqlAisleRepository
from src.infrastructure.repositories.sql_inventory_repository import SqlInventoryRepository
from tests.support.sql_integration import sql_server_client_or_skip
from tests.support.sql_migration_fixture import ensure_sql_migrations_applied
from tests.support.sqlserver_test_connection import resolved_sqlserver_connection_string_for_tests

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def sql_client():
    client = sql_server_client_or_skip(resolved_sqlserver_connection_string_for_tests())
    ensure_sql_migrations_applied(client)
    return client


@pytest.fixture(scope="module")
def migration_status(sql_client):
    from src.config import load_settings
    from src.database.migrations import get_migration_status

    settings = load_settings()
    return get_migration_status(client=sql_client, service=settings.db_schema_service_name)


def _index_exists(cur, *, table: str, index: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM sys.indexes i
        INNER JOIN sys.tables t ON t.object_id = i.object_id
        INNER JOIN sys.schemas s ON s.schema_id = t.schema_id
        WHERE s.name = N'dbo'
          AND t.name = ?
          AND i.name = ?
        """,
        (table, index),
    )
    return cur.fetchone() is not None


def _index_is_unique(cur, *, table: str, index: str) -> bool:
    cur.execute(
        """
        SELECT i.is_unique, i.has_filter, i.filter_definition
        FROM sys.indexes i
        INNER JOIN sys.tables t ON t.object_id = i.object_id
        INNER JOIN sys.schemas s ON s.schema_id = t.schema_id
        WHERE s.name = N'dbo'
          AND t.name = ?
          AND i.name = ?
        """,
        (table, index),
    )
    row = cur.fetchone()
    if row is None:
        return False
    return bool(row.is_unique)


def _index_columns(cur, *, table: str, index: str) -> list[str]:
    cur.execute(
        """
        SELECT c.name
        FROM sys.indexes i
        INNER JOIN sys.index_columns ic
            ON ic.object_id = i.object_id AND ic.index_id = i.index_id
        INNER JOIN sys.columns c
            ON c.object_id = ic.object_id AND c.column_id = ic.column_id
        INNER JOIN sys.tables t ON t.object_id = i.object_id
        INNER JOIN sys.schemas s ON s.schema_id = t.schema_id
        WHERE s.name = N'dbo'
          AND t.name = ?
          AND i.name = ?
          AND ic.is_included_column = 0
        ORDER BY ic.key_ordinal
        """,
        (table, index),
    )
    return [str(r.name) for r in cur.fetchall()]


def _index_filter(cur, *, table: str, index: str) -> tuple[bool, str | None]:
    cur.execute(
        """
        SELECT i.has_filter, i.filter_definition
        FROM sys.indexes i
        INNER JOIN sys.tables t ON t.object_id = i.object_id
        INNER JOIN sys.schemas s ON s.schema_id = t.schema_id
        WHERE s.name = N'dbo'
          AND t.name = ?
          AND i.name = ?
        """,
        (table, index),
    )
    row = cur.fetchone()
    if row is None:
        return False, None
    definition = str(row.filter_definition) if row.filter_definition is not None else None
    return bool(row.has_filter), definition


def _fk_exists(cur, *, name: str) -> bool:
    cur.execute(
        "SELECT 1 FROM sys.foreign_keys WHERE name = ?",
        (name,),
    )
    return cur.fetchone() is not None


def _assert_unique_violation(exc: BaseException) -> None:
    assert isinstance(exc, pyodbc.IntegrityError)
    sqlstate = getattr(exc, "args", [None])[0]
    assert sqlstate in ("23000", "23505")
    message = str(exc).lower()
    assert "2627" in message or "2601" in message or "unique" in message


def _seed_aisle(sql_client) -> str:
    inv_repo = SqlInventoryRepository(sql_client)
    aisle_repo = SqlAisleRepository(sql_client)
    now = datetime.now(timezone.utc)
    inv_id = f"inv-cidx-{uuid.uuid4().hex[:10]}"
    aisle_id = f"aisle-cidx-{uuid.uuid4().hex[:10]}"
    inv_repo.save(
        Inventory(
            id=inv_id,
            name="Catalog index behavior",
            status=InventoryStatus.PROCESSING,
            created_at=now,
            updated_at=now,
            processing_mode=InventoryProcessingMode.TEST,
        )
    )
    aisle_repo.save(
        Aisle(
            id=aisle_id,
            inventory_id=inv_id,
            code=f"A-{uuid.uuid4().hex[:6]}",
            status=AisleStatus.CREATED,
            created_at=now,
            updated_at=now,
        )
    )
    return aisle_id


@pytest.mark.parametrize(
    ("table", "index", "columns", "require_filter", "filter_predicates"),
    [
        (
            "source_assets",
            "UQ_source_assets_aisle_upload_batch_client",
            ["aisle_id", "upload_batch_id", "upload_client_file_id"],
            True,
            ["upload_batch_id", "upload_client_file_id"],
        ),
        (
            "source_assets",
            "UQ_source_assets_ordered_session_sequence",
            ["ordered_capture_session_id", "sequence_number"],
            True,
            ["ordered_capture_session_id", "sequence_number"],
        ),
        (
            "source_assets",
            "UQ_source_assets_ordered_session_client_file",
            ["ordered_capture_session_id", "upload_client_file_id"],
            True,
            ["ordered_capture_session_id", "upload_client_file_id"],
        ),
        (
            "manual_product_position_overrides",
            "UQ_manual_position_override_active",
            ["job_id", "result_id"],
            True,
            ["is_active"],
        ),
        (
            "external_image_analysis_requests",
            "UQ_eiar_idempotency_key",
            ["idempotency_key"],
            False,
            [],
        ),
        (
            "local_csv_productive_results",
            "UX_local_csv_productive_label",
            ["capture_session_id", "label_id"],
            True,
            ["label_id"],
        ),
        (
            "local_csv_import_rows",
            "UX_local_csv_import_rows_imported_label",
            ["capture_session_id", "label_id"],
            True,
            ["label_id", "status"],
        ),
        (
            "inventory_counted_product_labels",
            "UQ_icpl_aisle_label",
            ["aisle_id", "label_id"],
            False,
            [],
        ),
    ],
)
def test_critical_unique_index_present(
    sql_client,
    table: str,
    index: str,
    columns: list[str],
    require_filter: bool,
    filter_predicates: list[str],
) -> None:
    with sql_client.cursor() as cur:
        if not _index_exists(cur, table=table, index=index):
            pytest.fail(
                f"Critical unique index {index} on {table} is missing; "
                "expected migrations through 0095 to be applied"
            )
        assert _index_is_unique(cur, table=table, index=index)
        assert _index_columns(cur, table=table, index=index) == columns
        has_filter, definition = _index_filter(cur, table=table, index=index)
        if require_filter:
            assert has_filter is True
            assert definition
            lowered = definition.lower()
            for predicate in filter_predicates:
                assert predicate.lower() in lowered, (
                    f"filter_definition for {index} missing predicate {predicate!r}: "
                    f"{definition!r}"
                )


def test_0095_icpl_aisle_fk_and_not_null(sql_client) -> None:
    with sql_client.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM sys.tables
            WHERE name = N'inventory_counted_product_labels'
            """
        )
        if cur.fetchone() is None:
            pytest.fail(
                "inventory_counted_product_labels table missing; apply migrations through 0095"
            )
        cur.execute(
            """
            SELECT is_nullable
            FROM sys.columns
            WHERE object_id = OBJECT_ID(N'dbo.inventory_counted_product_labels')
              AND name = N'aisle_id'
            """
        )
        col = cur.fetchone()
        if col is None:
            pytest.fail("aisle_id column missing on inventory_counted_product_labels (0095)")
        assert int(col.is_nullable) == 0
        if not _fk_exists(cur, name="FK_icpl_aisle"):
            pytest.fail("FK_icpl_aisle missing after migration 0095")
        if not _index_exists(
            cur, table="inventory_counted_product_labels", index="UQ_icpl_aisle_label"
        ):
            pytest.fail("UQ_icpl_aisle_label missing after migration 0095")
        assert not _index_exists(
            cur, table="inventory_counted_product_labels", index="UQ_icpl_inventory_label"
        )


def test_0094_legacy_photo_unique_dropped(sql_client) -> None:
    with sql_client.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM sys.tables
            WHERE name = N'local_csv_productive_results'
            """
        )
        if cur.fetchone() is None:
            pytest.fail("local_csv_productive_results table missing; apply migration 0086+")
        if not _index_exists(
            cur, table="local_csv_productive_results", index="UX_local_csv_productive_label"
        ):
            pytest.fail("UX_local_csv_productive_label missing; apply migration 0094")
        assert not _index_exists(
            cur,
            table="local_csv_productive_results",
            index="UX_local_csv_productive_secondary",
        )
        assert not _index_exists(
            cur,
            table="local_csv_import_rows",
            index="UX_local_csv_import_rows_imported_secondary",
        )


def test_migrations_include_0094_and_0095(migration_status) -> None:
    current = migration_status.current_version or ""
    assert current >= "0095", (
        f"Expected schema at least 0095 after run_pending_migrations; current={current!r}"
    )
    assert "0094" <= current
    assert migration_status.pending_versions == []


def test_uq_source_assets_upload_batch_client_enforces_uniqueness(sql_client) -> None:
    aisle_id = _seed_aisle(sql_client)
    asset_ids: list[str] = []
    batch_id = f"batch-{uuid.uuid4().hex[:8]}"
    client_file_id = f"file-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)
    try:
        with sql_client.cursor() as cur:
            for idx in range(2):
                asset_id = str(uuid.uuid4())
                asset_ids.append(asset_id)
                cur.execute(
                    """
                    INSERT INTO source_assets (
                        id, aisle_id, type, original_filename, storage_path,
                        mime_type, uploaded_at, upload_batch_id, upload_client_file_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        asset_id,
                        aisle_id,
                        "photo",
                        f"photo-{idx}.jpg",
                        f"/tmp/photo-{idx}.jpg",
                        "image/jpeg",
                        now,
                        batch_id if idx == 0 else batch_id,
                        client_file_id if idx == 0 else client_file_id,
                    ),
                )
                if idx == 1:
                    pytest.fail("Expected duplicate insert to raise IntegrityError")
    except pyodbc.IntegrityError as exc:
        _assert_unique_violation(exc)
    finally:
        with sql_client.cursor() as cur:
            if asset_ids:
                placeholders = ",".join("?" * len(asset_ids))
                cur.execute(
                    f"DELETE FROM source_assets WHERE id IN ({placeholders})",
                    asset_ids,
                )


def test_uq_source_assets_upload_batch_client_allows_null_filter_columns(sql_client) -> None:
    aisle_id = _seed_aisle(sql_client)
    asset_ids: list[str] = []
    now = datetime.now(timezone.utc)
    try:
        with sql_client.cursor() as cur:
            for idx in range(2):
                asset_id = str(uuid.uuid4())
                asset_ids.append(asset_id)
                cur.execute(
                    """
                    INSERT INTO source_assets (
                        id, aisle_id, type, original_filename, storage_path,
                        mime_type, uploaded_at, upload_batch_id, upload_client_file_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        asset_id,
                        aisle_id,
                        "photo",
                        f"null-filter-{idx}.jpg",
                        f"/tmp/null-filter-{idx}.jpg",
                        "image/jpeg",
                        now,
                        None,
                        None,
                    ),
                )
    finally:
        with sql_client.cursor() as cur:
            if asset_ids:
                placeholders = ",".join("?" * len(asset_ids))
                cur.execute(
                    f"DELETE FROM source_assets WHERE id IN ({placeholders})",
                    asset_ids,
                )
