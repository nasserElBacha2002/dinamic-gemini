"""Phase 3 — per-provider model metadata mapping for ``LLMRequest.metadata``."""

from __future__ import annotations

from src.pipeline.services.provider_llm_request_metadata import (
    apply_job_model_name_to_llm_request_metadata,
)


def test_apply_job_model_name_sets_vendor_specific_keys() -> None:
    meta: dict = {}
    out = apply_job_model_name_to_llm_request_metadata(
        resolved_provider_key="openai",
        job_model_name=" gpt-4o ",
        metadata=meta,
    )
    assert out == "gpt-4o"
    assert meta["openai_model_name"] == "gpt-4o"
    assert "gemini_model_name" not in meta


def test_apply_job_model_name_empty_returns_none_and_does_not_mutate() -> None:
    meta: dict = {"existing": 1}
    assert (
        apply_job_model_name_to_llm_request_metadata(
            resolved_provider_key="gemini",
            job_model_name=None,
            metadata=meta,
        )
        is None
    )
    assert "gemini_model_name" not in meta
    assert meta == {"existing": 1}


def test_apply_job_model_name_unknown_provider_key_returns_model_without_metadata_mutation() -> (
    None
):
    """Unregistered logical keys still expose the job model for composition but skip legacy keys."""
    meta: dict = {}
    out = apply_job_model_name_to_llm_request_metadata(
        resolved_provider_key="future_vendor",
        job_model_name="some-model",
        metadata=meta,
    )
    assert out == "some-model"
    assert meta == {}
