"""
Phase 4 — golden parity: hybrid base prompt text must not drift silently.

SHA-256 fingerprints lock the four distinct base texts (default vs openai for v21 / v21_b).
``get_hybrid_prompt`` must remain a thin delegate of ``HybridPromptComposer``.
"""

from __future__ import annotations

import hashlib

import pytest

from src.jobs.image_identity import JobImage
from src.llm.prompt_composer.composer import HybridPromptComposer, default_hybrid_composer
from src.llm.prompt_composer.enrichments import enrich_prompt_with_image_ids
from src.llm.prompts import (
    enrich_prompt_with_image_ids as enrich_prompt_with_image_ids_facade,
    enrich_prompt_with_product_label_association as product_label_facade,
    get_hybrid_prompt,
)
from src.llm.prompt_composer.enrichments import (
    enrich_prompt_with_product_label_association as product_label_direct,
)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# Fingerprints of ``default_hybrid_composer.compose_base`` outputs (update only when intentionally changing prompts).
_GOLDEN_BASE: dict[tuple[str, str | None], str] = {
    ("global_v21", None): "0b902e46b3c2b57507d423e075a6c96482ba83c8710718b15eb642e4c6033f34",
    ("global_v21", "openai"): "151b9dbf548a7f9592e94becd0c37936d93e7bc3a9b0d95d551f40a986f850c3",
    ("global_v21_b", None): "e8ffba99272ebf0e4ee3bbfc239ee35fd3645cf4599a0659f689c4f7391a110a",
    ("global_v21_b", "openai"): "73f35647625e5259d32bd0af54ce577e4d50f2b301cbbd5af55f30ccb9408c89",
}


@pytest.mark.parametrize("profile,provider", list(_GOLDEN_BASE.keys()))
def test_hybrid_base_prompt_golden_sha256(profile: str, provider: str | None) -> None:
    text = default_hybrid_composer.compose_base(profile, provider)
    assert _sha256(text) == _GOLDEN_BASE[(profile, provider)]


def test_gemini_and_unknown_vendor_match_default_variant() -> None:
    d = default_hybrid_composer.compose_base("global_v21", None)
    assert default_hybrid_composer.compose_base("global_v21", "gemini") == d
    assert default_hybrid_composer.compose_base("global_v21", "unknown_vendor") == d


def test_get_hybrid_prompt_matches_composer_for_matrix() -> None:
    for profile in ("global_v21", "global_v21_b", "unknown_xyz"):
        for pk in (None, "gemini", "openai", "unknown_vendor"):
            assert get_hybrid_prompt(profile, pk) == default_hybrid_composer.compose_base(profile, pk)


def test_new_composer_instance_matches_singleton() -> None:
    c = HybridPromptComposer()
    assert c.compose_base("global_v21_b", "openai") == default_hybrid_composer.compose_base(
        "global_v21_b", "openai"
    )


def test_enrichment_functions_same_object_via_facade() -> None:
    assert enrich_prompt_with_image_ids_facade is enrich_prompt_with_image_ids
    assert product_label_facade is product_label_direct


def test_image_id_enrichment_parity_sample() -> None:
    base = default_hybrid_composer.compose_base("global_v21", None)
    images = [
        JobImage(
            image_id="img_001",
            original_filename="a.jpg",
            upload_order=1,
            storage_path="input_photos/a.jpg",
        )
    ]
    enriched = enrich_prompt_with_image_ids(base, images)
    assert "img_001" in enriched
    assert "TRACEABILITY (v3.1)" in enriched
    assert _sha256(enriched) == "db433a90f3c2eeed054c4650efcf12213c375e1c250f7b6612e9d17e5d96644d"

