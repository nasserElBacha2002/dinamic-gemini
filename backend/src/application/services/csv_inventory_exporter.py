"""Build CSV text for v3 inventory results export (single table, UTF-8).

Output is prefixed with a UTF-8 BOM so Excel recognizes UTF-8 and renders accented text correctly.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping, Sequence
from typing import Any

UTF8_BOM = "\ufeff"

# Standard operational export aligned with the public contract (snake_case CSV view).
INVENTORY_RESULTS_CSV_FIELDS: tuple[str, ...] = (
    "inventory_id",
    "inventory_name",
    "aisle_id",
    "aisle_code",
    "aisle_sequence",
    "position_id",
    "position_status",
    "needs_review",
    "position_code",
    "product_sku",
    "product_display_label",
    "barcode",
    "detected_quantity",
    "corrected_quantity",
    "final_quantity",
    "qty_source",
    "qty_inference_reason",
    "traceability_status",
    "source_image_id",
    "primary_evidence_id",
    "updated_at",
)

INVENTORY_RESULTS_TECHNICAL_CSV_FIELDS: tuple[str, ...] = (
    "inventory_id",
    "inventory_name",
    "aisle_id",
    "aisle_code",
    "aisle_sequence",
    "position_id",
    "position_code",
    "internal_code",
    "review_display_label",
    "position_barcode",
    "pallet_id",
    "entity_uid",
    "entity_type",
    "count_status",
    "raw_qty",
    "qty_parse_status",
    "qty_origin_field",
    "aggregated_from_ids",
    "audit_json",
    "updated_at",
)


class CsvInventoryExporter:
    """Turn export rows (flat dicts) into CSV text with stable headers."""

    @staticmethod
    def to_csv(
        rows: Sequence[Mapping[str, Any]],
        *,
        fieldnames: Sequence[str] = INVENTORY_RESULTS_CSV_FIELDS,
    ) -> str:
        buf = io.StringIO(newline="")
        writer = csv.DictWriter(
            buf,
            fieldnames=list(fieldnames),
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            out = {k: CsvInventoryExporter._cell(row.get(k)) for k in fieldnames}
            writer.writerow(out)
        return f"{UTF8_BOM}{buf.getvalue()}"

    @staticmethod
    def _cell(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)
