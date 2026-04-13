"""Claude hybrid base + JSON suffix align with canonical v2.1 entity extraction (text model path)."""

from __future__ import annotations

from src.llm.prompt_composer.hybrid_assembly import compose_hybrid_base
from src.llm.prompt_composer.hybrid_profiles import CLAUDE_JSON_OUTPUT_INSTRUCTION_SUFFIX


def _canonical_field_markers() -> tuple[str, ...]:
    return (
        "internal_code",
        "position_barcode",
        "product_label_quantity",
        "product_label_bbox",
        "position_label_bbox",
    )


def test_compose_hybrid_base_claude_includes_canonical_entity_fields() -> None:
    text = compose_hybrid_base("global_v21", "claude", prompt_parity_mode=False)
    for key in _canonical_field_markers():
        assert key in text, f"missing canonical mention: {key}"


def test_compose_hybrid_base_claude_forbids_non_canonical_keys() -> None:
    text = compose_hybrid_base("global_v21", "claude", prompt_parity_mode=False)
    assert "FORBIDDEN" in text
    assert "position_label" in text and "product_label" in text
    assert "detected_quantity" in text


def test_claude_json_output_suffix_lists_canonical_and_forbidden() -> None:
    s = CLAUDE_JSON_OUTPUT_INSTRUCTION_SUFFIX
    for key in _canonical_field_markers():
        assert key in s
    assert "Do NOT include keys:" in s
    assert "position_label, product_label" in s
    assert "detected_quantity" in s


def test_compose_hybrid_base_gemini_unchanged_no_claude_contract_block() -> None:
    gemini = compose_hybrid_base("global_v21", "gemini", prompt_parity_mode=False)
    claude = compose_hybrid_base("global_v21", "claude", prompt_parity_mode=False)
    assert "CLAUDE JSON ENTITY CONTRACT" not in gemini
    assert "CLAUDE JSON ENTITY CONTRACT" in claude
    assert gemini != claude


def test_claude_parity_mode_drops_supplement_matches_gemini_base() -> None:
    g = compose_hybrid_base("global_v21", "gemini", prompt_parity_mode=True)
    c = compose_hybrid_base("global_v21", "claude", prompt_parity_mode=True)
    assert g == c
    assert "CLAUDE JSON ENTITY CONTRACT" not in c


def test_global_v21_b_claude_also_gets_contract() -> None:
    text = compose_hybrid_base("global_v21_b", "claude", prompt_parity_mode=False)
    assert "CLAUDE JSON ENTITY CONTRACT" in text
    assert "internal_code" in text and "position_barcode" in text
