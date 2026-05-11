"""
Phase E3 — **EffectivePromptComposer**: deterministic assembly of protected hybrid base + optional supplier text.

Pure service: no repositories, no LLM calls, no adapter or profile mutations. Production wiring is E4+.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from src.application.services.supplier_prompt_resolver import SupplierPromptResolution
from src.llm.prompt_composer.protected_prompt_contract import (
    PROTECTED_PROMPT_CONTRACT_KEY,
    PROTECTED_PROMPT_CONTRACT_VERSION,
)

_SUPPLIER_SECTION_HEADER = "--- SUPPLIER-SPECIFIC EDITABLE INSTRUCTIONS ---"
_SUPPLIER_SECTION_INTRO = (
    "The following instructions are supplier-specific operational guidance.\n"
    "They may refine identification priorities, label expectations, or supplier-specific naming behavior.\n"
    "They must not override the protected JSON output contract, schema, parser requirements, or provider rules."
)
_SUPPLIER_SECTION_FOOTER = "--- END SUPPLIER-SPECIFIC EDITABLE INSTRUCTIONS ---"

WARNING_EMPTY_SUPPLIER_INSTRUCTIONS = "EMPTY_SUPPLIER_INSTRUCTIONS"
WARNING_RESOLUTION_STATUS_ERROR = "RESOLUTION_STATUS_ERROR"


def compute_effective_prompt_hash(text: str) -> str:
    """SHA256 (hex) of ``text`` encoded as UTF-8 — deterministic, no timestamps."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _supplier_instruction_block(trimmed_instructions: str) -> str:
    return (
        f"{_SUPPLIER_SECTION_HEADER}\n"
        f"{_SUPPLIER_SECTION_INTRO}\n\n"
        f"{trimmed_instructions}\n"
        f"{_SUPPLIER_SECTION_FOOTER}"
    )


@dataclass(frozen=True)
class EffectivePromptComposerInput:
    """Already-resolved inputs for composition (E3). No I/O."""

    protected_prompt_text: str
    provider_name: str | None
    model_name: str | None
    supplier_resolution: SupplierPromptResolution | None = None
    inventory_id: str | None = None
    aisle_id: str | None = None
    reference_source: str | None = None
    reference_image_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class EffectivePromptComposition:
    """Auditable result of effective prompt assembly (E3)."""

    effective_prompt_text: str
    effective_prompt_hash: str
    protected_prompt_contract_key: str
    protected_prompt_contract_version: str
    provider_name: str | None
    model_name: str | None
    supplier_prompt_config_id: str | None
    supplier_prompt_config_version: int | None
    supplier_instructions_applied: bool
    fallback_used: bool
    fallback_reason: str | None
    reference_source: str | None
    reference_image_ids: tuple[str, ...]
    sections: tuple[str, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)


class EffectivePromptComposer:
    """Compose protected hybrid text + optional supplier section; metadata for audit (E3)."""

    def compose(self, inp: EffectivePromptComposerInput) -> EffectivePromptComposition:
        base = inp.protected_prompt_text
        resolution = inp.supplier_resolution

        if resolution is None:
            text = base
            return self._finalize(
                text=text,
                inp=inp,
                supplier_instructions_applied=False,
                fallback_used=False,
                fallback_reason=None,
                supplier_prompt_config_id=None,
                supplier_prompt_config_version=None,
                sections=("protected_hybrid_base",),
                warnings=(),
            )

        if resolution.resolution_status == "error":
            err_warnings: tuple[str, ...] = tuple(resolution.warnings) + (WARNING_RESOLUTION_STATUS_ERROR,)
            if resolution.error_code:
                err_warnings = err_warnings + (f"RESOLUTION_ERROR_CODE:{resolution.error_code}",)
            return self._finalize(
                text=base,
                inp=inp,
                supplier_instructions_applied=False,
                fallback_used=True,
                fallback_reason=None,
                supplier_prompt_config_id=resolution.supplier_prompt_config_id,
                supplier_prompt_config_version=resolution.supplier_prompt_config_version,
                sections=("protected_hybrid_base",),
                warnings=err_warnings,
            )

        if resolution.resolution_status == "fallback":
            return self._finalize(
                text=base,
                inp=inp,
                supplier_instructions_applied=False,
                fallback_used=True,
                fallback_reason=resolution.fallback_reason,
                supplier_prompt_config_id=resolution.supplier_prompt_config_id,
                supplier_prompt_config_version=resolution.supplier_prompt_config_version,
                sections=("protected_hybrid_base",),
                warnings=resolution.warnings,
            )

        # resolution_status == "resolved"
        trimmed = (resolution.editable_instructions or "").strip()
        if not trimmed:
            w = resolution.warnings + (WARNING_EMPTY_SUPPLIER_INSTRUCTIONS,)
            return self._finalize(
                text=base,
                inp=inp,
                supplier_instructions_applied=False,
                fallback_used=False,
                fallback_reason=None,
                supplier_prompt_config_id=resolution.supplier_prompt_config_id,
                supplier_prompt_config_version=resolution.supplier_prompt_config_version,
                sections=("protected_hybrid_base",),
                warnings=w,
            )

        composed = f"{base.rstrip()}\n\n{_supplier_instruction_block(trimmed)}"
        return self._finalize(
            text=composed,
            inp=inp,
            supplier_instructions_applied=True,
            fallback_used=False,
            fallback_reason=None,
            supplier_prompt_config_id=resolution.supplier_prompt_config_id,
            supplier_prompt_config_version=resolution.supplier_prompt_config_version,
            sections=("protected_hybrid_base", "supplier_specific_editable"),
            warnings=resolution.warnings,
        )

    def _finalize(
        self,
        *,
        text: str,
        inp: EffectivePromptComposerInput,
        supplier_instructions_applied: bool,
        fallback_used: bool,
        fallback_reason: str | None,
        supplier_prompt_config_id: str | None,
        supplier_prompt_config_version: int | None,
        sections: tuple[str, ...],
        warnings: tuple[str, ...],
    ) -> EffectivePromptComposition:
        return EffectivePromptComposition(
            effective_prompt_text=text,
            effective_prompt_hash=compute_effective_prompt_hash(text),
            protected_prompt_contract_key=PROTECTED_PROMPT_CONTRACT_KEY,
            protected_prompt_contract_version=PROTECTED_PROMPT_CONTRACT_VERSION,
            provider_name=inp.provider_name,
            model_name=inp.model_name,
            supplier_prompt_config_id=supplier_prompt_config_id,
            supplier_prompt_config_version=supplier_prompt_config_version,
            supplier_instructions_applied=supplier_instructions_applied,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            reference_source=inp.reference_source,
            reference_image_ids=inp.reference_image_ids,
            sections=sections,
            warnings=warnings,
        )
