"""
Phase E1 — **Protected hybrid prompt contract** (terminology + stable regression markers).

This module does **not** assemble prompts and is **not** imported by hot-path adapters to avoid
cycles. It exists so tests and audits share one definition of:

- **ProtectedSystemContractBlock** — hybrid ``default`` profile text in ``hybrid_profiles.PROMPTS``
  (e.g. ``global_v21`` / ``global_v21_b``) plus the Claude canonical entity contract string that is
  **appended** for Claude-family providers. This text is non–operator-editable and must not be
  replaced by supplier instructions (enforced in E3/E4+).

- **ProviderPromptRules** — overlay / wire rules applied in ``hybrid_resolution`` (OpenAI replacement
  fragment, Claude supplement, parity mode) and adapter-only strings such as OpenAI's JSON suffix.

**Stable keys (metadata only; do not change prompt wording):**

Changing ``PROTECTED_PROMPT_CONTRACT_KEY`` / ``PROTECTED_PROMPT_CONTRACT_VERSION`` is a deliberate
audit action when the protected *meaning* of the hybrid contract is versioned for persistence
(E6). They must not be confused with ``prompt_composition``'s Phase 7 ``prompt_version`` label.
"""

from __future__ import annotations

from typing import Final

# --- Audit / persistence identifiers (E6 may echo these on job metadata) ---
PROTECTED_PROMPT_CONTRACT_KEY: Final[str] = "hybrid_global_analysis_v21"
PROTECTED_PROMPT_CONTRACT_VERSION: Final[str] = "e1-1"

# --- Substrings that must remain present in ``compose_hybrid_base("global_v21", ...)`` outputs ---
# Chosen to be unlikely to appear in future *supplier* text while staying stable across refactors
# that preserve contract meaning. Prefer short, distinctive phrases from ``hybrid_profiles``.
#
# The OpenAI **replacement** fragment does not repeat every phrase from the Gemini-oriented
# ``default`` body (e.g. explicit ``model_entity_id`` / ``product_label_bbox`` lines). Shared markers
# must appear on **all** branches; ``default``-only markers apply when the resolved text is the
# default branch or default+Claude supplement.
HYBRID_V21_SHARED_CONTRACT_MARKERS: Final[tuple[str, ...]] = (
    "PALLET",
    "EMPTY_PALLET",
    "LOOSE_BOXES",
    "confidence",
)

HYBRID_V21_DEFAULT_BRANCH_MARKERS: Final[tuple[str, ...]] = (
    "model_entity_id",
    "product_label_bbox",
    "NORMALIZED coords",
)

# Present only when OpenAI overlay applies (provider_key == openai, parity off).
HYBRID_V21_OPENAI_OVERLAY_MARKERS: Final[tuple[str, ...]] = (
    "total_entities_detected",
    "Return valid JSON only",
)

# Present when Claude-family supplement is appended (see ``hybrid_resolution``).
HYBRID_V21_CLAUDE_SUPPLEMENT_MARKERS: Final[tuple[str, ...]] = (
    "CLAUDE JSON ENTITY CONTRACT",
    "entity_type",
)

# OpenAI adapter wire requirement (not part of hybrid base; **ProviderPromptRules**).
OPENAI_JSON_OBJECT_REQUIREMENT_MARKER: Final[str] = "single JSON object only (no markdown fences)"
