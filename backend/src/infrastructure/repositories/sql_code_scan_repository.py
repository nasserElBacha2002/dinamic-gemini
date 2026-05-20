"""SQL Server implementation of CodeScanRepository."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from src.application.ports.code_scan_repository import CodeScanRepository, CodeScanSummaryItem
from src.application.services.code_scan_summary import detection_counts_toward_summary
from src.application.services.code_scan_summary_match import aggregate_group_match
from src.database.sqlserver import SqlServerClient
from src.domain.code_scans.bounding_box import parse_bounding_box
from src.domain.code_scans.entities import (
    CodeScanDetection,
    CodeScanDetectionStatus,
    CodeScanRun,
    CodeScanRunStatus,
    CodeType,
)
from src.infrastructure.repositories.db_row_text import normalize_db_str, optional_nonempty_db_str

logger = logging.getLogger(__name__)


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _parse_metadata(raw: object) -> dict[str, Any] | None:
    if raw is None:
        return None
    text = raw.strip() if isinstance(raw, str) else str(raw).strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Invalid metadata_json in code scan row")
        return None
    return parsed if isinstance(parsed, dict) else None


def _enum_run_status(raw: object) -> CodeScanRunStatus:
    text = normalize_db_str(raw) or CodeScanRunStatus.FAILED.value
    try:
        return CodeScanRunStatus(text)
    except ValueError:
        return CodeScanRunStatus.FAILED


def _enum_detection_status(raw: object) -> CodeScanDetectionStatus:
    text = normalize_db_str(raw) or CodeScanDetectionStatus.ERROR.value
    try:
        return CodeScanDetectionStatus(text)
    except ValueError:
        return CodeScanDetectionStatus.ERROR


def _enum_code_type(raw: object) -> CodeType:
    text = normalize_db_str(raw) or CodeType.UNKNOWN.value
    try:
        return CodeType(text)
    except ValueError:
        return CodeType.UNKNOWN


def _row_to_run(row) -> CodeScanRun:
    started = _ensure_utc(getattr(row, "started_at", None))
    if started is None:
        raise ValueError("aisle_code_scan_runs row missing started_at")
    return CodeScanRun(
        id=normalize_db_str(getattr(row, "id", None)),
        inventory_id=normalize_db_str(getattr(row, "inventory_id", None)),
        aisle_id=normalize_db_str(getattr(row, "aisle_id", None)),
        status=_enum_run_status(getattr(row, "status", None)),
        total_assets=int(getattr(row, "total_assets", 0) or 0),
        processed_assets=int(getattr(row, "processed_assets", 0) or 0),
        failed_assets=int(getattr(row, "failed_assets", 0) or 0),
        total_codes_found=int(getattr(row, "total_codes_found", 0) or 0),
        total_qr_found=int(getattr(row, "total_qr_found", 0) or 0),
        total_barcodes_found=int(getattr(row, "total_barcodes_found", 0) or 0),
        started_at=started,
        finished_at=_ensure_utc(getattr(row, "finished_at", None)),
        scanner_engine=normalize_db_str(getattr(row, "scanner_engine", None)) or "noop",
        is_latest=bool(getattr(row, "is_latest", False)),
        error_message=optional_nonempty_db_str(getattr(row, "error_message", None)),
        created_by=optional_nonempty_db_str(getattr(row, "created_by", None)),
        metadata_json=_parse_metadata(getattr(row, "metadata_json", None)),
    )


def _row_to_detection(row) -> CodeScanDetection:
    created = _ensure_utc(getattr(row, "created_at", None))
    if created is None:
        raise ValueError("aisle_code_scan_detections row missing created_at")
    return CodeScanDetection(
        id=normalize_db_str(getattr(row, "id", None)),
        run_id=normalize_db_str(getattr(row, "run_id", None)),
        inventory_id=normalize_db_str(getattr(row, "inventory_id", None)),
        aisle_id=normalize_db_str(getattr(row, "aisle_id", None)),
        asset_id=normalize_db_str(getattr(row, "asset_id", None)),
        code_type=_enum_code_type(getattr(row, "code_type", None)),
        code_value=normalize_db_str(getattr(row, "code_value", None)),
        normalized_code_value=normalize_db_str(getattr(row, "normalized_code_value", None)),
        detection_status=_enum_detection_status(getattr(row, "detection_status", None)),
        scanner_engine=normalize_db_str(getattr(row, "scanner_engine", None)) or "noop",
        created_at=created,
        bounding_box_json=parse_bounding_box(getattr(row, "bounding_box_json", None)),
        confidence=getattr(row, "confidence", None),
        metadata_json=_parse_metadata(getattr(row, "metadata_json", None)),
        matched_position_id=optional_nonempty_db_str(getattr(row, "matched_position_id", None)),
        match_status=optional_nonempty_db_str(getattr(row, "match_status", None)),
        match_type=optional_nonempty_db_str(getattr(row, "match_type", None)),
        match_confidence=getattr(row, "match_confidence", None),
        match_metadata_json=_parse_metadata(getattr(row, "match_metadata_json", None)),
        matched_at=_ensure_utc(getattr(row, "matched_at", None)),
    )


class SqlCodeScanRepository(CodeScanRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def replace_latest_run(self, run: CodeScanRun) -> None:
        if not run.is_latest:
            raise ValueError("replace_latest_run requires run.is_latest=True")
        started = _ensure_utc(run.started_at)
        finished = _ensure_utc(run.finished_at)
        meta = json.dumps(run.metadata_json, ensure_ascii=False) if run.metadata_json else None
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE aisle_code_scan_runs
                SET is_latest = 0
                WHERE inventory_id = ? AND aisle_id = ? AND is_latest = 1
                """,
                (run.inventory_id, run.aisle_id),
            )
            cur.execute(
                """
                INSERT INTO aisle_code_scan_runs (
                    id, inventory_id, aisle_id, status, total_assets, processed_assets,
                    failed_assets, total_codes_found, total_qr_found, total_barcodes_found,
                    started_at, finished_at, error_message, scanner_engine, is_latest,
                    created_by, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.id,
                    run.inventory_id,
                    run.aisle_id,
                    run.status.value,
                    run.total_assets,
                    run.processed_assets,
                    run.failed_assets,
                    run.total_codes_found,
                    run.total_qr_found,
                    run.total_barcodes_found,
                    started,
                    finished,
                    run.error_message,
                    run.scanner_engine,
                    1,
                    run.created_by,
                    meta,
                ),
            )

    def save_run(self, run: CodeScanRun) -> None:
        started = _ensure_utc(run.started_at)
        finished = _ensure_utc(run.finished_at)
        meta = json.dumps(run.metadata_json, ensure_ascii=False) if run.metadata_json else None
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE aisle_code_scan_runs
                SET status = ?, total_assets = ?, processed_assets = ?, failed_assets = ?,
                    total_codes_found = ?, total_qr_found = ?, total_barcodes_found = ?,
                    finished_at = ?, error_message = ?, scanner_engine = ?, is_latest = ?,
                    metadata_json = ?
                WHERE id = ?
                """,
                (
                    run.status.value,
                    run.total_assets,
                    run.processed_assets,
                    run.failed_assets,
                    run.total_codes_found,
                    run.total_qr_found,
                    run.total_barcodes_found,
                    finished,
                    run.error_message,
                    run.scanner_engine,
                    1 if run.is_latest else 0,
                    meta,
                    run.id,
                ),
            )
            if cur.rowcount == 0:
                cur.execute(
                    """
                    INSERT INTO aisle_code_scan_runs (
                        id, inventory_id, aisle_id, status, total_assets, processed_assets,
                        failed_assets, total_codes_found, total_qr_found, total_barcodes_found,
                        started_at, finished_at, error_message, scanner_engine, is_latest,
                        created_by, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run.id,
                        run.inventory_id,
                        run.aisle_id,
                        run.status.value,
                        run.total_assets,
                        run.processed_assets,
                        run.failed_assets,
                        run.total_codes_found,
                        run.total_qr_found,
                        run.total_barcodes_found,
                        started,
                        finished,
                        run.error_message,
                        run.scanner_engine,
                        1 if run.is_latest else 0,
                        run.created_by,
                        meta,
                    ),
                )

    def save_detections(self, detections: Sequence[CodeScanDetection]) -> None:
        if not detections:
            return
        with self._client.cursor() as cur:
            for d in detections:
                bbox = json.dumps(d.bounding_box_json) if d.bounding_box_json else None
                meta = json.dumps(d.metadata_json, ensure_ascii=False) if d.metadata_json else None
                match_meta = (
                    json.dumps(d.match_metadata_json, ensure_ascii=False)
                    if d.match_metadata_json
                    else None
                )
                created = _ensure_utc(d.created_at)
                matched_at = _ensure_utc(d.matched_at)
                cur.execute(
                    """
                    INSERT INTO aisle_code_scan_detections (
                        id, run_id, inventory_id, aisle_id, asset_id, code_type, code_value,
                        normalized_code_value, bounding_box_json, confidence, detection_status,
                        scanner_engine, metadata_json, created_at,
                        matched_position_id, match_status, match_type, match_confidence,
                        match_metadata_json, matched_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        d.id,
                        d.run_id,
                        d.inventory_id,
                        d.aisle_id,
                        d.asset_id,
                        d.code_type.value,
                        d.code_value,
                        d.normalized_code_value,
                        bbox,
                        d.confidence,
                        d.detection_status.value,
                        d.scanner_engine,
                        meta,
                        created,
                        d.matched_position_id,
                        d.match_status,
                        d.match_type,
                        d.match_confidence,
                        match_meta,
                        matched_at,
                    ),
                )

    def update_detection_matches(self, detections: Sequence[CodeScanDetection]) -> None:
        if not detections:
            return
        with self._client.cursor() as cur:
            for d in detections:
                match_meta = (
                    json.dumps(d.match_metadata_json, ensure_ascii=False)
                    if d.match_metadata_json
                    else None
                )
                matched_at = _ensure_utc(d.matched_at)
                cur.execute(
                    """
                    UPDATE aisle_code_scan_detections
                    SET matched_position_id = ?, match_status = ?, match_type = ?,
                        match_confidence = ?, match_metadata_json = ?, matched_at = ?
                    WHERE id = ?
                    """,
                    (
                        d.matched_position_id,
                        d.match_status,
                        d.match_type,
                        d.match_confidence,
                        match_meta,
                        matched_at,
                        d.id,
                    ),
                )

    def get_latest_run_by_aisle(self, *, inventory_id: str, aisle_id: str) -> CodeScanRun | None:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT TOP 1 *
                FROM aisle_code_scan_runs
                WHERE inventory_id = ? AND aisle_id = ? AND is_latest = 1
                ORDER BY started_at DESC
                """,
                (inventory_id, aisle_id),
            )
            row = cur.fetchone()
        return _row_to_run(row) if row else None

    def list_detections_for_run(self, run_id: str) -> Sequence[CodeScanDetection]:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM aisle_code_scan_detections
                WHERE run_id = ?
                ORDER BY created_at ASC
                """,
                (run_id,),
            )
            rows = cur.fetchall()
        return [_row_to_detection(r) for r in rows]

    def list_latest_detections_by_aisle(
        self, *, inventory_id: str, aisle_id: str
    ) -> Sequence[CodeScanDetection]:
        run = self.get_latest_run_by_aisle(inventory_id=inventory_id, aisle_id=aisle_id)
        if run is None:
            return []
        return self.list_detections_for_run(run.id)

    def summarize_latest_detections_by_aisle(
        self, *, inventory_id: str, aisle_id: str
    ) -> Sequence[CodeScanSummaryItem]:
        detections = self.list_latest_detections_by_aisle(
            inventory_id=inventory_id, aisle_id=aisle_id
        )
        groups: dict[tuple[str, str], list[CodeScanDetection]] = defaultdict(list)
        for d in detections:
            if not detection_counts_toward_summary(d.detection_status):
                continue
            groups[(d.normalized_code_value, d.code_type.value)].append(d)

        items: list[CodeScanSummaryItem] = []
        for (norm, code_type), rows in groups.items():
            asset_ids = tuple(dict.fromkeys(r.asset_id for r in rows))
            first_seen = min(r.created_at for r in rows)
            match_status, matched_position_ids, match_types, match_status_counts = (
                aggregate_group_match(rows)
            )
            items.append(
                CodeScanSummaryItem(
                    code_value=rows[0].code_value,
                    normalized_code_value=norm,
                    code_type=code_type,
                    occurrences=len(rows),
                    asset_ids=asset_ids,
                    first_seen_at=first_seen,
                    match_status=match_status,
                    matched_position_ids=matched_position_ids,
                    match_types=match_types,
                    match_status_counts=match_status_counts,
                )
            )
        items.sort(key=lambda x: (x.normalized_code_value, x.code_type))
        return items
