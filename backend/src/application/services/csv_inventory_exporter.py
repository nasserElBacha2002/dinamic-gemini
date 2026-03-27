"""Build CSV text for v3 inventory results export (single table, UTF-8).

Output is prefixed with a UTF-8 BOM so Excel recognizes UTF-8 and renders accented text correctly.
"""

from __future__ import annotations

import csv
import io
from typing import Any, Mapping, Sequence

UTF8_BOM = "\ufeff"

# Column order matches product/API spec (snake_case headers).
INVENTORY_RESULTS_CSV_FIELDS: tuple[str, ...] = (
    "inventory_id",
    "inventory_name",
    "aisle_id",
    "aisle_name",
    "aisle_sequence",
    "position_id",
    "position_code",
    "sku",
    "product_label",
    "barcode",
    "internal_code",
    "detected_quantity",
    "corrected_quantity",
    "final_quantity",
    "qty_source",
    "qty_inference_reason",
    "position_status",
    "traceability_status",
    "has_evidence",
    "source_image_id",
    "primary_evidence_id",
    "needs_review",
    "updated_at",
)


class CsvInventoryExporter:
    """Turn export rows (flat dicts) into CSV text with stable headers."""

    @staticmethod
    def to_csv(rows: Sequence[Mapping[str, Any]]) -> str:
        buf = io.StringIO(newline="")
        writer = csv.DictWriter(
            buf,
            fieldnames=list(INVENTORY_RESULTS_CSV_FIELDS),
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            out = {k: CsvInventoryExporter._cell(row.get(k)) for k in INVENTORY_RESULTS_CSV_FIELDS}
            writer.writerow(out)
        return f"{UTF8_BOM}{buf.getvalue()}"

    @staticmethod
    def _cell(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)
