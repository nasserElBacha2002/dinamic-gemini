"""
AnalysisStage — delegate to AnalysisProvider and return structured result (v2.3.C).

Performs the global analysis call only; no entity parsing.
v3.2.4 Phase 4: passes through provider_metadata (visual reference usage) for callers to persist.
Phase 5: normalizes ``parsed_json`` (e.g. OpenAI quantity aliases) before entity resolution.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from src.llm.errors import LLMProviderError
from src.llm.normalization.entity_normalizer import normalize_llm_response
from src.pipeline.context.run_context import RunContext
from src.pipeline.ports.analysis_provider import AnalysisProvider, AnalysisResult
from src.pipeline.stages.frame_acquisition_stage import AcquiredFrames

_OPENAI_CANONICAL_ENTITY_KEYS: tuple[str, ...] = (
    "source_image_id",
    "position_barcode",
    "internal_code",
    "product_label_quantity",
    "product_label_bbox",
)


def _log_analysis_analyze_failure(context: RunContext, exc: LLMProviderError) -> None:
    """Structured warning when ``analyze`` raises (same keys/previews as previous inline block)."""
    log = getattr(context, "logger", None)
    if log is None:
        return
    d = dict(exc.details) if exc.details else {}
    log.warning(
        "analysis_stage analyze_failed job_id=%s code=%s message=%s "
        "provider_details_keys=%s text_preview=%r",
        context.job_id,
        exc.code,
        (exc.message or str(exc))[:400],
        sorted(d.keys()),
        (d.get("text_preview") or d.get("parse_failure") or "")[:240],
    )


def _count_product_label_quantity_set(entities: list[Any]) -> int:
    return sum(
        1
        for ent in entities
        if isinstance(ent, dict) and ent.get("product_label_quantity") is not None
    )


def _openai_canonical_key_presence_counts(entities: list[Any]) -> dict[str, int]:
    """Per-key counts of non-empty canonical entity fields (OpenAI debug diagnostics)."""
    presence: dict[str, int] = {k: 0 for k in _OPENAI_CANONICAL_ENTITY_KEYS}
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        for key in _OPENAI_CANONICAL_ENTITY_KEYS:
            val = ent.get(key)
            if val is None:
                continue
            if isinstance(val, str) and not val.strip():
                continue
            presence[key] += 1
    return presence


def _log_analysis_post_normalize(
    context: RunContext, provider_name: str, parsed: dict[str, Any]
) -> None:
    """Info log + optional DEBUG diagnostics for normalized entities (unchanged behavior)."""
    log = getattr(context, "logger", None)
    if log is None:
        return
    ents = parsed.get("entities")
    n_ent = len(ents) if isinstance(ents, list) else 0
    log.info(
        "analysis_stage ok job_id=%s provider=%s normalized_entities=%d",
        context.job_id,
        provider_name,
        n_ent,
    )
    if not log.isEnabledFor(logging.DEBUG) or not isinstance(ents, list):
        return
    with_plq = _count_product_label_quantity_set(ents)
    log.debug(
        "analysis_stage post_normalize: provider=%s entities=%d product_label_quantity_set=%d",
        provider_name,
        len(ents),
        with_plq,
    )
    provider_norm = (provider_name or "").strip().lower()
    if provider_norm == "openai":
        after_presence = _openai_canonical_key_presence_counts(ents)
        log.debug(
            "analysis_stage openai_canonical_key_presence_after_normalize entities=%d presence=%s",
            len(ents),
            after_presence,
        )


@dataclass
class AnalysisStageResult:
    """Output of AnalysisStage: parsed analysis payload for entity resolution."""

    parsed_json: dict[str, Any]
    provider_name: str
    provider_metadata: dict[str, Any] | None = None
    # Phase 6: pass-through of AnalysisResult.prompt_composition for run_metadata persistence.
    prompt_composition: dict[str, Any] | None = None
    # Phase 9: pass-through of provider-agnostic usage+pricing snapshot for run_metadata persistence.
    llm_cost_snapshot: dict[str, Any] | None = None


class AnalysisStage:
    """Stage: call AnalysisProvider.analyze and return result; progress is caller's responsibility."""

    def __init__(self, analysis_provider: AnalysisProvider) -> None:
        self._analysis_provider = analysis_provider

    def run(self, context: RunContext, data: AcquiredFrames) -> AnalysisStageResult:
        """
        Invoke analysis provider; return parsed JSON and provider name.

        Raises:
            LLMProviderError (from provider): When the provider fails (caller maps to exit code 1).
        """
        try:
            result: AnalysisResult = self._analysis_provider.analyze(
                context,
                data.frames_nd,
                data.frame_paths,
                data.frame_refs,
                data.metadata,
            )
        except LLMProviderError as e:
            _log_analysis_analyze_failure(context, e)
            raise

        parsed = normalize_llm_response(result.parsed_json, result.provider_name)
        _log_analysis_post_normalize(context, result.provider_name, parsed)

        return AnalysisStageResult(
            parsed_json=parsed,
            provider_name=result.provider_name,
            provider_metadata=result.provider_metadata,
            prompt_composition=result.prompt_composition,
            llm_cost_snapshot=result.llm_cost_snapshot,
        )
