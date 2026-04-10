"""Phase 6 — prompt composition metadata validation."""

from __future__ import annotations

from src.llm.prompt_composer.prompt_traceability import (
    build_prompt_composition_dict,
    validate_prompt_composition_dict,
)


def test_validate_prompt_composition_detects_hash_mismatch() -> None:
    meta = build_prompt_composition_dict(
        profile_name="p",
        pipeline_provider_key="gemini",
        base_prompt_text="base",
        final_prompt_text="final",
        enrichments_applied=["x"],
        composition_steps=[{"step": "compose"}],
        job_prompt_key=None,
        settings_hybrid_prompt_key=None,
    )
    meta_bad = dict(meta)
    meta_bad["prompt_hash"] = "0" * 64
    errs = validate_prompt_composition_dict(meta_bad)
    assert any("prompt_hash" in e for e in errs)


def test_validate_prompt_composition_empty_enrichments_implies_base_equals_final() -> None:
    meta = build_prompt_composition_dict(
        profile_name="p",
        pipeline_provider_key="openai",
        base_prompt_text="same",
        final_prompt_text="different",
        enrichments_applied=[],
        composition_steps=[],
        job_prompt_key=None,
        settings_hybrid_prompt_key=None,
    )
    errs = validate_prompt_composition_dict(meta)
    assert any("enrichments_applied" in e for e in errs)
