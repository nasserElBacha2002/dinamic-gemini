"""
Stage 4 — Write hybrid report artifacts (JSON and CSV).

Epic 3.1.C: write_report_csv writes entity-based CSV with traceability columns
(source_image_id, traceability_status, traceability_warning). CSV is always generated
when the reporting stage runs (no optional flag); see ReportingStage.

Epic 3.1.D: Additive column review_display_label — single display label for review/export
(derived via derive_review_display_label: internal_code else position_barcode). Intentional
contract evolution for Epic D; backward compatible (entities without the field get derived value).

Epic 5 — CSV contract evolution: Additive column source_image_original_filename.
- New column is intentional schema evolution; not a breaking change.
- Populated when the report entity has source_image_original_filename (photos jobs, Epic 5+ reports).
- Empty cell when: no source image, source_image_id not in map, video jobs, or legacy reports
  that do not contain the field. Missing values are expected and valid.
"""

import csv
import json
from pathlib import Path
from typing import Any, Dict, List

from src.domain.pallet import Pallet
from src.reporting.display_label import derive_review_display_label


def write_json(path: Path, data: Dict[str, Any]) -> None:
    """Write a dict as UTF-8 JSON to path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def write_report_csv(path: Path, report: Dict[str, Any]) -> None:
    """Write report entities to CSV with traceability (Epic 3.1.C), review_display_label (Epic 3.1.D), and source_image_original_filename (Epic 5).

    Columns: entity_uid, pallet_id, entity_type, count_status, final_quantity,
    internal_code, confidence, source_image_id, traceability_status, traceability_warning,
    source_image_original_filename, review_display_label.

    Epic 5: source_image_original_filename is an additive column. Empty string is written when
    the entity dict has no key or value (video jobs, legacy reports, or source_image_id not in map).
    """
    entities = report.get("entities") or []
    if not entities:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow([
                "entity_uid", "pallet_id", "entity_type", "count_status", "final_quantity",
                "internal_code", "confidence", "source_image_id", "traceability_status", "traceability_warning",
                "source_image_original_filename", "review_display_label",
            ])
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "entity_uid", "pallet_id", "entity_type", "count_status", "final_quantity",
            "internal_code", "confidence", "source_image_id", "traceability_status", "traceability_warning",
            "source_image_original_filename", "review_display_label",
        ])
        for e in entities:
            rdl = derive_review_display_label(e.get("internal_code"), e.get("position_barcode"))
            w.writerow([
                e.get("entity_uid") or "",
                e.get("pallet_id") or "",
                e.get("entity_type") or "",
                e.get("count_status") or "",
                e.get("final_quantity") if e.get("final_quantity") is not None else "",
                e.get("internal_code") or "",
                e.get("confidence") if e.get("confidence") is not None else "",
                e.get("source_image_id") or "",
                e.get("traceability_status") or "",
                e.get("traceability_warning") or "",
                e.get("source_image_original_filename") or "",
                rdl if rdl is not None else "",
            ])


def write_csv(path: Path, pallets: List[Pallet]) -> None:
    """Write pallets to a CSV with columns: pallet_id, internal_code, final_quantity, source, confidence, fallback_used.

    Uses comma (,) as delimiter by default. Note: some locales (e.g. Excel in certain regions)
    use semicolon or tab; this output is standard comma-separated for machine parsing.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["pallet_id", "internal_code", "final_quantity", "source", "confidence", "fallback_used"])
        for p in pallets:
            w.writerow([
                p.pallet_id,
                p.internal_code if p.internal_code is not None else "",
                p.final_quantity if p.final_quantity is not None else "",
                p.source,
                p.confidence,
                p.fallback_used,
            ])
