"""Phase 6 — prompt composition metadata validation."""

from __future__ import annotations

from src.llm.prompt_composer.prompt_traceability import (
    COMPOSITION_STEP_COMPOSE_HYBRID_BASE,
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
        composition_steps=[{"step": COMPOSITION_STEP_COMPOSE_HYBRID_BASE}],
        job_prompt_key=None,
        settings_hybrid_prompt_key=None,
    )
    meta_bad = dict(meta)
    meta_bad["prompt_hash"] = "0" * 64
    errs = validate_prompt_composition_dict(meta_bad)
    assert any("prompt_hash" in e for e in errs)


def test_validate_prompt_composition_rejects_wrong_types() -> None:
    meta = build_prompt_composition_dict(
        profile_name="global_v21",
        pipeline_provider_key="gemini",
        base_prompt_text="a",
        final_prompt_text="a",
        enrichments_applied=[],
        composition_steps=[],
        job_prompt_key=None,
        settings_hybrid_prompt_key=None,
    )
    bad = dict(meta)
    bad["enrichments_applied"] = "not-a-list"
    errs = validate_prompt_composition_dict(bad)
    assert any("enrichments_applied must be a list" in e for e in errs)

    bad2 = dict(meta)
    bad2["composition_steps"] = {}
    errs2 = validate_prompt_composition_dict(bad2)
    assert any("composition_steps must be a list" in e for e in errs2)


def test_validate_prompt_composition_rejects_empty_profile_name() -> None:
    meta = build_prompt_composition_dict(
        profile_name="x",
        pipeline_provider_key="openai",
        base_prompt_text="a",
        final_prompt_text="a",
        enrichments_applied=[],
        composition_steps=[],
        job_prompt_key=None,
        settings_hybrid_prompt_key=None,
    )
    bad = dict(meta)
    bad["profile_name"] = "   "
    errs = validate_prompt_composition_dict(bad)
    assert any("profile_name" in e for e in errs)


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
