"""SQL Server benchmarks: row-by-row vs executemany (± fast_executemany)."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus
from src.domain.local_csv_import.entities import LocalCsvImport, LocalCsvImportRow
from src.domain.local_csv_import.sources import INGESTION_SOURCE_LOCAL_CSV_IMPORT
from src.infrastructure.database.sql_batch import (
    EXECUTEMANY_PRODUCTIVE_PARAM_SET_CHUNK,
    cursor_executemany,
)
from src.infrastructure.database.sql_transaction import sql_repository_cursor
from src.infrastructure.repositories.local_csv_inventory_result_writer import (
    _PRODUCTIVE_INSERT_SQL,
    SqlLocalCsvInventoryResultWriter,
    _productive_insert_params,
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


@dataclass(frozen=True)
class BenchResult:
    mode: str
    n_rows: int
    duration_ms: float
    rows_persisted: int
    python_execute_calls: int
    python_executemany_calls: int


def _seed(client) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    inv_id = f"inv-bench-{uuid.uuid4().hex[:10]}"
    aisle_id = f"aisle-bench-{uuid.uuid4().hex[:10]}"
    SqlInventoryRepository(client).save(
        Inventory(
            id=inv_id,
            name="executemany bench",
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
            code=f"E-{uuid.uuid4().hex[:6]}",
            status=AisleStatus.CREATED,
            created_at=now,
            updated_at=now,
        )
    )
    return inv_id, aisle_id


def _build_record(
    *,
    inventory_id: str,
    aisle_id: str,
    n_rows: int,
    with_nullables: bool,
) -> LocalCsvImport:
    now = datetime.now(timezone.utc)
    import_id = str(uuid.uuid4())
    rows: list[LocalCsvImportRow] = []
    for i in range(n_rows):
        rows.append(
            LocalCsvImportRow(
                id=str(uuid.uuid4()),
                import_id=import_id,
                row_number=i + 1,
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                capture_session_id=f"sess-{import_id[:8]}",
                capture_photo_id=f"photo-{i}",
                client_file_id=f"file-{i}",
                capture_order=i + 1,
                captured_at=now,
                position_code="" if with_nullables and i % 2 == 0 else f"P-{i}",
                internal_code=f"SKU-{i}",
                quantity=None if with_nullables and i % 3 == 0 else 1,
                quantity_status="PRESENT",
                detection_status="DETECTED",
                detection_source="LOCAL_CODE_SCAN",
                ingestion_source=INGESTION_SOURCE_LOCAL_CSV_IMPORT,
                requires_review=False,
                error_code=None,
                notes=None,
                status="PREVIEW_VALID",
                label_id=None if with_nullables and i % 2 == 1 else f"L{uuid.uuid4().hex[:8].upper()}",
                position_label_id=None,
                position_payload_raw=None,
            )
        )
    return LocalCsvImport(
        id=import_id,
        export_id=f"exp-{uuid.uuid4().hex[:12]}",
        schema_version="1",
        inventory_id=inventory_id,
        device_id="bench",
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


def _count(client, inventory_id: str) -> int:
    with client.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS c FROM local_csv_productive_results WHERE inventory_id = ?",
            (inventory_id,),
        )
        return int(cur.fetchone().c)


def _row_by_row_insert(cur, params_list: list[tuple[object, ...]]) -> tuple[int, int]:
    executes = 0
    for params in params_list:
        cur.execute(_PRODUCTIVE_INSERT_SQL, params)
        executes += 1
    return executes, 0


def _run_mode(
    sql_client,
    *,
    mode: str,
    n_rows: int,
    use_fast: bool,
    with_nullables: bool,
) -> BenchResult:
    from src.domain.local_csv_import.entities import LocalCsvProductiveResult
    from src.infrastructure.database.sql_batch import chunked

    inv_id, aisle_id = _seed(sql_client)
    record = _build_record(
        inventory_id=inv_id,
        aisle_id=aisle_id,
        n_rows=n_rows,
        with_nullables=with_nullables,
    )
    SqlLocalCsvImportRepository(sql_client).save(record)
    now = datetime.now(timezone.utc)

    built = []
    for row in record.rows:
        built.append(
            LocalCsvProductiveResult(
                id=str(uuid.uuid4()),
                inventory_id=record.inventory_id,
                aisle_id=row.aisle_id,
                import_id=record.id,
                import_row_id=row.id,
                capture_session_id=row.capture_session_id,
                capture_photo_id=row.capture_photo_id,
                client_file_id=row.client_file_id,
                capture_order=row.capture_order,
                position_code=row.position_code or None,
                internal_code=row.internal_code,
                quantity=row.quantity,
                quantity_status=row.quantity_status,
                detection_status=row.detection_status,
                detection_source=row.detection_source,
                ingestion_source=INGESTION_SOURCE_LOCAL_CSV_IMPORT,
                requires_review=bool(row.requires_review) or not (row.position_code or "").strip(),
                has_image_evidence=False,
                source_asset_id=None,
                confirmed_by_user_id="bench",
                created_at=now,
                updated_at=now,
                label_id=(row.label_id or "").strip().upper() or None,
                position_label_id=None,
                position_payload_raw=None,
            )
        )
    params_list = [_productive_insert_params(r) for r in built]

    execute_calls = 0
    executemany_calls = 0
    started = time.perf_counter()
    with sql_client.begin_transaction() as txn:
        with sql_repository_cursor(sql_client, connection=txn.connection) as cur:
            if mode == "row_by_row":
                execute_calls, executemany_calls = _row_by_row_insert(cur, params_list)
            elif mode == "executemany":
                for chunk in chunked(params_list, EXECUTEMANY_PRODUCTIVE_PARAM_SET_CHUNK):
                    cursor_executemany(
                        cur,
                        _PRODUCTIVE_INSERT_SQL,
                        chunk,
                        operation=f"bench.{mode}",
                        use_fast_executemany=use_fast,
                    )
                    executemany_calls += 1
            else:
                raise AssertionError(mode)
        txn.commit()
    duration_ms = (time.perf_counter() - started) * 1000.0
    persisted = _count(sql_client, inv_id)
    assert persisted == n_rows
    return BenchResult(
        mode=f"{mode}:fast={use_fast}",
        n_rows=n_rows,
        duration_ms=duration_ms,
        rows_persisted=persisted,
        python_execute_calls=execute_calls,
        python_executemany_calls=executemany_calls,
    )


@pytest.mark.parametrize("n_rows", [10, 100, 1000])
def test_executemany_wall_clock_vs_row_by_row(sql_client, n_rows: int) -> None:
    """Measure wall-clock; report Python cursor calls — do NOT claim network RPCs."""
    baseline = _run_mode(
        sql_client, mode="row_by_row", n_rows=n_rows, use_fast=False, with_nullables=True
    )
    em_plain = _run_mode(
        sql_client, mode="executemany", n_rows=n_rows, use_fast=False, with_nullables=True
    )

    # Cursor-call reduction is structural for executemany path.
    assert baseline.python_execute_calls == n_rows
    assert em_plain.python_execute_calls == 0
    assert em_plain.python_executemany_calls >= 1

    # Wall-clock: executemany should not be dramatically worse; allow driver noise.
    # We record both durations for the audit report; assert only correctness + call shape.
    assert baseline.rows_persisted == n_rows
    assert em_plain.rows_persisted == n_rows

    # Optional fast path — only if driver supports the attribute.
    with sql_client.cursor() as probe:
        supports_fast = hasattr(probe, "fast_executemany")
    if supports_fast:
        em_fast = _run_mode(
            sql_client, mode="executemany", n_rows=n_rows, use_fast=True, with_nullables=True
        )
        assert em_fast.rows_persisted == n_rows
        # Publish timings via assertion message / pytest print for audit capture.
        print(  # noqa: T201 — intentional benchmark evidence
            f"BENCH n={n_rows} "
            f"row_by_row_ms={baseline.duration_ms:.1f} "
            f"executemany_ms={em_plain.duration_ms:.1f} "
            f"fast_executemany_ms={em_fast.duration_ms:.1f} "
            f"python_execute_calls_baseline={baseline.python_execute_calls} "
            f"python_executemany_calls={em_plain.python_executemany_calls}"
        )
    else:
        print(  # noqa: T201
            f"BENCH n={n_rows} "
            f"row_by_row_ms={baseline.duration_ms:.1f} "
            f"executemany_ms={em_plain.duration_ms:.1f} "
            f"fast_executemany=unsupported "
            f"python_execute_calls_baseline={baseline.python_execute_calls} "
            f"python_executemany_calls={em_plain.python_executemany_calls}"
        )


def test_fast_executemany_nullable_datetime_rollback(sql_client) -> None:
    """If fast_executemany works, NULL + datetime inserts roll back atomically."""
    with sql_client.cursor() as probe:
        if not hasattr(probe, "fast_executemany"):
            pytest.skip("pyodbc cursor has no fast_executemany")

    inv_id, aisle_id = _seed(sql_client)
    record = _build_record(
        inventory_id=inv_id, aisle_id=aisle_id, n_rows=25, with_nullables=True
    )
    SqlLocalCsvImportRepository(sql_client).save(record)
    writer = SqlLocalCsvInventoryResultWriter(sql_client)
    now = datetime.now(timezone.utc)
    from src.domain.local_csv_import.entities import LocalCsvProductiveResult

    built = []
    for row in record.rows:
        built.append(
            LocalCsvProductiveResult(
                id=str(uuid.uuid4()),
                inventory_id=record.inventory_id,
                aisle_id=row.aisle_id,
                import_id=record.id,
                import_row_id=row.id,
                capture_session_id=row.capture_session_id,
                capture_photo_id=row.capture_photo_id,
                client_file_id=row.client_file_id,
                capture_order=row.capture_order,
                position_code=row.position_code or None,
                internal_code=row.internal_code,
                quantity=row.quantity,
                quantity_status=row.quantity_status,
                detection_status=row.detection_status,
                detection_source=row.detection_source,
                ingestion_source=INGESTION_SOURCE_LOCAL_CSV_IMPORT,
                requires_review=False,
                has_image_evidence=False,
                source_asset_id=None,
                confirmed_by_user_id=None,
                created_at=now,
                updated_at=now,
                label_id=(row.label_id or "").strip().upper() or None,
            )
        )
    params_list = [_productive_insert_params(r) for r in built]

    class BoomError(Exception):
        pass

    try:
        with sql_client.begin_transaction() as txn:
            with sql_repository_cursor(sql_client, connection=txn.connection) as cur:
                cursor_executemany(
                    cur,
                    _PRODUCTIVE_INSERT_SQL,
                    params_list,
                    operation="bench.fast_rollback",
                    use_fast_executemany=True,
                )
                raise BoomError("rollback after fast_executemany")
    except BoomError:
        pass

    assert _count(sql_client, inv_id) == 0
    # Production path keeps fast_executemany=False; this only proves capability.
    _ = writer
