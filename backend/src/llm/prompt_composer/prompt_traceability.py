"""
Phase 6 — prompt composition traceability (JSON-serializable, audit-friendly metadata).

**Persistence vs execution logs**

- The full ``prompt_composition`` dict (including ``base_prompt_text`` and ``final_prompt_text``) is
  attached to ``LLMRequest.metadata`` and, after analysis, copied into job ``run_metadata`` for
  **audit replay and debugging**. That choice is intentional for Phase 6; a later phase may trim
  or externalize large text while keeping hashes.
- **Execution logs** (``ExecutionLogWriter``) intentionally omit full prompt bodies by default and
  only record hashes, lengths, and a redacted summary — see
  ``prompt_composition_summary_for_execution_log`` and ``Settings.debug_log_full_analysis_prompt``
  (env ``DEBUG_LOG_FULL_ANALYSIS_PROMPT``) for optional full ``prompt_text`` in the log payload.

Attached to ``LLMRequest.metadata`` and job ``run_metadata`` without changing prompt text.

**Semantics: profile / key vs version vs hash (do not conflate)**

- **Profile / prompt family (what text template is used):** In composition metadata this is
  ``profile_name`` (the hybrid registry key used for the composed **default** body; aisle analysis
  hard-binds ``global_v22``). ``job_prompt_key`` and ``settings_hybrid_prompt_key`` record
  configuration hints only. Top-level job ``run_metadata["prompt_key"]`` prefers the composed profile
  when present. None of this is the same as Phase 7 ``prompt_version``.
- **``prompt_version`` (Phase 7, optional):** A logical label for traceability, comparison, and
  future A/B work. It **does not** select prompt bodies, **does not** change ``DEFAULT_HYBRID_PROMPT_PROFILE``,
  **does not** alter prompt text, and **is not** an input to ``prompt_hash`` / ``base_prompt_hash``.
- **``prompt_hash`` / ``base_prompt_hash``:** SHA-256 of UTF-8 ``final_prompt_text`` / ``base_prompt_text``
  only — exact fingerprints of the strings sent or built.

**Top-level ``run_metadata["prompt_version"]`` (legacy)** in ``hybrid_inventory_pipeline`` is the
string ``{prompt_key}@v2.1`` for job ``result_json``. That is **not** the same field as
``run_metadata["prompt_composition"]["prompt_version"]`` (Phase 7 optional label).
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Stable key on ``LLMRequest.metadata`` and job-level run_metadata (optional block).
LLM_METADATA_KEY_PROMPT_COMPOSITION = "prompt_composition"
# Pre-Phase 10 — comparison parity + canonical identity (also mirrored inside ``prompt_composition``).
LLM_METADATA_KEY_PROMPT_PARITY_MODE = "prompt_parity_mode"
LLM_IDENTITY_METADATA_KEY = "llm_identity"

# E6.1 — only these keys may appear under ``effective_prompt`` in execution log summaries.
# Blocks accidental leakage of prompt bodies or future ad-hoc keys from the full composition dict.
EFFECTIVE_PROMPT_EXECUTION_LOG_KEYS = frozenset(
    {
        "protected_prompt_contract_key",
        "protected_prompt_contract_version",
        "effective_prompt_hash",
        "supplier_prompt_config_id",
        "supplier_prompt_config_version",
        "supplier_instructions_applied",
        "fallback_used",
        "fallback_reason",
        "resolution_status",
        "resolution_error_code",
        "reference_source",
        "reference_image_ids",
        "warnings",
        "sections",
    }
)

PROMPT_COMPOSITION_SCHEMA_VERSION = "prompt_composition_v1"

# --- composition_steps: lightweight ordered audit trail (not a workflow engine) ---
# Each entry is a dict with required key ``step`` (one of the constants below). Optional keys
# document inputs/outputs for humans and future tooling; keep shapes stable when extending.
COMPOSITION_STEP_RESOLVE_PROFILE = "resolve_profile"
COMPOSITION_STEP_NORMALIZE_PIPELINE_PROVIDER = "normalize_pipeline_provider"
COMPOSITION_STEP_COMPOSE_HYBRID_BASE = "compose_hybrid_base"
COMPOSITION_STEP_ENRICH_IMAGE_IDS = "enrich_image_ids"
COMPOSITION_STEP_PROMPT_PARITY_MODE = "prompt_parity_mode"
# Phase E4: optional supplier-editable block appended after protected hybrid + enrichments (metadata only).
COMPOSITION_STEP_EFFECTIVE_SUPPLIER_PROMPT = "effective_supplier_prompt"


def sha256_utf8(text: str) -> str:
    """SHA-256 hex digest of UTF-8 encoded text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class PromptCompositionMetadata:
    """
    Single JSON-friendly record for hybrid analysis prompt traceability.

    **Boundary: prompt construction vs execution layer**

    - **Prompt construction** (filled in ``pipeline.services.hybrid_analysis_prompt`` via
      ``build_prompt_composition_dict``): profile resolution, pipeline provider key used for
      overlay/compose, config keys that influenced the profile, base/final prompt text, hashes,
      enrichments, ``composition_steps``, timestamp. ``resolved_llm_provider_key`` and ``model_name``
      are present as fields but empty/None until the execution step below — the datatype is one
      blob for practical JSON attachment.
    - **Execution-layer enrichment** (filled in ``HybridGlobalAnalysisStrategy`` via
      ``apply_execution_layer_to_composition``): registry-resolved LLM provider key and concrete
      model name for the call. These do not change prompt *text*; they describe *who ran* the
      prompt.

    Consumers should treat the whole dict as the Phase 6+7 contract while understanding which keys
    are authoritative for “how the prompt was built” vs “how it was executed”.

    **Phase 7 — ``prompt_version``:** Optional logical label (e.g. ``"v1"``, ``"2026-04-10"``) for
    audit and future comparison. It is **not** the profile selector (that is ``profile_name`` /
    ``job_prompt_key`` / ``hybrid_prompt``), **not** derived from ``prompt_hash``, does **not** affect
    prompt text, and is **not** used to pick prompt content in this phase.

    **Pre-Phase 10 — ``prompt_parity_mode``:** When true, hybrid **base** text for OpenAI uses the
    ``default`` fragment (same as Gemini/Claude/DeepSeek) for fair comparison; recorded for audit.

    **``llm_identity``:** Canonical ``provider_name`` + ``model_name`` (set in
    ``apply_execution_layer_to_composition``); complements legacy per-vendor request metadata keys.
    """

    schema_version: str
    profile_name: str
    pipeline_provider_key: str
    resolved_llm_provider_key: str
    model_name: str | None
    job_prompt_key: str | None
    settings_hybrid_prompt_key: str | None
    prompt_version: str | None
    prompt_parity_mode: bool
    llm_identity: dict[str, Any] | None
    base_prompt_text: str
    final_prompt_text: str
    enrichments_applied: list[str]
    composition_steps: list[dict[str, Any]]
    prompt_hash: str
    base_prompt_hash: str
    timestamp: str

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _PromptCompositionBuildArgs:
    """Internal bundle for :func:`build_prompt_composition_dict` (B8.5 PLR0913)."""

    profile_name: str
    pipeline_provider_key: str
    base_prompt_text: str
    final_prompt_text: str
    enrichments_applied: Sequence[str]
    composition_steps: Sequence[dict[str, Any]]
    job_prompt_key: str | None
    settings_hybrid_prompt_key: str | None
    prompt_version: str | None = None
    prompt_parity_mode: bool = False
    resolved_llm_provider_key: str = ""
    model_name: str | None = None
    timestamp: str | None = None


def _build_prompt_composition_dict_impl(args: _PromptCompositionBuildArgs) -> dict[str, Any]:
    ts = args.timestamp or datetime.now(timezone.utc).isoformat()
    meta = PromptCompositionMetadata(
        schema_version=PROMPT_COMPOSITION_SCHEMA_VERSION,
        profile_name=args.profile_name,
        pipeline_provider_key=args.pipeline_provider_key,
        resolved_llm_provider_key=(args.resolved_llm_provider_key or "").strip().lower(),
        model_name=(
            str(args.model_name).strip()
            if args.model_name and str(args.model_name).strip()
            else None
        ),
        job_prompt_key=(
            str(args.job_prompt_key).strip()
            if args.job_prompt_key and str(args.job_prompt_key).strip()
            else None
        ),
        settings_hybrid_prompt_key=(
            str(args.settings_hybrid_prompt_key).strip()
            if args.settings_hybrid_prompt_key and str(args.settings_hybrid_prompt_key).strip()
            else None
        ),
        prompt_version=(
            args.prompt_version.strip()
            if isinstance(args.prompt_version, str) and args.prompt_version.strip()
            else None
        ),
        prompt_parity_mode=bool(args.prompt_parity_mode),
        llm_identity=None,
        base_prompt_text=args.base_prompt_text,
        final_prompt_text=args.final_prompt_text,
        enrichments_applied=list(args.enrichments_applied),
        composition_steps=list(args.composition_steps),
        prompt_hash=sha256_utf8(args.final_prompt_text),
        base_prompt_hash=sha256_utf8(args.base_prompt_text),
        timestamp=ts,
    )
    return meta.to_json_dict()


def build_prompt_composition_dict(  # noqa: PLR0913 — stable Phase 6 API surface
    *,
    profile_name: str,
    pipeline_provider_key: str,
    base_prompt_text: str,
    final_prompt_text: str,
    enrichments_applied: Sequence[str],
    composition_steps: Sequence[dict[str, Any]],
    job_prompt_key: str | None,
    settings_hybrid_prompt_key: str | None,
    prompt_version: str | None = None,
    prompt_parity_mode: bool = False,
    resolved_llm_provider_key: str = "",
    model_name: str | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """
    Build the **prompt-construction** portion of ``prompt_composition`` (hashes from prompt strings).

    ``prompt_version`` is optional traceability metadata only; it does not affect which profile is
    resolved, does not change prompt strings, and does not affect ``prompt_hash`` /
    ``base_prompt_hash``.

    Leaves ``resolved_llm_provider_key`` / ``model_name`` empty or None until
    ``apply_execution_layer_to_composition`` runs in the analysis strategy. Full ``base_prompt_text``
    and ``final_prompt_text`` are included on purpose for job-level audit (see module docstring).
    """
    return _build_prompt_composition_dict_impl(
        _PromptCompositionBuildArgs(
            profile_name=profile_name,
            pipeline_provider_key=pipeline_provider_key,
            base_prompt_text=base_prompt_text,
            final_prompt_text=final_prompt_text,
            enrichments_applied=enrichments_applied,
            composition_steps=composition_steps,
            job_prompt_key=job_prompt_key,
            settings_hybrid_prompt_key=settings_hybrid_prompt_key,
            prompt_version=prompt_version,
            prompt_parity_mode=prompt_parity_mode,
            resolved_llm_provider_key=resolved_llm_provider_key,
            model_name=model_name,
            timestamp=timestamp,
        )
    )


def _prompt_comp_validate_required(meta: Mapping[str, Any]) -> tuple[list[str], str | None]:
    errors: list[str] = []

    sv = meta.get("schema_version")
    if not isinstance(sv, str) or not sv.strip():
        errors.append("schema_version must be a non-empty string")

    pn = meta.get("profile_name")
    if not isinstance(pn, str) or not pn.strip():
        errors.append("profile_name must be a non-empty string")

    ppk = meta.get("pipeline_provider_key")
    if not isinstance(ppk, str) or not ppk.strip():
        errors.append("pipeline_provider_key must be a non-empty string")

    enrich = meta.get("enrichments_applied")
    if not isinstance(enrich, list):
        errors.append("enrichments_applied must be a list")

    steps = meta.get("composition_steps")
    if not isinstance(steps, list):
        errors.append("composition_steps must be a list")

    final = meta.get("final_prompt_text")
    if not isinstance(final, str):
        errors.append("final_prompt_text must be a string")
        return errors, None
    return errors, final


def _prompt_comp_validate_hashes(meta: Mapping[str, Any], final: str) -> list[str]:
    errors: list[str] = []
    want_ph = meta.get("prompt_hash")
    if isinstance(want_ph, str) and want_ph:
        if sha256_utf8(final) != want_ph:
            errors.append("prompt_hash does not match final_prompt_text")

    base = meta.get("base_prompt_text")
    if isinstance(base, str):
        want_bh = meta.get("base_prompt_hash")
        if isinstance(want_bh, str) and want_bh:
            if sha256_utf8(base) != want_bh:
                errors.append("base_prompt_hash does not match base_prompt_text")
    return errors


def validate_prompt_composition_dict(meta: Mapping[str, Any]) -> list[str]:
    """
    Return human-readable validation errors; empty list means invariants hold.

    Lightweight structural checks plus SHA-256 consistency and enrichment/base/final alignment.
    """
    errors, final = _prompt_comp_validate_required(meta)
    if final is None:
        return errors

    errors.extend(_prompt_comp_validate_hashes(meta, final))

    enrich = meta.get("enrichments_applied")
    base = meta.get("base_prompt_text")
    if isinstance(enrich, list) and len(enrich) == 0:
        if isinstance(base, str) and final != base:
            errors.append("enrichments_applied is empty but base_prompt_text != final_prompt_text")

    return errors


def apply_execution_layer_to_composition(
    composition: dict[str, Any],
    *,
    resolved_llm_provider_key: str,
    model_name: str | None,
) -> dict[str, Any]:
    """
    Shallow-copy ``composition`` and set **execution-layer** fields.

    The registry-resolved provider key and job model name describe the executor invocation; they
    are merged into the same dict shape as prompt-construction metadata so one blob can ride on
    ``LLMRequest.metadata`` and ``run_metadata`` without a second top-level key.
    """
    out = dict(composition)
    rpk = (resolved_llm_provider_key or "").strip().lower()
    mn = str(model_name).strip() if model_name and str(model_name).strip() else None
    out["resolved_llm_provider_key"] = rpk
    out["model_name"] = mn
    out["llm_identity"] = {"provider_name": rpk, "model_name": mn}
    errs = validate_prompt_composition_dict(out)
    for msg in errs:
        logger.warning("prompt_composition validation: %s", msg)
    return out


def prompt_composition_summary_for_execution_log(
    full_composition: Mapping[str, Any],
    *,
    final_prompt_char_len: int,
) -> dict[str, Any]:
    """
    Redacted subset of ``prompt_composition`` for execution logs (no full prompt bodies).

    Keeps hashes, profile/provider fields, enrichments, steps, and character lengths so log readers
    align with persisted metadata without duplicating large strings in JSONL.
    """
    base_text = full_composition.get("base_prompt_text")
    base_len = len(base_text) if isinstance(base_text, str) else 0
    out: dict[str, Any] = {
        "schema_version": full_composition.get("schema_version"),
        "profile_name": full_composition.get("profile_name"),
        "pipeline_provider_key": full_composition.get("pipeline_provider_key"),
        "resolved_llm_provider_key": full_composition.get("resolved_llm_provider_key"),
        "model_name": full_composition.get("model_name"),
        "job_prompt_key": full_composition.get("job_prompt_key"),
        "settings_hybrid_prompt_key": full_composition.get("settings_hybrid_prompt_key"),
        "enrichments_applied": full_composition.get("enrichments_applied"),
        "composition_steps": full_composition.get("composition_steps"),
        "prompt_hash": full_composition.get("prompt_hash"),
        "base_prompt_hash": full_composition.get("base_prompt_hash"),
        "final_prompt_char_len": final_prompt_char_len,
        "base_prompt_char_len": base_len,
        "timestamp": full_composition.get("timestamp"),
    }
    # Phase 7 label only; omit from log payload when unset (noise / backward compat).
    pv = full_composition.get("prompt_version")
    if isinstance(pv, str) and pv.strip():
        out["prompt_version"] = pv.strip()
    if full_composition.get("prompt_parity_mode") is True:
        out["prompt_parity_mode"] = True
    lid = full_composition.get("llm_identity")
    if isinstance(lid, dict) and lid:
        out["llm_identity"] = dict(lid)
    # E6 / E6.1: surface allowlisted ``effective_prompt`` keys only (no prompt bodies).
    eff = full_composition.get("effective_prompt")
    if isinstance(eff, dict) and eff:
        safe_eff = {
            key: value
            for key, value in eff.items()
            if key in EFFECTIVE_PROMPT_EXECUTION_LOG_KEYS
        }
        if safe_eff:
            out["effective_prompt"] = safe_eff
    return out
