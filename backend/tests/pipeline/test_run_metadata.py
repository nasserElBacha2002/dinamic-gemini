"""Tests for run metadata (visual_reference_context) — v3.2.4 Phase 5."""

from __future__ import annotations

import pytest

from src.pipeline.ports.analysis_provider import (
    PROVIDER_METADATA_KEY_VISUAL_REFERENCE_COUNT,
    PROVIDER_METADATA_KEY_VISUAL_REFERENCES_CONSUMED,
)
from src.pipeline.run_metadata import (
    RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT,
    build_run_metadata,
    build_visual_reference_context,
)


def test_build_visual_reference_context_no_refs() -> None:
    """Case 1: No visual references — resolved=False, reference_ids=[], provider_consumed=False."""
    block = build_visual_reference_context(
        analysis_context=None,
        provider_metadata=None,
    )
    assert block["resolved"] is False
    assert block["reference_ids"] == []
    assert block["resolved_count"] == 0
    assert block["provider_consumed"] is False
    assert block["provider_consumed_count"] == 0


def test_build_visual_reference_context_empty_refs() -> None:
    """Empty visual_references list — same as no refs."""
    block = build_visual_reference_context(
        analysis_context={"visual_references": [], "instructions": []},
        provider_metadata={},
    )
    assert block["resolved"] is False
    assert block["reference_ids"] == []
    assert block["resolved_count"] == 0
    assert block["provider_consumed"] is False
    assert block["provider_consumed_count"] == 0


def test_build_visual_reference_context_resolved_not_consumed() -> None:
    """Case 3: References resolved but provider did not consume."""
    analysis_context = {
        "visual_references": [
            {"reference_id": "ref-1", "source_path": "inv/refs/ref-1.jpg", "mime_type": "image/jpeg"},
            {"reference_id": "ref-2", "source_path": "inv/refs/ref-2.jpg", "mime_type": "image/jpeg"},
        ],
        "instructions": ["Use as context."],
    }
    provider_metadata = {
        PROVIDER_METADATA_KEY_VISUAL_REFERENCES_CONSUMED: False,
        PROVIDER_METADATA_KEY_VISUAL_REFERENCE_COUNT: 0,
    }
    block = build_visual_reference_context(analysis_context, provider_metadata)
    assert block["resolved"] is True
    assert block["reference_ids"] == ["ref-1", "ref-2"]
    assert block["resolved_count"] == 2
    assert block["provider_consumed"] is False
    assert block["provider_consumed_count"] == 0


def test_build_visual_reference_context_resolved_and_consumed() -> None:
    """Case 2: References resolved and provider consumed them."""
    analysis_context = {
        "visual_references": [
            {"reference_id": "r1", "source_path": "inv/refs/r1.jpg", "mime_type": "image/jpeg"},
            {"reference_id": "r2", "source_path": "inv/refs/r2.jpg", "mime_type": "image/jpeg"},
        ],
        "instructions": [],
    }
    provider_metadata = {
        PROVIDER_METADATA_KEY_VISUAL_REFERENCES_CONSUMED: True,
        PROVIDER_METADATA_KEY_VISUAL_REFERENCE_COUNT: 2,
    }
    block = build_visual_reference_context(analysis_context, provider_metadata)
    assert block["resolved"] is True
    assert block["reference_ids"] == ["r1", "r2"]
    assert block["resolved_count"] == 2
    assert block["provider_consumed"] is True
    assert block["provider_consumed_count"] == 2


def test_build_visual_reference_context_partial_consumed() -> None:
    """Resolved 3 refs, provider consumed 2 (e.g. one file missing)."""
    analysis_context = {
        "visual_references": [
            {"reference_id": "a"},
            {"reference_id": "b"},
            {"reference_id": "c"},
        ],
    }
    provider_metadata = {
        PROVIDER_METADATA_KEY_VISUAL_REFERENCES_CONSUMED: True,
        PROVIDER_METADATA_KEY_VISUAL_REFERENCE_COUNT: 2,
    }
    block = build_visual_reference_context(analysis_context, provider_metadata)
    assert block["resolved"] is True
    assert block["reference_ids"] == ["a", "b", "c"]
    assert block["resolved_count"] == 3
    assert block["provider_consumed"] is True
    assert block["provider_consumed_count"] == 2


def test_build_visual_reference_context_sanitizes_inconsistent_provider_metadata() -> None:
    """provider_consumed=False with count>0 → provider_consumed_count forced to 0; count>resolved_count → clamped."""
    analysis_context = {
        "visual_references": [{"reference_id": "r1"}, {"reference_id": "r2"}],
    }
    # Inconsistent: consumed=False but count=2 → sanitizer forces count to 0
    provider_metadata = {
        PROVIDER_METADATA_KEY_VISUAL_REFERENCES_CONSUMED: False,
        PROVIDER_METADATA_KEY_VISUAL_REFERENCE_COUNT: 2,
    }
    block = build_visual_reference_context(analysis_context, provider_metadata)
    assert block["resolved"] is True
    assert block["resolved_count"] == 2
    assert block["provider_consumed"] is False
    assert block["provider_consumed_count"] == 0

    # Inconsistent: consumed=True but count=10 > resolved_count=2 → clamped to 2
    provider_metadata2 = {
        PROVIDER_METADATA_KEY_VISUAL_REFERENCES_CONSUMED: True,
        PROVIDER_METADATA_KEY_VISUAL_REFERENCE_COUNT: 10,
    }
    block2 = build_visual_reference_context(analysis_context, provider_metadata2)
    assert block2["provider_consumed_count"] == 2


def test_build_run_metadata_structure() -> None:
    """build_run_metadata returns dict with visual_reference_context key."""
    out = build_run_metadata(
        analysis_context={"visual_references": [{"reference_id": "x"}]},
        provider_metadata={PROVIDER_METADATA_KEY_VISUAL_REFERENCES_CONSUMED: True, PROVIDER_METADATA_KEY_VISUAL_REFERENCE_COUNT: 1},
    )
    assert RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT in out
    vrc = out[RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT]
    assert vrc["resolved"] is True
    assert vrc["reference_ids"] == ["x"]
    assert vrc["provider_consumed"] is True
    assert vrc["provider_consumed_count"] == 1
