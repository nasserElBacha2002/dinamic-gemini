"""Claude hybrid base + JSON suffix align with canonical v2.1 entity extraction (text model path)."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.llm.prompt_composer.hybrid_assembly import compose_hybrid_base, compose_hybrid_base_from_settings
from src.pipeline.provider_keys import normalize_pipeline_provider_key
from src.llm.prompt_composer.hybrid_profiles import (
    CLAUDE_CONTRACT_MARKER,
    CLAUDE_FORBIDDEN_JSON_KEYS,
    CLAUDE_JSON_ENTITY_OUTPUT_KEYS,
    CLAUDE_JSON_OUTPUT_INSTRUCTION_SUFFIX,
    build_claude_json_output_instruction_suffix,
    claude_forbidden_json_keys_csv,
)


def test_compose_hybrid_base_claude_includes_canonical_entity_fields() -> None:
    text = compose_hybrid_base("global_v21", "claude", prompt_parity_mode=False)
    for key in CLAUDE_JSON_ENTITY_OUTPUT_KEYS:
        assert key in text, f"missing canonical mention: {key}"


def test_compose_hybrid_base_claude_forbids_non_canonical_keys() -> None:
    text = compose_hybrid_base("global_v21", "claude", prompt_parity_mode=False)
    assert "FORBIDDEN" in text
    assert "position_label" in text and "product_label" in text
    assert "detected_quantity" in text


def test_claude_json_output_suffix_lists_canonical_and_forbidden() -> None:
    s = CLAUDE_JSON_OUTPUT_INSTRUCTION_SUFFIX
    assert ", ".join(CLAUDE_JSON_ENTITY_OUTPUT_KEYS) in s
    assert claude_forbidden_json_keys_csv() in s
    assert "Do NOT include keys:" in s
    for fk in CLAUDE_FORBIDDEN_JSON_KEYS:
        assert fk in s


def test_claude_contract_and_suffix_share_forbidden_and_entity_key_lists() -> None:
    """Builder + constants stay aligned (single source of truth in hybrid_profiles)."""
    from src.llm.prompt_composer.hybrid_profiles import PROMPTS

    contract = PROMPTS["global_v21"]
    assert isinstance(contract, dict)
    ctext = str(contract["claude"])
    assert claude_forbidden_json_keys_csv() in ctext
    suffix = build_claude_json_output_instruction_suffix()
    assert suffix == CLAUDE_JSON_OUTPUT_INSTRUCTION_SUFFIX
    assert claude_forbidden_json_keys_csv() in suffix


def test_compose_hybrid_base_gemini_unchanged_no_claude_contract_block() -> None:
    gemini = compose_hybrid_base("global_v21", "gemini", prompt_parity_mode=False)
    claude = compose_hybrid_base("global_v21", "claude", prompt_parity_mode=False)
    assert CLAUDE_CONTRACT_MARKER not in gemini
    assert CLAUDE_CONTRACT_MARKER in claude
    assert gemini != claude


def test_claude_parity_mode_drops_supplement_matches_gemini_base() -> None:
    g = compose_hybrid_base("global_v21", "gemini", prompt_parity_mode=True)
    c = compose_hybrid_base("global_v21", "claude", prompt_parity_mode=True)
    assert g == c
    assert CLAUDE_CONTRACT_MARKER not in c


def test_global_v21_b_claude_also_gets_contract() -> None:
    text = compose_hybrid_base("global_v21_b", "claude", prompt_parity_mode=False)
    assert CLAUDE_CONTRACT_MARKER in text
    assert "internal_code" in text and "position_barcode" in text


def test_compose_from_settings_with_normalized_pipeline_provider_claude() -> None:
    """Production ``llm_provider`` resolves to ``claude``; composition must attach the overlay."""
    settings = MagicMock()
    settings.hybrid_prompt = "global_v21"
    pk = normalize_pipeline_provider_key("claude", settings)
    assert pk == "claude"
    text = compose_hybrid_base_from_settings(settings, pipeline_provider_key=pk)
    assert CLAUDE_CONTRACT_MARKER in text
