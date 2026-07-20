"""Phase 5 — versioned prompt for single-image external label analysis."""

from __future__ import annotations

EXTERNAL_FALLBACK_PROMPT_KEY = "external_fallback_single_label"
EXTERNAL_FALLBACK_PROMPT_VERSION = "1.0.0"

EXTERNAL_FALLBACK_PROMPT_TEXT = """You analyze exactly ONE inventory label image.

Rules (mandatory):
- This image represents at most ONE physical label / position.
- Return at most one internal_code and one quantity.
- Never invent a code or a quantity. If evidence is insufficient, say so.
- If multiple distinct labels/products are visible, mark the result as AMBIGUOUS.
- Do not default quantity to 1.
- Prefer explicit labeled fields over guessing.

Respond with ONLY valid JSON (no markdown) using this schema:
{
  "status": "VALID" | "INVALID" | "AMBIGUOUS" | "NO_RESULT",
  "internal_code": string | null,
  "quantity": integer | null,
  "confidence": number | null,
  "warnings": string[],
  "reason": string | null
}
"""


def build_external_fallback_prompt(*, client_rules: dict | None = None) -> str:
    """Compose the versioned prompt; optional client rules are appended as hints only."""
    parts = [EXTERNAL_FALLBACK_PROMPT_TEXT]
    if client_rules:
        prefer = client_rules.get("prefer_ean_as_internal_code")
        if prefer is True:
            parts.append(
                "\nClient hint: when both EAN and an internal article code are present, "
                "prefer the EAN as internal_code."
            )
        elif prefer is False:
            parts.append(
                "\nClient hint: when both EAN and an internal article code are present, "
                "prefer the labeled internal article code over a bare EAN."
            )
    return "".join(parts)


__all__ = [
    "EXTERNAL_FALLBACK_PROMPT_KEY",
    "EXTERNAL_FALLBACK_PROMPT_TEXT",
    "EXTERNAL_FALLBACK_PROMPT_VERSION",
    "build_external_fallback_prompt",
]
