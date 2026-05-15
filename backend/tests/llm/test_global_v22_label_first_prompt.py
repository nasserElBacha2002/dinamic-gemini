"""global_v22 — label-first wording, same v2.1 JSON wire contract as global_v21."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.application.services.supplier_prompt_resolver import SupplierPromptResolution
from src.jobs.image_identity import JobImage
from src.llm.prompt_composer.enrichments import enrich_prompt_with_image_ids
from src.llm.prompt_composer.hybrid_assembly import compose_hybrid_base
from src.llm.prompt_composer.hybrid_profiles import PROMPTS
from src.llm.prompt_composer.hybrid_resolution import registered_hybrid_prompt_keys
from src.llm.prompt_composer.protected_prompt_contract import (
    HYBRID_V21_CLAUDE_SUPPLEMENT_MARKERS,
    HYBRID_V21_DEFAULT_BRANCH_MARKERS,
    HYBRID_V21_OPENAI_OVERLAY_MARKERS,
    HYBRID_V21_SHARED_CONTRACT_MARKERS,
)
from src.llm.prompts import get_hybrid_prompt
from src.parsing.global_analysis_parser import parse_entities
from src.pipeline.context.run_context import RunContext
from src.pipeline.services.effective_prompt_composer import (
    EffectivePromptComposer,
    EffectivePromptComposerInput,
)
from src.pipeline.services.hybrid_analysis_prompt import (
    build_hybrid_analysis_prompt_with_traceability,
)
from src.validation.global_analysis_schema import validate_global_analysis_structure_v21


def _assert_all_markers(text: str, markers: tuple[str, ...], *, label: str) -> None:
    missing = [m for m in markers if m not in text]
    assert not missing, f"{label}: missing markers {missing!r} in prompt preview={text[:200]!r}..."


def test_global_v22_registered_and_differs_from_v21_default() -> None:
    assert "global_v22" in registered_hybrid_prompt_keys()
    v21 = compose_hybrid_base("global_v21", None, restrict_to_default_aisle_profile=False)
    v22 = compose_hybrid_base("global_v22", None)
    assert v22 != v21
    assert "Label-first" in v22 or "label-first" in v22.lower()
    assert "inventory positions" in v22.lower()


def test_global_v22_openai_variant_differs_from_default() -> None:
    d = compose_hybrid_base("global_v22", None)
    o = compose_hybrid_base("global_v22", "openai")
    assert d != o
    assert "Return valid JSON only" in o


def test_global_v22_preserves_root_contract_language_not_alternate_roots() -> None:
    """Intentionally avoid the alternate root key names in prompt text (grep-friendly invariant)."""
    text_default = compose_hybrid_base("global_v22", None)
    text_openai = compose_hybrid_base("global_v22", "openai")
    assert "total_positions_detected" not in text_default
    assert "total_positions_detected" not in text_openai
    assert "total_entities_detected" in text_default
    assert "total_entities_detected" in text_openai
    assert "entities" in text_default


def test_global_v22_entity_type_taxonomy_strings_present() -> None:
    text = compose_hybrid_base("global_v22", None)
    for token in ("PALLET", "EMPTY_PALLET", "LOOSE_BOXES"):
        assert token in text


def test_global_v22_claude_path_shares_canonical_contract_tail_with_v21() -> None:
    contract = str(PROMPTS["global_v22"]["claude"]).rstrip()
    assert contract == str(PROMPTS["global_v21"]["claude"]).rstrip()
    t21 = compose_hybrid_base(
        "global_v21", "claude", prompt_parity_mode=False, restrict_to_default_aisle_profile=False
    )
    t22 = compose_hybrid_base("global_v22", "claude", prompt_parity_mode=False)
    assert t21.endswith(contract)
    assert t22.endswith(contract)


def test_get_hybrid_prompt_delegates_global_v22() -> None:
    assert get_hybrid_prompt("global_v22", None) == compose_hybrid_base("global_v22", None)


@pytest.mark.parametrize(
    ("provider_key", "prompt_parity_mode", "extra_markers"),
    [
        (None, False, ()),
        ("gemini", False, ()),
        ("openai", False, HYBRID_V21_OPENAI_OVERLAY_MARKERS),
        ("openai", True, ()),
        ("claude", False, HYBRID_V21_CLAUDE_SUPPLEMENT_MARKERS),
        ("anthropic", False, HYBRID_V21_CLAUDE_SUPPLEMENT_MARKERS),
    ],
)
def test_compose_hybrid_base_global_v22_includes_protected_markers(
    provider_key: str | None,
    prompt_parity_mode: bool,
    extra_markers: tuple[str, ...],
) -> None:
    text = compose_hybrid_base(
        "global_v22", provider_key, prompt_parity_mode=prompt_parity_mode
    )
    _assert_all_markers(text, HYBRID_V21_SHARED_CONTRACT_MARKERS, label="global_v22 shared")
    use_openai_overlay = (
        (provider_key or "").strip().lower() == "openai" and not prompt_parity_mode
    )
    if not use_openai_overlay:
        _assert_all_markers(
            text, HYBRID_V21_DEFAULT_BRANCH_MARKERS, label="global_v22 default-branch"
        )
    _assert_all_markers(text, extra_markers, label="global_v22 overlay")


def test_v22_enrichment_then_supplier_preserves_traceability_and_disclaimer() -> None:
    base = compose_hybrid_base("global_v22", None)
    images = [
        JobImage(
            image_id="img_v22_1",
            original_filename="slot.jpg",
            upload_order=1,
            storage_path="input_photos/slot.jpg",
        )
    ]
    enriched = enrich_prompt_with_image_ids(base, images)
    assert "TRACEABILITY (v3.1)" in enriched
    assert "source_image_id" in enriched
    assert "img_v22_1" in enriched

    resolution = SupplierPromptResolution(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        client_id="c1",
        client_supplier_id="s1",
        provider_name="gemini",
        model_name=None,
        supplier_prompt_config_id="cfg-v22",
        supplier_prompt_config_version=1,
        editable_instructions="Prefer SKU format ABC-123 when visible.",
        fallback_used=False,
        fallback_reason=None,
        resolution_status="resolved",
        warnings=(),
        error_code=None,
    )
    composer = EffectivePromptComposer()
    out = composer.compose(
        EffectivePromptComposerInput(
            protected_prompt_text=enriched,
            provider_name="gemini",
            model_name=None,
            supplier_resolution=resolution,
        )
    )
    text = out.effective_prompt_text
    assert "img_v22_1" in text
    assert text.index("TRACEABILITY (v3.1)") < text.index("--- SUPPLIER-SPECIFIC EDITABLE INSTRUCTIONS ---")
    assert "must not override the protected JSON output contract" in text
    assert "ABC-123" in text


def test_build_hybrid_analysis_prompt_v22_profile_traceability_photos_job(tmp_path: Path) -> None:
    job_dir = tmp_path / "j"
    run_dir = job_dir / "r"
    run_dir.mkdir(parents=True)
    photos_dir = job_dir / "photos"
    photos_dir.mkdir()
    manifest = {
        "input_type": "photos",
        "photos": [{"index": 1, "stored_filename": "a.jpg", "image_id": "trace_img_v22"}],
    }
    (job_dir / "input_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    settings = MagicMock()
    settings.hybrid_prompt = "global_v22"
    settings.prompt_version = None
    job_input = MagicMock()
    job_input.input_type = "photos"
    job_input.input_manifest_path = "input_manifest.json"
    job_input.photos_dir = "photos"
    ctx = RunContext(
        job_id="j",
        run_id="r",
        workspace_path=tmp_path,
        run_dir=run_dir,
        job_input=job_input,
        settings=settings,
        logger=MagicMock(),
    )
    text, meta = build_hybrid_analysis_prompt_with_traceability(ctx)
    assert meta.get("profile_name") == "global_v22"
    assert "trace_img_v22" in text
    assert "source_image_id" in text
    assert "Label-first" in text or "label-first" in text.lower()


def test_validate_and_parse_label_first_payload_with_extra_entity_keys_ignored() -> None:
    """Validator checks known fields only; parser ignores unknown entity properties."""
    data = {
        "total_entities_detected": 2,
        "entities": [
            {
                "entity_type": "PALLET",
                "model_entity_id": "E1",
                "has_boxes": True,
                "confidence": 0.91,
                "internal_code": "SKU-A",
                "product_label_quantity": 12,
                "source_image_id": "cam-1",
                "label_readable": True,
                "quantity_source": "LABEL",
            },
            {
                "entity_type": "PALLET",
                "model_entity_id": "E2",
                "has_boxes": True,
                "confidence": 0.7,
                "internal_code": None,
                "product_label_quantity": None,
                "source_image_id": "cam-1",
                "label_readable": False,
            },
        ],
    }
    validate_global_analysis_structure_v21(data)
    entities = parse_entities(data, job_id="job-x")
    assert len(entities) == 2
    assert entities[0].internal_code == "SKU-A"
    assert entities[0].product_label_quantity == 12
    assert entities[1].internal_code is None
