"""Unit tests for :func:`build_run_audit_snapshot` (Phase H4)."""

from __future__ import annotations

from typing import Any

from src.application.services.run_audit_snapshot import (
    RUN_AUDIT_SNAPSHOT_SCHEMA_VERSION,
    build_run_audit_snapshot,
)
from src.application.services.supplier_prompt_resolver import SupplierPromptResolution
from src.pipeline.run_metadata import RUN_METADATA_KEY_PROMPT_COMPOSITION, build_run_metadata


def _spr(**kwargs: Any) -> SupplierPromptResolution:
    defaults: dict[str, Any] = {
        "inventory_id": "inv-1",
        "aisle_id": "aisle-1",
        "client_id": "cl-1",
        "client_supplier_id": "cs-1",
        "provider_name": "gemini",
        "model_name": "gemini-pro",
        "supplier_prompt_config_id": "sp-db",
        "supplier_prompt_config_version": 4,
        "editable_instructions": "DO NOT LEAK",
        "fallback_used": True,
        "fallback_reason": "NO_ACTIVE_SUPPLIER_PROMPT_CONFIG",
        "resolution_status": "fallback",
        "warnings": ("spr-warn",),
        "error_code": None,
    }
    defaults.update(kwargs)
    return SupplierPromptResolution(**defaults)


def test_schema_version_and_core_ids() -> None:
    rm = build_run_metadata(None, None)
    rm["prompt_key"] = "global_v21"
    rm["prompt_version"] = "global_v21@v2.1"
    snap = build_run_audit_snapshot(
        run_metadata=rm,
        inventory_id="inv-1",
        aisle_id="aisle-1",
        client_id="cl-1",
        client_supplier_id="cs-1",
        provider_name="gemini",
        model_name="gemini-2.0-flash",
        supplier_prompt_resolution=None,
        analysis_context_available=True,
        created_at_iso="2026-05-11T12:00:00+00:00",
    )
    assert snap["schema_version"] == RUN_AUDIT_SNAPSHOT_SCHEMA_VERSION
    assert snap["inventory_id"] == "inv-1"
    assert snap["aisle_id"] == "aisle-1"
    assert snap["client_id"] == "cl-1"
    assert snap["client_supplier_id"] == "cs-1"
    assert snap["provider_name"] == "gemini"
    assert snap["model_name"] == "gemini-2.0-flash"
    assert snap["prompt_key"] == "global_v21"
    assert snap["prompt_version"] == "global_v21@v2.1"
    assert snap["metadata_sources"]["run_metadata"] is True
    assert snap["metadata_sources"]["prompt_composition"] is False


def test_frames_sent_ids_persisted_in_run_audit_snapshot_from_prompt_composition() -> None:
    comp: dict[str, Any] = {
        "frames_sent_ids": ["img_001", "img_002"],
        "prompt_listed_image_ids": ["img_001", "img_002"],
    }
    rm = build_run_metadata(None, None, prompt_composition=comp)
    snap = build_run_audit_snapshot(
        run_metadata=rm,
        inventory_id="inv-1",
        aisle_id="aisle-1",
        client_id=None,
        client_supplier_id=None,
        provider_name="gemini",
        model_name=None,
        supplier_prompt_resolution=None,
        analysis_context_available=False,
        created_at_iso="2026-05-11T12:00:00+00:00",
    )
    assert snap["frames_sent_ids"] == ["img_001", "img_002"]
    assert snap["prompt_listed_image_ids"] == ["img_001", "img_002"]
    assert snap["metadata_sources"]["prompt_composition"] is True


def test_frames_sent_ids_empty_when_prompt_composition_missing() -> None:
    rm = build_run_metadata(None, None)
    snap = build_run_audit_snapshot(
        run_metadata=rm,
        inventory_id=None,
        aisle_id=None,
        client_id=None,
        client_supplier_id=None,
        provider_name=None,
        model_name=None,
        supplier_prompt_resolution=None,
        analysis_context_available=False,
        created_at_iso="2026-05-11T12:00:00+00:00",
    )
    assert snap["frames_sent_ids"] == []
    assert snap["prompt_listed_image_ids"] == []


def test_effective_prompt_fields_and_references_from_composition() -> None:
    comp: dict[str, Any] = {
        "model_name": "from-comp",
        "effective_prompt": {
            "protected_prompt_contract_key": "hybrid_global",
            "protected_prompt_contract_version": "v2",
            "effective_prompt_hash": "abc",
            "supplier_prompt_config_id": "spc-1",
            "supplier_prompt_config_version": 2,
            "fallback_used": False,
            "fallback_reason": None,
            "warnings": ["w1"],
            "reference_image_ids": ["rid-1", "rid-2"],
            "reference_source": "supplier_reference_images",
        },
    }
    rm = build_run_metadata(None, None, prompt_composition=comp)
    snap = build_run_audit_snapshot(
        run_metadata=rm,
        inventory_id=None,
        aisle_id=None,
        client_id=None,
        client_supplier_id=None,
        provider_name="openai",
        model_name=None,
        supplier_prompt_resolution=None,
        analysis_context_available=False,
        created_at_iso="2026-01-01T00:00:00+00:00",
    )
    assert snap["protected_prompt_contract_key"] == "hybrid_global"
    assert snap["protected_prompt_contract_version"] == "v2"
    assert snap["effective_prompt_hash"] == "abc"
    assert snap["supplier_prompt_config_id"] == "spc-1"
    assert snap["supplier_prompt_config_version"] == "2"
    assert snap["supplier_prompt_fallback_used"] is False
    assert snap["supplier_prompt_fallback_reason"] is None
    assert snap["reference_ids"] == ["rid-1", "rid-2"]
    assert snap["reference_image_count"] == 2
    assert snap["reference_source"] == "supplier_reference_images"
    assert snap["supplier_reference_images_used"] is True
    assert snap["warnings"] == ["w1"]
    assert snap["prompt_composition_available"] is True


def test_supplier_prompt_resolution_fills_gaps_and_merges_warnings() -> None:
    rm = build_run_metadata(None, None)
    spr = _spr()
    snap = build_run_audit_snapshot(
        run_metadata=rm,
        inventory_id="inv-1",
        aisle_id="aisle-1",
        client_id=None,
        client_supplier_id=None,
        provider_name="gemini",
        model_name=None,
        supplier_prompt_resolution=spr,
        analysis_context_available=False,
        created_at_iso="2026-01-01T00:00:00+00:00",
    )
    assert snap["client_id"] == "cl-1"
    assert snap["client_supplier_id"] == "cs-1"
    assert snap["supplier_prompt_config_id"] == "sp-db"
    assert snap["supplier_prompt_config_version"] == "4"
    assert snap["supplier_prompt_fallback_used"] is True
    assert snap["supplier_prompt_fallback_reason"] == "NO_ACTIVE_SUPPLIER_PROMPT_CONFIG"
    assert "spr-warn" in snap["warnings"]
    assert "editable_instructions" not in snap
    assert "DO NOT LEAK" not in str(snap)


def test_missing_prompt_composition_safe() -> None:
    rm = build_run_metadata(None, None)
    snap = build_run_audit_snapshot(
        run_metadata=rm,
        inventory_id=None,
        aisle_id=None,
        client_id=None,
        client_supplier_id=None,
        provider_name=None,
        model_name=None,
        supplier_prompt_resolution=None,
        analysis_context_available=False,
        created_at_iso="2026-01-01T00:00:00+00:00",
    )
    assert snap["prompt_composition_available"] is False
    assert snap["effective_prompt_hash"] is None
    assert snap["warnings"] == []


def test_no_full_prompt_text_in_snapshot() -> None:
    comp: dict[str, Any] = {
        "prompt_text": "SECRET BODY",
        "effective_prompt": {"effective_prompt_hash": "h-only"},
    }
    rm = build_run_metadata(None, None, prompt_composition=comp)
    snap = build_run_audit_snapshot(
        run_metadata=rm,
        inventory_id=None,
        aisle_id=None,
        client_id=None,
        client_supplier_id=None,
        provider_name="x",
        model_name=None,
        supplier_prompt_resolution=None,
        analysis_context_available=False,
        created_at_iso="2026-01-01T00:00:00+00:00",
    )
    dumped = str(snap)
    assert "SECRET" not in dumped
    assert "prompt_text" not in snap
    assert RUN_METADATA_KEY_PROMPT_COMPOSITION not in snap
    assert snap["effective_prompt_hash"] == "h-only"
