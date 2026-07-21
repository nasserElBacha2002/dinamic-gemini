"""External fallback prompt composition + mandatory supplier prompt tests."""

from __future__ import annotations

import pytest

from src.application.services.image_processing.external_fallback_prompt import (
    EXTERNAL_FALLBACK_PROMPT_KEY,
    SupplierPromptConfigError,
    build_resolved_supplier_prompt,
    compose_external_fallback_prompt,
)
from src.llm.schema_versions import LlmSchemaVersion


def _supplier_prompt(content: str = "UNIQUE_SUPPLIER_MARKER prefer labeled EAN-13."):
    return build_resolved_supplier_prompt(
        supplier_id="sup-1",
        prompt_id="prompt-1",
        prompt_version=3,
        content=content,
        extraction_profile_id="prof-1",
    )


def test_compose_includes_supplier_custom_instructions_complete() -> None:
    prompt = _supplier_prompt()
    composed = compose_external_fallback_prompt(
        client_rules={
            "client_rule_key": "ean_first",
            "prefer_ean_as_internal_code": True,
            "required_fields": ["internal_code", "quantity"],
        },
        supplier_extraction_profile={
            "supplier_profile_id": "prof-1",
            "supplier_profile_key": "masol",
            "supplier_profile_version": 2,
            "quantity_rules": {"required": True},
            "configuration": {
                "quantity_rules": {"required": True, "minimum": 1},
                "validation_rules": {"code": {"exact_length": 13}},
            },
        },
        supplier_prompt=prompt,
        supplier_prompt_required=True,
        quantity_max=999,
        strategy="INTERNAL_OCR",
    )
    assert composed.base_prompt_key == EXTERNAL_FALLBACK_PROMPT_KEY
    assert composed.schema_version == LlmSchemaVersion.EXTERNAL_FALLBACK_V1
    assert "[SUPPLIER CUSTOM INSTRUCTIONS]" in composed.text
    assert "UNIQUE_SUPPLIER_MARKER prefer labeled EAN-13." in composed.text
    assert "[SUPPLIER EXTRACTION PROFILE]" in composed.text
    assert "quantity.required: True" in composed.text
    assert "code.exact_length: 13" in composed.text
    assert composed.supplier_prompt_loaded is True
    assert composed.supplier_prompt_sha256 == prompt.content_sha256
    # Must not invent llm_instructions path as the source of custom text.
    assert "llm_instructions" not in composed.text


def test_compose_requires_supplier_prompt_when_flag_set() -> None:
    with pytest.raises(SupplierPromptConfigError) as ei:
        compose_external_fallback_prompt(supplier_prompt_required=True, supplier_prompt=None)
    assert ei.value.code == "SUPPLIER_PROMPT_REQUIRED"


def test_compose_hash_stable_and_changes_with_supplier_prompt() -> None:
    a = compose_external_fallback_prompt(supplier_prompt=_supplier_prompt("AAA"))
    b = compose_external_fallback_prompt(supplier_prompt=_supplier_prompt("AAA"))
    c = compose_external_fallback_prompt(supplier_prompt=_supplier_prompt("BBB"))
    assert a.sha256 == b.sha256
    assert a.sha256 != c.sha256


def test_compose_changes_hash_when_client_rules_change() -> None:
    base = compose_external_fallback_prompt(client_rules={"prefer_ean_as_internal_code": False})
    changed = compose_external_fallback_prompt(
        client_rules={"prefer_ean_as_internal_code": True}
    )
    assert base.sha256 != changed.sha256
