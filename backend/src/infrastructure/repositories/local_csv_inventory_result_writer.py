"""In-memory / SQL productive writers for local CSV and package confirm."""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone

from src.domain.local_csv_import.entities import (
    LocalCsvImport,
    LocalCsvImportRow,
    LocalCsvProductiveResult,
    local_csv_row_secondary_key,
)
from src.domain.local_csv_import.sources import INGESTION_SOURCE_LOCAL_CSV_IMPORT


class MemoryLocalCsvInventoryResultWriter:
    def __init__(self) -> None:
        self._by_id: dict[str, LocalCsvProductiveResult] = {}
        self._lock = threading.Lock()

    def apply_import(
        self,
        *,
        record: LocalCsvImport,
        rows_to_import: tuple[LocalCsvImportRow, ...],
        confirmed_by_user_id: str | None,
        image_evidence_by_import_row_id: dict[str, str] | None = None,
    ) -> tuple[LocalCsvProductiveResult, ...]:
        evidence = image_evidence_by_import_row_id or {}
        now = datetime.now(timezone.utc)
        applied: list[LocalCsvProductiveResult] = []
        with self._lock:
            for row in rows_to_import:
                row_key = row.secondary_key
                existing = next(
                    (
                        r
                        for r in self._by_id.values()
                        if r.import_row_id == row.id
                        or local_csv_row_secondary_key(
                            capture_session_id=r.capture_session_id,
                            capture_photo_id=r.capture_photo_id,
                            label_id=r.label_id,
                            detection_source=r.detection_source,
                        )
                        == row_key
                    ),
                    None,
                )
                if existing is not None:
                    applied.append(existing)
                    continue
                requires_review = bool(row.requires_review) or not (row.position_code or "").strip()
                source_asset_id = evidence.get(row.id)
                result = LocalCsvProductiveResult(
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
                    requires_review=requires_review,
                    has_image_evidence=source_asset_id is not None,
                    source_asset_id=source_asset_id,
                    confirmed_by_user_id=confirmed_by_user_id,
                    created_at=now,
                    updated_at=now,
                    label_id=(row.label_id or "").strip().upper() or None,
                    position_label_id=(row.position_label_id or "").strip() or None,
                    position_payload_raw=(row.position_payload_raw or "").strip() or None,
                )
                self._by_id[result.id] = result
                applied.append(result)
        return tuple(applied)

    def list_for_inventory(self, inventory_id: str) -> tuple[LocalCsvProductiveResult, ...]:
        return tuple(r for r in self._by_id.values() if r.inventory_id == inventory_id)


class SqlLocalCsvInventoryResultWriter:
    """SQL Server writer — inserts productive rows inside the caller's transaction cursor when provided."""

    def __init__(self, client: object) -> None:
        self._client = client

    def apply_import(
        self,
        *,
        record: LocalCsvImport,
        rows_to_import: tuple[LocalCsvImportRow, ...],
        confirmed_by_user_id: str | None,
        cursor: object | None = None,
        image_evidence_by_import_row_id: dict[str, str] | None = None,
    ) -> tuple[LocalCsvProductiveResult, ...]:
        from src.infrastructure.database.sql_transaction import sql_repository_cursor

        evidence = image_evidence_by_import_row_id or {}
        now = datetime.now(timezone.utc)
        applied: list[LocalCsvProductiveResult] = []

        def _run(cur: object) -> None:
            for row in rows_to_import:
                cur.execute(  # type: ignore[attr-defined]
                    "SELECT id FROM local_csv_productive_results WHERE import_row_id = ?",
                    (row.id,),
                )
                existing = cur.fetchone()  # type: ignore[attr-defined]
                if existing:
                    cur.execute(  # type: ignore[attr-defined]
                        "SELECT * FROM local_csv_productive_results WHERE id = ?",
                        (str(existing.id),),
                    )
                    db_row = cur.fetchone()  # type: ignore[attr-defined]
                    applied.append(_productive_from_db(db_row))
                    continue
                requires_review = bool(row.requires_review) or not (row.position_code or "").strip()
                source_asset_id = evidence.get(row.id)
                result_id = str(uuid.uuid4())
                result = LocalCsvProductiveResult(
                    id=result_id,
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
                    requires_review=requires_review,
                    has_image_evidence=source_asset_id is not None,
                    source_asset_id=source_asset_id,
                    confirmed_by_user_id=confirmed_by_user_id,
                    created_at=now,
                    updated_at=now,
                    label_id=(row.label_id or "").strip().upper() or None,
                    position_label_id=(row.position_label_id or "").strip() or None,
                    position_payload_raw=(row.position_payload_raw or "").strip() or None,
                )
                cur.execute(  # type: ignore[attr-defined]
                    "INSERT INTO local_csv_productive_results "
                    "(id, inventory_id, aisle_id, import_id, import_row_id, capture_session_id, "
                    "capture_photo_id, client_file_id, capture_order, position_code, internal_code, "
                    "quantity, quantity_status, detection_status, detection_source, ingestion_source, "
                    "requires_review, has_image_evidence, source_asset_id, confirmed_by_user_id, "
                    "created_at, updated_at, label_id, position_label_id, position_payload_raw) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        result.id,
                        result.inventory_id,
                        result.aisle_id,
                        result.import_id,
                        result.import_row_id,
                        result.capture_session_id,
                        result.capture_photo_id,
                        result.client_file_id,
                        result.capture_order,
                        result.position_code,
                        result.internal_code,
                        result.quantity,
                        result.quantity_status,
                        result.detection_status,
                        result.detection_source,
                        result.ingestion_source,
                        1 if result.requires_review else 0,
                        1 if result.has_image_evidence else 0,
                        result.source_asset_id,
                        result.confirmed_by_user_id,
                        result.created_at,
                        result.updated_at,
                        result.label_id,
                        result.position_label_id,
                        result.position_payload_raw,
                    ),
                )
                applied.append(result)

        if cursor is not None:
            _run(cursor)
        else:
            with sql_repository_cursor(self._client) as cur:  # type: ignore[arg-type]
                _run(cur)
        return tuple(applied)

    def list_for_inventory(self, inventory_id: str) -> tuple[LocalCsvProductiveResult, ...]:
        with self._client.cursor() as cur:  # type: ignore[attr-defined]
            cur.execute(
                "SELECT * FROM local_csv_productive_results WHERE inventory_id = ? "
                "ORDER BY created_at, id",
                (inventory_id,),
            )
            return tuple(_productive_from_db(row) for row in cur.fetchall())


def _productive_from_db(row: object) -> LocalCsvProductiveResult:
    from datetime import timezone as tz

    def _utc(value: object) -> datetime:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=tz.utc)
        return datetime.now(tz.utc)

    source_asset_id = getattr(row, "source_asset_id", None)
    return LocalCsvProductiveResult(
        id=str(getattr(row, "id")),
        inventory_id=str(getattr(row, "inventory_id")),
        aisle_id=str(getattr(row, "aisle_id")),
        import_id=str(getattr(row, "import_id")),
        import_row_id=str(getattr(row, "import_row_id")),
        capture_session_id=str(getattr(row, "capture_session_id")),
        capture_photo_id=str(getattr(row, "capture_photo_id")),
        client_file_id=str(getattr(row, "client_file_id")),
        capture_order=(
            int(getattr(row, "capture_order"))
            if getattr(row, "capture_order", None) is not None
            else None
        ),
        position_code=(
            str(getattr(row, "position_code"))
            if getattr(row, "position_code", None) is not None
            else None
        ),
        internal_code=(
            str(getattr(row, "internal_code"))
            if getattr(row, "internal_code", None) is not None
            else None
        ),
        quantity=(
            int(getattr(row, "quantity")) if getattr(row, "quantity", None) is not None else None
        ),
        quantity_status=str(getattr(row, "quantity_status")),
        detection_status=str(getattr(row, "detection_status")),
        detection_source=str(getattr(row, "detection_source")),
        ingestion_source=str(getattr(row, "ingestion_source")),
        requires_review=bool(getattr(row, "requires_review")),
        has_image_evidence=bool(getattr(row, "has_image_evidence")),
        source_asset_id=str(source_asset_id) if source_asset_id is not None else None,
        confirmed_by_user_id=(
            str(getattr(row, "confirmed_by_user_id"))
            if getattr(row, "confirmed_by_user_id", None) is not None
            else None
        ),
        created_at=_utc(getattr(row, "created_at")),
        updated_at=_utc(getattr(row, "updated_at")),
        label_id=(
            str(getattr(row, "label_id")).strip().upper() or None
            if getattr(row, "label_id", None) is not None
            else None
        ),
        position_label_id=(
            str(getattr(row, "position_label_id")).strip() or None
            if getattr(row, "position_label_id", None) is not None
            else None
        ),
        position_payload_raw=(
            str(getattr(row, "position_payload_raw")).strip() or None
            if getattr(row, "position_payload_raw", None) is not None
            else None
        ),
    )
