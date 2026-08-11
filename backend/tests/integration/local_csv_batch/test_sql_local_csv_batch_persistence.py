"""SQL Server integration: batch productive writer + candidate-scoped secondary keys."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus
from src.domain.local_csv_import.entities import LocalCsvImport, LocalCsvImportRow
from src.domain.local_csv_import.sources import INGESTION_SOURCE_LOCAL_CSV_IMPORT
from src.infrastructure.database.sql_transaction import sql_repository_cursor
from src.infrastructure.repositories.local_csv_inventory_result_writer import (
    SqlLocalCsvInventoryResultWriter,
)
from src.infrastructure.repositories.sql_aisle_repository import SqlAisleRepository
from src.infrastructure.repositories.sql_inventory_repository import SqlInventoryRepository
from src.infrastructure.repositories.sql_local_csv_import_repository import (
    SqlLocalCsvImportRepository,
)
from tests.support.sql_integration import sql_server_client_or_skip
from tests.support.sql_migration_fixture import ensure_sql_migrations_applied
from tests.support.sqlserver_test_connection import resolved_sqlserver_connection_string_for_tests

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def sql_client():
    client = sql_server_client_or_skip(resolved_sqlserver_connection_string_for_tests())
    ensure_sql_migrations_applied(client)
    return client


def _seed(client) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    inv_id = f"inv-batch-{uuid.uuid4().hex[:10]}"
    aisle_id = f"aisle-batch-{uuid.uuid4().hex[:10]}"
    SqlInventoryRepository(client).save(
        Inventory(
            id=inv_id,
            name="Batch writer SQL",
            status=InventoryStatus.DRAFT,
            created_at=now,
            updated_at=now,
            processing_mode=InventoryProcessingMode.TEST,
        )
    )
    SqlAisleRepository(client).save(
        Aisle(
            id=aisle_id,
            inventory_id=inv_id,
            code=f"B-{uuid.uuid4().hex[:6]}",
            status=AisleStatus.CREATED,
            created_at=now,
            updated_at=now,
        )
    )
    return inv_id, aisle_id


def _build_previewed_import(
    *,
    inventory_id: str,
    aisle_id: str,
    n_rows: int,
    with_labels: bool = True,
    include_nullables: bool = False,
) -> LocalCsvImport:
    now = datetime.now(timezone.utc)
    import_id = str(uuid.uuid4())
    export_id = f"exp-{uuid.uuid4().hex[:12]}"
    rows: list[LocalCsvImportRow] = []
    for i in range(n_rows):
        label = f"L{uuid.uuid4().hex[:8].upper()}" if with_labels else None
        rows.append(
            LocalCsvImportRow(
                id=str(uuid.uuid4()),
                import_id=import_id,
                row_number=i + 1,
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                capture_session_id=f"sess-{export_id}",
                capture_photo_id=f"photo-{i}",
                client_file_id=f"file-{i}",
                capture_order=i + 1,
                captured_at=now,
                position_code="" if include_nullables and i % 2 == 0 else f"P-{i}",
                internal_code=f"SKU-{i}",
                quantity=1 if not include_nullables else (None if i % 3 == 0 else 2),
                quantity_status="PRESENT",
                detection_status="DETECTED",
                detection_source="LOCAL_CODE_SCAN",
                ingestion_source=INGESTION_SOURCE_LOCAL_CSV_IMPORT,
                requires_review=False,
                error_code=None,
                notes=None,
                status="PREVIEW_VALID",
                label_id=label,
                position_label_id=None,
                position_payload_raw=None if not include_nullables else None,
            )
        )
    return LocalCsvImport(
        id=import_id,
        export_id=export_id,
        schema_version="1",
        inventory_id=inventory_id,
        device_id="device-batch",
        exported_at=now,
        status="PREVIEWED",
        content_hash=uuid.uuid4().hex,
        total_rows=n_rows,
        valid_rows=n_rows,
        rejected_rows=0,
        duplicate_rows=0,
        created_at=now,
        updated_at=now,
        conflict_policy="SKIP",
        rows=tuple(rows),
    )


def _count_productive(client, inventory_id: str) -> int:
    with client.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS c FROM local_csv_productive_results WHERE inventory_id = ?",
            (inventory_id,),
        )
        row = cur.fetchone()
        return int(row.c)


@pytest.mark.parametrize("n_rows", [10, 100, 1000])
def test_batch_apply_import_happy_path(sql_client, n_rows: int) -> None:
    inv_id, aisle_id = _seed(sql_client)
    record = _build_previewed_import(
        inventory_id=inv_id, aisle_id=aisle_id, n_rows=n_rows
    )
    csv_repo = SqlLocalCsvImportRepository(sql_client)
    csv_repo.save(record)
    writer = SqlLocalCsvInventoryResultWriter(sql_client)

    with sql_client.begin_transaction() as txn:
        with sql_repository_cursor(sql_client, connection=txn.connection) as cur:
            applied = writer.apply_import(
                record=record,
                rows_to_import=record.rows,
                confirmed_by_user_id="user-batch",
                cursor=cur,
            )
        txn.commit()

    assert len(applied) == n_rows
    assert _count_productive(sql_client, inv_id) == n_rows
    listed = writer.list_for_import(record.id)
    assert len(listed) == n_rows


def test_batch_apply_import_rollback_on_failure(sql_client) -> None:
    inv_id, aisle_id = _seed(sql_client)
    record = _build_previewed_import(inventory_id=inv_id, aisle_id=aisle_id, n_rows=25)
    SqlLocalCsvImportRepository(sql_client).save(record)
    writer = SqlLocalCsvInventoryResultWriter(sql_client)

    class BoomError(Exception):
        pass

    try:
        with sql_client.begin_transaction() as txn:
            with sql_repository_cursor(sql_client, connection=txn.connection) as cur:
                writer.apply_import(
                    record=record,
                    rows_to_import=record.rows,
                    confirmed_by_user_id=None,
                    cursor=cur,
                )
                raise BoomError("fail after batch insert, before commit")
    except BoomError:
        pass

    assert _count_productive(sql_client, inv_id) == 0


def test_batch_apply_import_idempotent_reapply(sql_client) -> None:
    inv_id, aisle_id = _seed(sql_client)
    record = _build_previewed_import(inventory_id=inv_id, aisle_id=aisle_id, n_rows=15)
    SqlLocalCsvImportRepository(sql_client).save(record)
    writer = SqlLocalCsvInventoryResultWriter(sql_client)

    first = writer.apply_import(
        record=record,
        rows_to_import=record.rows,
        confirmed_by_user_id="u1",
    )
    second = writer.apply_import(
        record=record,
        rows_to_import=record.rows,
        confirmed_by_user_id="u2",
    )
    assert len(first) == 15
    assert len(second) == 15
    assert {r.id for r in first} == {r.id for r in second}
    assert _count_productive(sql_client, inv_id) == 15


def test_batch_apply_import_mixed_nullables(sql_client) -> None:
    inv_id, aisle_id = _seed(sql_client)
    record = _build_previewed_import(
        inventory_id=inv_id,
        aisle_id=aisle_id,
        n_rows=12,
        with_labels=False,
        include_nullables=True,
    )
    SqlLocalCsvImportRepository(sql_client).save(record)
    writer = SqlLocalCsvInventoryResultWriter(sql_client)
    applied = writer.apply_import(
        record=record,
        rows_to_import=record.rows,
        confirmed_by_user_id=None,
        image_evidence_by_import_row_id={},
    )
    assert len(applied) == 12
    assert all(r.source_asset_id is None for r in applied)
    assert all(r.label_id is None for r in applied)
    assert _count_productive(sql_client, inv_id) == 12


def test_find_confirmed_secondary_keys_candidate_scoped(sql_client) -> None:
    from dataclasses import replace

    inv_id, aisle_id = _seed(sql_client)
    csv_repo = SqlLocalCsvImportRepository(sql_client)
    writer = SqlLocalCsvInventoryResultWriter(sql_client)

    first = _build_previewed_import(inventory_id=inv_id, aisle_id=aisle_id, n_rows=5)
    csv_repo.save(first)
    writer.apply_import(
        record=first, rows_to_import=first.rows, confirmed_by_user_id=None
    )
    confirmed = replace(
        first,
        status="CONFIRMED",
        confirmed_at=datetime.now(timezone.utc),
        rows=tuple(replace(r, status="IMPORTED") for r in first.rows),
    )
    csv_repo.save(confirmed)

    second = _build_previewed_import(inventory_id=inv_id, aisle_id=aisle_id, n_rows=3)
    overlap_label = first.rows[0].label_id
    assert overlap_label
    overlapping = replace(
        second.rows[0],
        capture_session_id=first.rows[0].capture_session_id,
        label_id=overlap_label,
    )
    second = replace(second, rows=(overlapping, *second.rows[1:]))
    csv_repo.save(second)

    keys = {r.secondary_key for r in second.rows}
    found = csv_repo.find_confirmed_secondary_keys(keys)
    assert first.rows[0].secondary_key in found
    assert len(found) == 1
