"""Defensive parsing of execution_log.jsonl for run auditability (Phase H1)."""

from __future__ import annotations

from typing import Any

ANALYSIS_STAGE = "AnalysisStage"
ANALYSIS_REQUEST_PREPARED = "Analysis request prepared"
ANALYSIS_REQUEST_EVENT_TYPE = "analysis_request"


def find_last_analysis_request_prepared_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the last matching analysis request event payload root, or ``None``.

    Matching rule (stable keys first):
    - ``stage == AnalysisStage``
    - ``message == "Analysis request prepared"`` (pipeline contract)
    - ``payload.event_type == "analysis_request"`` when payload exists
    """
    last: dict[str, Any] | None = None
    for evt in events:
        if not isinstance(evt, dict):
            continue
        if evt.get("stage") != ANALYSIS_STAGE:
            continue
        if evt.get("message") != ANALYSIS_REQUEST_PREPARED:
            continue
        payload = evt.get("payload")
        if not isinstance(payload, dict):
            continue
        if payload.get("event_type") != ANALYSIS_REQUEST_EVENT_TYPE:
            continue
        last = payload
    return last


def extract_prompt_composition_from_analysis_request(
    analysis_request_payload: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return ``payload["prompt_composition"]`` when it is a non-empty dict."""
    if not analysis_request_payload:
        return None
    raw = analysis_request_payload.get("prompt_composition")
    return raw if isinstance(raw, dict) and raw else None


def merge_effective_prompt_fields(composition: dict[str, Any] | None) -> dict[str, Any]:
    """Flatten allowlisted ``effective_prompt`` keys onto a dict for the read model."""
    out: dict[str, Any] = {}
    if not composition or not isinstance(composition, dict):
        return out
    eff = composition.get("effective_prompt")
    if not isinstance(eff, dict):
        return out
    for key in (
        "protected_prompt_contract_key",
        "protected_prompt_contract_version",
        "effective_prompt_hash",
        "supplier_prompt_config_id",
        "supplier_prompt_config_version",
        "fallback_used",
        "fallback_reason",
        "warnings",
        "reference_image_ids",
        "reference_source",
    ):
        if key in eff:
            out[key] = eff[key]
    return out
