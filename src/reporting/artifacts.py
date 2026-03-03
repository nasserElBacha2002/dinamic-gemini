"""
Stage 4 — Write hybrid report artifacts (JSON and CSV).
"""

import csv
import json
from pathlib import Path
from typing import Any, Dict, List

from src.domain.pallet import Pallet


def write_json(path: Path, data: Dict[str, Any]) -> None:
    """Write a dict as UTF-8 JSON to path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


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
