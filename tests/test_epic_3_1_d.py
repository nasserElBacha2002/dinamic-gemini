"""Epic 3.1.D — Backend prompt + product/label association (hardened).

Tests: centralized derive_review_display_label (prefer internal_code, fallback position_barcode;
None/empty/whitespace); prompt enrichment explicit (get_hybrid_prompt base only, enrich at call sites);
report/API/CSV use review_display_label; API also returns product_display_label (backward compat);
empty/legacy handling.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.domain.entity import Entity
from src.llm.prompts import enrich_prompt_with_product_label_association, get_hybrid_prompt
from src.reporting.artifacts import write_report_csv
from src.reporting.display_label import derive_review_display_label
from src.reporting.hybrid_report import build_hybrid_report


# ---------- Centralized derivation helper ----------


def test_derive_review_display_label_prefers_internal_code():
    """Prefers internal_code when present and non-empty."""
    assert derive_review_display_label("SKU-X", "POS-1") == "SKU-X"
    assert derive_review_display_label(internal_code="A", position_barcode="B") == "A"


def test_derive_review_display_label_fallback_to_position_barcode():
    """Falls back to position_barcode when internal_code missing or blank."""
    assert derive_review_display_label(None, "BC-001") == "BC-001"
    assert derive_review_display_label("", "BC-001") == "BC-001"
    assert derive_review_display_label("  ", "BC-001") == "BC-001"


def test_derive_review_display_label_none_when_both_missing():
    """Returns None when both missing or blank."""
    assert derive_review_display_label(None, None) is None
    assert derive_review_display_label("", "") is None
    assert derive_review_display_label("  ", "\t") is None


def test_derive_review_display_label_empty_strings_treated_as_missing():
    """Empty and whitespace-only strings trigger fallback or None."""
    assert derive_review_display_label("", "POS") == "POS"
    assert derive_review_display_label("  ", None) is None
    assert derive_review_display_label(internal_code="  ", position_barcode="") is None


# ---------- Prompt: base vs explicit enrichment ----------


def test_get_hybrid_prompt_returns_base_only():
    """get_hybrid_prompt() returns base prompt only; does not append Epic D block."""
    prompt = get_hybrid_prompt()
    assert "Analyze the frames" in prompt or "Entity types" in prompt
    assert "PRODUCT AND LABEL ASSOCIATION" not in prompt


def test_enrich_prompt_with_product_label_association_adds_block():
    """enrich_prompt_with_product_label_association() appends product/label block."""
    base = get_hybrid_prompt()
    enriched = enrich_prompt_with_product_label_association(base)
    assert "PRODUCT AND LABEL ASSOCIATION" in enriched
    assert "internal_code" in enriched
    assert "position_barcode" in enriched
    assert base.rstrip() in enriched
    assert enriched.endswith("position/pallet identifier.") or "pallet" in enriched


def test_enriched_prompt_used_at_adapter_layer():
    """Pipeline adapter builds prompt with explicit enrichment (integration point)."""
    from src.llm.prompts import get_hybrid_prompt, enrich_prompt_with_product_label_association
    base = get_hybrid_prompt("global_v21")
    enriched = enrich_prompt_with_product_label_association(base)
    assert "PRODUCT AND LABEL ASSOCIATION" in enriched


# ---------- Report review_display_label ----------


def test_build_hybrid_report_includes_review_display_label_from_internal_code():
    """Report entities include review_display_label; prefer internal_code."""
    entities = [
        Entity("u1", "PALLET", "m1", internal_code="SKU123", position_barcode="POS-A"),
    ]
    report = build_hybrid_report(
        video_path="/tmp/v.mp4",
        entities=entities,
        frames_selected=2,
    )
    out = report["entities"]
    assert len(out) == 1
    assert out[0]["review_display_label"] == "SKU123"


def test_build_hybrid_report_review_display_label_fallback_to_position_barcode():
    """When internal_code missing, review_display_label uses position_barcode."""
    entities = [
        Entity("u1", "PALLET", "m1", position_barcode="BC-001"),
    ]
    report = build_hybrid_report(
        video_path="/tmp/v.mp4",
        entities=entities,
        frames_selected=2,
    )
    out = report["entities"]
    assert len(out) == 1
    assert out[0]["review_display_label"] == "BC-001"


def test_build_hybrid_report_review_display_label_none_when_both_missing():
    """When both internal_code and position_barcode missing, review_display_label is None."""
    entities = [
        Entity("u1", "PALLET", "m1"),
    ]
    report = build_hybrid_report(
        video_path="/tmp/v.mp4",
        entities=entities,
        frames_selected=2,
    )
    out = report["entities"]
    assert len(out) == 1
    assert out[0]["review_display_label"] is None


def test_build_hybrid_report_review_display_label_empty_strings_treated_as_missing():
    """Empty internal_code and position_barcode yield None review_display_label."""
    entities = [
        Entity("u1", "PALLET", "m1", internal_code="", position_barcode="  "),
    ]
    report = build_hybrid_report(
        video_path="/tmp/v.mp4",
        entities=entities,
        frames_selected=2,
    )
    out = report["entities"]
    assert len(out) == 1
    assert out[0]["review_display_label"] is None


# ---------- API list_entities: review_display_label + product_display_label alias ----------


@pytest.fixture
def client():
    return TestClient(app)


def test_list_entities_returns_review_display_label_and_alias(client, tmp_path):
    """GET /jobs/{id}/entities returns review_display_label and product_display_label (same value)."""
    job_id = "job_epic3d01"
    run_dir = tmp_path / job_id / "run"
    run_dir.mkdir(parents=True)
    report_path = run_dir / "hybrid_report.json"
    report = {
        "report_version": "2.1",
        "mode": "hybrid_v2.1",
        "entities": [
            {
                "entity_uid": f"{job_id}_E1",
                "entity_type": "PALLET",
                "count_status": "COUNTED",
                "internal_code": "SKU-X",
                "position_barcode": "POS-1",
            },
        ],
        "traceability_summary": {"total_entities": 1, "valid": 0, "missing": 1, "invalid": 0, "unvalidated": 0},
    }
    report_path.write_text(json.dumps(report), encoding="utf-8")
    with patch("src.api.routes.entities._resolve_report_and_run_dir") as mock_resolve:
        mock_resolve.return_value = (report_path, run_dir)
        resp = client.get(f"/api/v1/inventory/jobs/{job_id}/entities")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["entities"]) == 1
    ent = data["entities"][0]
    assert ent["review_display_label"] == "SKU-X"
    assert ent["product_display_label"] == "SKU-X"


def test_list_entities_derives_display_label_when_key_missing(client, tmp_path):
    """Legacy report without review_display_label: API derives internal_code else position_barcode."""
    job_id = "job_epic3d02"
    run_dir = tmp_path / job_id / "run"
    run_dir.mkdir(parents=True)
    report_path = run_dir / "hybrid_report.json"
    report = {
        "report_version": "2.1",
        "mode": "hybrid_v2.1",
        "entities": [
            {
                "entity_uid": f"{job_id}_E1",
                "entity_type": "PALLET",
                "count_status": "NEEDS_REVIEW",
                "position_barcode": "LEGACY-POS",
            },
        ],
        "traceability_summary": {"total_entities": 1, "valid": 0, "missing": 1, "invalid": 0, "unvalidated": 0},
    }
    report_path.write_text(json.dumps(report), encoding="utf-8")
    with patch("src.api.routes.entities._resolve_report_and_run_dir") as mock_resolve:
        mock_resolve.return_value = (report_path, run_dir)
        resp = client.get(f"/api/v1/inventory/jobs/{job_id}/entities")
    assert resp.status_code == 200
    data = resp.json()
    assert data["entities"][0]["review_display_label"] == "LEGACY-POS"
    assert data["entities"][0]["product_display_label"] == "LEGACY-POS"


# ---------- CSV review_display_label ----------


def test_write_report_csv_includes_review_display_label_column(tmp_path):
    """CSV has review_display_label column; value derived via helper."""
    report = {
        "entities": [
            {"entity_uid": "e1", "internal_code": "SKU1", "pallet_id": "P1", "entity_type": "PALLET", "count_status": "COUNTED"},
            {"entity_uid": "e2", "position_barcode": "BC2", "pallet_id": "P2", "entity_type": "PALLET", "count_status": "COUNTED"},
            {"entity_uid": "e3", "pallet_id": "P3", "entity_type": "PALLET", "count_status": "COUNTED"},
        ],
    }
    path = tmp_path / "out.csv"
    write_report_csv(path, report)
    content = path.read_text(encoding="utf-8")
    assert "review_display_label" in content
    lines = content.strip().split("\n")
    assert len(lines) >= 2
    header = lines[0]
    assert "review_display_label" in header
    idx = header.split(",").index("review_display_label")
    assert lines[1].split(",")[idx] == "SKU1"
    assert lines[2].split(",")[idx] == "BC2"
    assert lines[3].split(",")[idx] == ""


def test_write_report_csv_empty_entities_header_includes_review_display_label(tmp_path):
    """Empty entities list still writes header with review_display_label."""
    report = {"entities": []}
    path = tmp_path / "empty.csv"
    write_report_csv(path, report)
    content = path.read_text(encoding="utf-8")
    assert "review_display_label" in content
