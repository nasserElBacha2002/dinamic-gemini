"""Phase 5 — production prompt construction must not bypass ``prompt_composer`` assembly."""

from __future__ import annotations

from pathlib import Path


def _src_root() -> Path:
    return Path(__file__).resolve().parents[2] / "src"


def _src_text(rel: str) -> str:
    return (_src_root() / rel).read_text(encoding="utf-8")


def test_adapters_do_not_import_legacy_get_hybrid_prompt() -> None:
    assert "get_hybrid_prompt" not in _src_text("llm/gemini_sdk_adapter.py")
    assert "get_hybrid_prompt" not in _src_text("llm/openai_sdk_adapter.py")


def test_gemini_global_analyzer_does_not_import_get_hybrid_prompt() -> None:
    assert "get_hybrid_prompt" not in _src_text("llm/gemini_global_analyzer.py")


def test_hybrid_assembly_defines_adapter_fallback_entrypoint() -> None:
    text = _src_text("llm/prompt_composer/hybrid_assembly.py")
    assert "def compose_hybrid_base_from_settings" in text
    assert "def resolve_hybrid_profile_name" in text


def test_production_code_does_not_import_prompt_registry_outside_composer() -> None:
    """``PROMPTS`` must only be imported inside ``prompt_composer`` (not adapters/pipeline/application)."""
    root = _src_root()
    bad: list[str] = []
    for path in root.rglob("*.py"):
        rel = path.relative_to(root)
        if "prompt_composer" in rel.parts:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if "hybrid_profiles" in s and "import" in s and "PROMPTS" in s:
                bad.append(f"{rel}:{s[:80]}")
                break
    assert not bad, f"Direct PROMPTS import outside prompt_composer: {bad}"


def test_llm_prompts_facade_does_not_reexport_prompt_registry() -> None:
    text = _src_text("llm/prompts.py")
    assert ", PROMPTS" not in text
    assert ", HYBRID_PROMPTS" not in text
    assert '"PROMPTS"' not in text
    assert '"HYBRID_PROMPTS"' not in text
