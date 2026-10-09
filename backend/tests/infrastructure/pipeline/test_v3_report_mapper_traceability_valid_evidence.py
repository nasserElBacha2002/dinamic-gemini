"""Phase 4.2 — v3_report_mapper persists traceability_warning and has_valid_evidence."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.infrastructure.pipeline.v3_report_mapper import map_hybrid_report_to_domain


def test_mapper_persists_traceability_warning_and_has_valid_evidence(tmp_path: Path) -> None:
    now = datetime(2026, 6, 17, tzinfo=timezone.utc)
    report = {
        "entities": [
            {
                "entity_uid": "job_E1",
                "entity_type": "PALLET",
                "model_entity_id": "E1",
                "internal_code": "SKU-X",
                "final_quantity": 1,
                "confidence": 0.9,
                "count_status": "COUNTED",
                "evidence_path": "evidence/crop.jpg",
                "source_image_id": "asset-bad",
                "traceability_status": "invalid",
                "traceability_warning": "Returned image ID was not part of the final provider payload.",
            }
        ]
    }
    mapped = map_hybrid_report_to_domain(
        aisle_id="aisle-1",
        report=report,
        run_dir=tmp_path,
        run_id="run",
        job_id="job-1",
        now=now,
        inventory_id="inv-1",
    )
    summary = mapped.positions[0].detected_summary_json or {}
    assert summary.get("traceability_warning") == (
        "Returned image ID was not part of the final provider payload."
    )
    assert summary.get("has_valid_evidence") is False
    assert summary.get("source_image_id") == "asset-bad"
