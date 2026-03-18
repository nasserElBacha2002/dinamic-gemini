"""
Stage 2.3.B — Ports & Adapters: contract and adapter tests.

- Contract test: AnalysisProvider implementations return AnalysisResult with expected structure.
- Unit test: GeminiAnalysisProvider adapter returns AnalysisResult and integrates with pipeline (parse_entities).
- Verification: JobStoreRepositoryAdapter.create() returns the persisted record (matches get()).
"""

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from src.jobs.adapters.job_store_adapter import JobStoreRepositoryAdapter
from src.jobs.models import JobInput, JobRecord, JobStatus
from src.parsing.global_analysis_parser import parse_entities
from src.pipeline.adapters.gemini_analysis_provider import GeminiAnalysisProvider
from src.pipeline.context.run_context import RunContext
from src.pipeline.ports.analysis_provider import (
    AnalysisResult,
    AnalysisProvider,
    ProviderCapabilities,
    PROVIDER_METADATA_KEY_VISUAL_REFERENCE_COUNT,
    PROVIDER_METADATA_KEY_VISUAL_REFERENCES_AVAILABLE,
    PROVIDER_METADATA_KEY_VISUAL_REFERENCES_CONSUMED,
)


# --- Contract: any AnalysisProvider returns expected shape ---


class FakeAnalysisProvider:
    """Minimal implementation of AnalysisProvider for contract tests."""

    def __init__(self, parsed_json: dict, provider_name: str = "fake") -> None:
        self._parsed_json = parsed_json
        self._provider_name = provider_name

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(supports_visual_reference_context=False)

    def analyze(
        self,
        context: RunContext,
        frames_nd: list,
        frame_paths: list,
        frame_refs: list,
        metadata: dict,
    ) -> AnalysisResult:
        return AnalysisResult(
            parsed_json=self._parsed_json,
            provider_name=self._provider_name,
            provider_metadata={
                PROVIDER_METADATA_KEY_VISUAL_REFERENCES_AVAILABLE: False,
                PROVIDER_METADATA_KEY_VISUAL_REFERENCES_CONSUMED: False,
                PROVIDER_METADATA_KEY_VISUAL_REFERENCE_COUNT: 0,
            },
        )


def test_analysis_provider_contract_returns_analysis_result() -> None:
    """Any AnalysisProvider implementation must return AnalysisResult with parsed_json and provider_name."""
    fixture = {
        "total_entities_detected": 1,
        "entities": [{"model_entity_id": "e1", "entity_type": "PALLET"}],
    }
    provider: AnalysisProvider = FakeAnalysisProvider(parsed_json=fixture, provider_name="contract-test")
    settings = MagicMock()
    job_input = MagicMock()
    context = RunContext(
        job_id="j1",
        run_id="r1",
        workspace_path=Path("/tmp"),
        run_dir=Path("/tmp/j1/r1"),
        job_input=job_input,
        settings=settings,
        logger=MagicMock(),
    )
    result = provider.analyze(
        context=context,
        frames_nd=[],
        frame_paths=[],
        frame_refs=[],
        metadata={},
    )
    assert isinstance(result, AnalysisResult)
    assert result.provider_name == "contract-test"
    assert isinstance(result.parsed_json, dict)
    assert "total_entities_detected" in result.parsed_json
    assert "entities" in result.parsed_json
    assert isinstance(result.parsed_json["entities"], list)
    # Pipeline consumes via parse_entities
    entities = parse_entities(result.parsed_json, job_id="j1")
    assert len(entities) == 1


def test_gemini_analysis_provider_adapter_returns_analysis_result() -> None:
    """GeminiAnalysisProvider with FakeProvider returns AnalysisResult; parsed_json usable by parse_entities."""
    settings = MagicMock()
    settings.llm_provider = "fake"
    settings.fake_llm_fixture_path = None
    job_input = MagicMock()
    context = RunContext(
        job_id="j1",
        run_id="r1",
        workspace_path=Path("/tmp"),
        run_dir=Path("/tmp/j1/r1"),
        job_input=job_input,
        settings=settings,
        logger=MagicMock(),
    )
    adapter = GeminiAnalysisProvider()
    result = adapter.analyze(
        context=context,
        frames_nd=[np.zeros((100, 100, 3), dtype=np.uint8)],
        frame_paths=[Path("/tmp/f0.png")],
        frame_refs=["f0"],
        metadata={"frame_count": 1},
    )
    assert isinstance(result, AnalysisResult)
    assert result.provider_name == "fake"
    assert "total_entities_detected" in result.parsed_json
    assert "entities" in result.parsed_json
    entities = parse_entities(result.parsed_json, job_id="j1")
    assert isinstance(entities, list)
    # v3.2.4 Phase 4: provider_metadata present when no analysis_context
    assert result.provider_metadata is not None
    assert result.provider_metadata["visual_references_available"] is False
    assert result.provider_metadata["visual_references_consumed"] is False


def test_job_repository_create_returns_persisted_record(tmp_path: Path) -> None:
    """JobStoreRepositoryAdapter.create() returns the persisted record, not just the input."""
    base = tmp_path / "output"
    base.mkdir()
    adapter = JobStoreRepositoryAdapter(base)
    job_id = "job-create-verify"
    job_input = JobInput(
        video_path="/tmp/v.mp4",
        mode="hybrid",
        confidence_threshold=0.7,
        input_type="video",
    )
    record = JobRecord(
        job_id=job_id,
        input=job_input,
        status=JobStatus.QUEUED,
        created_at="",
        updated_at="",
    )
    returned = adapter.create(record)
    assert returned.job_id == job_id
    assert returned.input.video_path == job_input.video_path
    # Persisted record must be retrievable and match what create() returned
    retrieved = adapter.get(job_id)
    assert retrieved is not None
    assert retrieved.job_id == returned.job_id
    assert retrieved.input.video_path == returned.input.video_path
    assert retrieved.status == returned.status
    # Persisted record should have created_at/updated_at set by store
    assert len(returned.created_at) > 0
    assert len(returned.updated_at) > 0
