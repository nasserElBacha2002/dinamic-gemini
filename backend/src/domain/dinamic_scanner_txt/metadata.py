"""JSON metadata persisted on staged local CSV imports for scanner TXT."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from src.domain.dinamic_scanner_txt.constants import SCANNER_TXT_METADATA_KIND


@dataclass(frozen=True)
class DinamicScannerTxtImportMetadata:
    aisle_code: str
    aisle_will_be_created: bool
    target_aisle_id: str | None
    positions_imported: int
    products_imported: int
    omitted_records: int
    parse_warnings: tuple[str, ...]
    aisle_created_on_confirm: bool = False

    def to_json(self) -> str:
        payload: dict[str, Any] = {
            "kind": SCANNER_TXT_METADATA_KIND,
            "aisle_code": self.aisle_code,
            "aisle_will_be_created": self.aisle_will_be_created,
            "target_aisle_id": self.target_aisle_id,
            "positions_imported": self.positions_imported,
            "products_imported": self.products_imported,
            "omitted_records": self.omitted_records,
            "parse_warnings": list(self.parse_warnings),
            "aisle_created_on_confirm": self.aisle_created_on_confirm,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @staticmethod
    def from_json(raw: str | None) -> DinamicScannerTxtImportMetadata | None:
        if not raw or not str(raw).strip():
            return None
        parsed = json.loads(str(raw))
        if not isinstance(parsed, dict) or parsed.get("kind") != SCANNER_TXT_METADATA_KIND:
            return None
        warnings = parsed.get("parse_warnings") or []
        return DinamicScannerTxtImportMetadata(
            aisle_code=str(parsed.get("aisle_code") or "").strip(),
            aisle_will_be_created=bool(parsed.get("aisle_will_be_created")),
            target_aisle_id=(
                str(parsed["target_aisle_id"]).strip()
                if parsed.get("target_aisle_id")
                else None
            ),
            positions_imported=int(parsed.get("positions_imported") or 0),
            products_imported=int(parsed.get("products_imported") or 0),
            omitted_records=int(parsed.get("omitted_records") or 0),
            parse_warnings=tuple(str(item) for item in warnings),
            aisle_created_on_confirm=bool(parsed.get("aisle_created_on_confirm")),
        )
