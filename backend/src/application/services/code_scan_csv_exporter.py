"""CSV builders for aisle code scan exports (Phase 6B)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from src.application.ports.code_scan_repository import CodeScanSummaryItem
from src.application.services.csv_inventory_exporter import CsvInventoryExporter
from src.domain.code_scans.entities import CodeScanDetection, CodeScanRun
from src.domain.code_scans.matching import CodeScanMatchStatus

DETECTIONS_CSV_FIELDS: tuple[str, ...] = (
    "inventory_id",
    "aisle_id",
    "run_id",
    "detection_id",
    "asset_id",
    "code_type",
    "code_value",
    "normalized_code_value",
    "detection_status",
    "match_status",
    "match_type",
    "matched_position_id",
    "scanner_engine",
    "created_at",
    "matched_at",
    "confidence",
)

UNMATCHED_CSV_FIELDS: tuple[str, ...] = (
    "inventory_id",
    "aisle_id",
    "run_id",
    "detection_id",
    "asset_id",
    "code_type",
    "code_value",
    "normalized_code_value",
    "scanner_engine",
    "created_at",
    "reason",
)

SUMMARY_CSV_FIELDS: tuple[str, ...] = (
    "inventory_id",
    "aisle_id",
    "run_id",
    "code_type",
    "code_value",
    "normalized_code_value",
    "occurrences",
    "asset_count",
    "asset_ids",
    "match_status",
    "matched_position_ids",
    "match_types",
    "first_seen_at",
)

UNMATCHED_EXPORT_STATUSES = frozenset(
    {
        CodeScanMatchStatus.NO_MATCH.value,
        CodeScanMatchStatus.MULTIPLE_CANDIDATES.value,
        CodeScanMatchStatus.NOT_EVALUATED.value,
    }
)


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    s = str(value)
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s


def _row(cells: Mapping[str, Any]) -> dict[str, str]:
    return {k: _csv_cell(cells.get(k)) for k in cells}


def code_scan_export_filename(
    inventory_id: str,
    aisle_id: str,
    export_type: str,
) -> str:
    return f"code-scans-{inventory_id}-{aisle_id}-{export_type}.csv"


def build_detections_csv(
    *,
    run: CodeScanRun,
    detections: Sequence[CodeScanDetection],
) -> str:
    rows = [
        _row(
            {
                "inventory_id": run.inventory_id,
                "aisle_id": run.aisle_id,
                "run_id": run.id,
                "detection_id": d.id,
                "asset_id": d.asset_id,
                "code_type": d.code_type.value,
                "code_value": d.code_value,
                "normalized_code_value": d.normalized_code_value,
                "detection_status": d.detection_status.value,
                "match_status": d.match_status,
                "match_type": d.match_type,
                "matched_position_id": d.matched_position_id,
                "scanner_engine": d.scanner_engine,
                "created_at": d.created_at,
                "matched_at": d.matched_at,
                "confidence": d.confidence,
            }
        )
        for d in detections
    ]
    return CsvInventoryExporter.to_csv(rows, fieldnames=DETECTIONS_CSV_FIELDS)


def build_unmatched_csv(
    *,
    run: CodeScanRun,
    detections: Sequence[CodeScanDetection],
) -> str:
    rows: list[dict[str, str]] = []
    for d in detections:
        status = (d.match_status or CodeScanMatchStatus.NOT_EVALUATED.value).strip()
        if status not in UNMATCHED_EXPORT_STATUSES:
            continue
        rows.append(
            _row(
                {
                    "inventory_id": run.inventory_id,
                    "aisle_id": run.aisle_id,
                    "run_id": run.id,
                    "detection_id": d.id,
                    "asset_id": d.asset_id,
                    "code_type": d.code_type.value,
                    "code_value": d.code_value,
                    "normalized_code_value": d.normalized_code_value,
                    "scanner_engine": d.scanner_engine,
                    "created_at": d.created_at,
                    "reason": status,
                }
            )
        )
    return CsvInventoryExporter.to_csv(rows, fieldnames=UNMATCHED_CSV_FIELDS)


def build_summary_csv(
    *,
    run: CodeScanRun,
    items: Sequence[CodeScanSummaryItem],
) -> str:
    rows = [
        _row(
            {
                "inventory_id": run.inventory_id,
                "aisle_id": run.aisle_id,
                "run_id": run.id,
                "code_type": item.code_type,
                "code_value": item.code_value,
                "normalized_code_value": item.normalized_code_value,
                "occurrences": item.occurrences,
                "asset_count": len(item.asset_ids),
                "asset_ids": ";".join(item.asset_ids),
                "match_status": item.match_status,
                "matched_position_ids": ";".join(item.matched_position_ids),
                "match_types": ";".join(item.match_types),
                "first_seen_at": item.first_seen_at,
            }
        )
        for item in items
    ]
    return CsvInventoryExporter.to_csv(rows, fieldnames=SUMMARY_CSV_FIELDS)
