"""Unit tests for set-based / batch persistence helpers (Phase 2)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.domain.local_csv_import.entities import LocalCsvImport, LocalCsvImportRow
from src.domain.local_csv_import.sources import INGESTION_SOURCE_LOCAL_CSV_IMPORT
from src.infrastructure.database.sql_batch import chunked, cursor_executemany
from src.infrastructure.repositories.local_csv_inventory_result_writer import (
    SqlLocalCsvInventoryResultWriter,
)


class CountingCursor:
    """Minimal cursor stub that counts Python cursor API calls (not network RPCs)."""

    def __init__(self) -> None:
        self.execute_calls = 0
        self.executemany_calls = 0
        self.executemany_row_counts: list[int] = []
        self._fetch_queue: list[list[Any]] = []
        self._existing: dict[str, Any] = {}

    def queue_fetchall(self, rows: list[Any]) -> None:
        self._fetch_queue.append(rows)

    def execute(self, sql: str, params: Any = None) -> None:
        self.execute_calls += 1
        _ = (sql, params)

    def executemany(self, sql: str, seq_of_params: Any) -> None:
        self.executemany_calls += 1
        self.executemany_row_counts.append(len(list(seq_of_params)))
        _ = sql

    def fetchone(self) -> Any:
        return None

    def fetchall(self) -> list[Any]:
        if self._fetch_queue:
            return self._fetch_queue.pop(0)
        return []

    @property
    def rowcount(self) -> int:
        return 0


def _row(n: int, *, import_id: str, inventory_id: str, aisle_id: str) -> LocalCsvImportRow:
    return LocalCsvImportRow(
        id=f"row-{n}",
        import_id=import_id,
        row_number=n,
        inventory_id=inventory_id,
        aisle_id=aisle_id,
        capture_session_id="sess-1",
        capture_photo_id=f"photo-{n}",
        client_file_id=f"file-{n}",
        capture_order=n,
        captured_at=datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc),
        position_code=f"P-{n}",
        internal_code=f"SKU-{n}",
        quantity=1,
        quantity_status="OK",
        detection_status="OK",
        detection_source="LOCAL_PRODUCT",
        ingestion_source=INGESTION_SOURCE_LOCAL_CSV_IMPORT,
        requires_review=False,
        error_code=None,
        notes=None,
        status="PREVIEW_VALID",
        validation_errors=(),
        validation_warnings=(),
        productive_result_id=None,
        label_id=f"LBL{n:04d}",
        position_label_id=None,
        position_payload_raw=None,
    )


def _record(n_rows: int) -> tuple[LocalCsvImport, tuple[LocalCsvImportRow, ...]]:
    inventory_id = "inv-1"
    aisle_id = "aisle-1"
    import_id = "imp-1"
    rows = tuple(_row(i, import_id=import_id, inventory_id=inventory_id, aisle_id=aisle_id) for i in range(n_rows))
    record = LocalCsvImport(
        id=import_id,
        export_id="exp-1",
        schema_version="1",
        inventory_id=inventory_id,
        device_id="dev-1",
        exported_at=datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc),
        status="PREVIEWED",
        content_hash="hash",
        total_rows=n_rows,
        valid_rows=n_rows,
        rejected_rows=0,
        duplicate_rows=0,
        conflict_policy="SKIP",
        confirmed_at=None,
        confirmed_by_user_id=None,
        created_at=datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc),
        rows=rows,
    )
    return record, rows


def test_chunked_splits_evenly() -> None:
    assert list(chunked([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]


def test_cursor_executemany_counts_one_batch() -> None:
    cur = CountingCursor()
    cursor_executemany(
        cur,
        "INSERT INTO t VALUES (?)",
        [(1,), (2,), (3,)],
        operation="test.insert",
    )
    assert cur.executemany_calls == 1
    assert cur.executemany_row_counts == [3]
    assert cur.execute_calls == 0


def test_apply_import_uses_batched_select_and_executemany_for_100_rows() -> None:
    """Before: ~200 explicit cursor.execute calls (SELECT+INSERT per row).

    After: 1 IN-select + ceil(100/80)=2 executemany *calls* (not claimed network RPCs).
    """
    record, rows = _record(100)
    cur = CountingCursor()
    cur.queue_fetchall([])  # no existing productive rows
    writer = SqlLocalCsvInventoryResultWriter(client=object())
    applied = writer.apply_import(
        record=record,
        rows_to_import=rows,
        confirmed_by_user_id="user-1",
        cursor=cur,
    )
    assert len(applied) == 100
    assert cur.execute_calls == 1  # SELECT ... WHERE import_row_id IN (...)
    assert cur.executemany_calls == 2
    assert cur.executemany_row_counts == [80, 20]


def test_apply_import_chunks_inserts_above_chunk_size() -> None:
    # PRODUCTIVE_INSERT_CHUNK_SIZE = 80 → 100 rows = 2 batches
    record, rows = _record(100)
    # Force smaller effective path by using 160 rows → 2 chunks of 80
    record160, rows160 = _record(160)
    cur = CountingCursor()
    cur.queue_fetchall([])
    writer = SqlLocalCsvInventoryResultWriter(client=object())
    applied = writer.apply_import(
        record=record160,
        rows_to_import=rows160,
        confirmed_by_user_id=None,
        cursor=cur,
    )
    assert len(applied) == 160
    assert cur.execute_calls == 1
    assert cur.executemany_calls == 2
    assert cur.executemany_row_counts == [80, 80]
    _ = record
    _ = rows
