"""Unit tests for execution log parsing helpers used by run auditability."""

from __future__ import annotations

from src.application.services.run_auditability_execution_log import (
    extract_prompt_composition_from_analysis_request,
    find_last_analysis_request_prepared_event,
    merge_effective_prompt_fields,
)


def test_find_last_analysis_request_takes_last_of_multiple() -> None:
    events = [
        {
            "stage": "AnalysisStage",
            "message": "Analysis request prepared",
            "payload": {"event_type": "analysis_request", "prompt_composition": {"x": 1}},
        },
        {
            "stage": "AnalysisStage",
            "message": "Analysis request prepared",
            "payload": {
                "event_type": "analysis_request",
                "prompt_composition": {
                    "effective_prompt": {"effective_prompt_hash": "second"},
                },
            },
        },
    ]
    last = find_last_analysis_request_prepared_event(events)
    assert last is not None
    comp = extract_prompt_composition_from_analysis_request(last)
    assert comp is not None
    assert merge_effective_prompt_fields(comp).get("effective_prompt_hash") == "second"


def test_find_last_ignores_wrong_stage_or_message() -> None:
    events = [
        {"stage": "Pipeline", "message": "Job started", "payload": {"event_type": "analysis_request"}},
        {
            "stage": "AnalysisStage",
            "message": "Other",
            "payload": {"event_type": "analysis_request"},
        },
    ]
    assert find_last_analysis_request_prepared_event(events) is None
