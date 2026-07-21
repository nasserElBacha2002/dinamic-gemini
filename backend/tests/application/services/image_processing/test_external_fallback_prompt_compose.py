"""External fallback prompt composition + schema routing tests."""

from __future__ import annotations

from src.application.services.image_processing.external_fallback_prompt import (
    EXTERNAL_FALLBACK_PROMPT_KEY,
    compose_external_fallback_prompt,
)
from src.llm.schema_versions import LlmSchemaVersion


def test_compose_includes_client_and_supplier_sections_deterministically() -> None:
    a = compose_external_fallback_prompt(
        client_rules={
            "client_rule_key": "ean_first",
            "client_rule_version": "1",
            "prefer_ean_as_internal_code": True,
            "required_fields": ["internal_code", "quantity"],
        },
        supplier_extraction_profile={
            "profile_key": "masol",
            "profile_version": "2",
            "configuration": {"llm_instructions": "Prefer labeled EAN."},
        },
        quantity_max=999,
        strategy="INTERNAL_OCR",
    )
    b = compose_external_fallback_prompt(
        client_rules={
            "client_rule_key": "ean_first",
            "client_rule_version": "1",
            "prefer_ean_as_internal_code": True,
            "required_fields": ["internal_code", "quantity"],
        },
        supplier_extraction_profile={
            "profile_key": "masol",
            "profile_version": "2",
            "configuration": {"llm_instructions": "Prefer labeled EAN."},
        },
        quantity_max=999,
        strategy="INTERNAL_OCR",
    )
    assert a["sha256"] == b["sha256"]
    assert a["prompt_key"] == EXTERNAL_FALLBACK_PROMPT_KEY
    assert a["schema_version"] == LlmSchemaVersion.EXTERNAL_FALLBACK_V1
    assert "[CLIENT RULES]" in a["text"]
    assert "[SUPPLIER EXTRACTION PROFILE]" in a["text"]
    assert "Prefer labeled EAN." in a["text"]
    assert "entities" in a["text"].lower()  # contract forbids returning entities
    assert "Do NOT return hybrid" in a["text"]


def test_compose_changes_hash_when_profile_changes() -> None:
    base = compose_external_fallback_prompt(client_rules={"prefer_ean_as_internal_code": False})
    changed = compose_external_fallback_prompt(
        client_rules={"prefer_ean_as_internal_code": True}
    )
    assert base["sha256"] != changed["sha256"]
