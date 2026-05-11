"""E6 — execution log IDs, instruction spacing, prompt log summary, supplier report traceability."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock

from src.application.services.aisle_analysis_context_builder import SUPPLIER_REFERENCES_INSTRUCTION
from src.application.services.supplier_prompt_resolver import SupplierPromptResolution
from src.jobs.models import JobInput
from src.llm.prompt_composer.enrichments import SUPPLIER_EDITABLE_INSTRUCTIONS_ENRICHMENT_ID
from src.llm.prompt_composer.prompt_traceability import (
    apply_execution_layer_to_composition,
    prompt_composition_summary_for_execution_log,
)
from src.llm.types import LLMRequest
from src.pipeline.context.run_context import RunContext
from src.pipeline.contracts.analysis_context import AnalysisContext, VisualReferenceContext
from src.pipeline.execution_log import ExecutionLogWriter
from src.pipeline.services.analysis_visual_reference_prep import (
    build_primary_evidence_attachments,
    prepare_visual_reference_inputs,
)
from src.pipeline.services.hybrid_analysis_prompt import (
    build_hybrid_analysis_prompt_with_traceability,
)
from src.reporting.supplier_traceability import build_supplier_traceability_report_block
from tests.pipeline.test_hybrid_analysis_prompt_e4_integration import (
    _minimal_run_context,
    _resolution,
)


def test_e6_supplier_instruction_spacing() -> None:
    assert "evidence.They" not in SUPPLIER_REFERENCES_INSTRUCTION
    assert "comparative context only" in SUPPLIER_REFERENCES_INSTRUCTION
    assert "not primary evidence" in SUPPLIER_REFERENCES_INSTRUCTION
    assert "not inventoried product listings" in SUPPLIER_REFERENCES_INSTRUCTION
    assert "must not be used as proof" in SUPPLIER_REFERENCES_INSTRUCTION


def test_e6_emit_stage_event_includes_ids_from_job_input_metadata(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    log = logging.getLogger("e6-test")
    exec_log = ExecutionLogWriter(run_dir)
    ji = JobInput(
        video_path="/v.mp4",
        metadata={"inventory_id": "inv-1", "aisle_id": "aisle-1", "attempt_count": 2},
    )
    ctx = RunContext(
        job_id="job-1",
        run_id="run-1",
        workspace_path=tmp_path,
        run_dir=run_dir,
        job_input=ji,
        settings=MagicMock(),
        logger=log,
        execution_log=exec_log,
    )
    ctx.emit_stage_event(stage="InputPreparationStage", event="stage.started")
    line = (exec_log.path).read_text(encoding="utf-8").strip().splitlines()[0]
    payload = json.loads(line)["payload"]
    assert payload["inventory_id"] == "inv-1"
    assert payload["aisle_id"] == "aisle-1"
    assert payload["attempt"] == 2


def test_e6_emit_stage_event_falls_back_to_supplier_resolution_ids(tmp_path: Path) -> None:
    run_dir = tmp_path / "run2"
    run_dir.mkdir()
    log = logging.getLogger("e6-test2")
    exec_log = ExecutionLogWriter(run_dir)
    ji = JobInput(video_path="/v.mp4", metadata={})
    spr = SupplierPromptResolution(
        inventory_id="inv-fb",
        aisle_id="aisle-fb",
        client_id="c1",
        client_supplier_id="s1",
        provider_name="gemini",
        model_name=None,
        supplier_prompt_config_id=None,
        supplier_prompt_config_version=None,
        editable_instructions=None,
        fallback_used=True,
        fallback_reason="NO_CONFIG",
        resolution_status="fallback",
    )
    ctx = RunContext(
        job_id="job-1",
        run_id="run-1",
        workspace_path=tmp_path,
        run_dir=run_dir,
        job_input=ji,
        settings=MagicMock(),
        logger=log,
        execution_log=exec_log,
        supplier_prompt_resolution=spr,
    )
    ctx.emit_stage_event(stage="AnalysisStage", event="stage.started")
    line = (exec_log.path).read_text(encoding="utf-8").strip().splitlines()[0]
    payload = json.loads(line)["payload"]
    assert payload["inventory_id"] == "inv-fb"
    assert payload["aisle_id"] == "aisle-fb"


def test_e61_prompt_composition_summary_filters_effective_prompt_to_allowlist() -> None:
    full = {
        "prompt_hash": "abc",
        "effective_prompt": {
            "supplier_instructions_applied": True,
            "fallback_used": False,
            "resolution_status": "resolved",
            "supplier_prompt_config_id": "cfg-1",
            "effective_prompt_hash": "effh",
            "editable_instructions": "SHOULD_NOT_LEAK",
            "effective_prompt_text": "FULL_PROMPT_SHOULD_NOT_LEAK",
            "unexpected_future_key": "DROP_ME",
        },
    }
    summary = prompt_composition_summary_for_execution_log(full, final_prompt_char_len=100)
    eff = summary["effective_prompt"]
    assert eff["supplier_instructions_applied"] is True
    assert eff["resolution_status"] == "resolved"
    assert eff["supplier_prompt_config_id"] == "cfg-1"
    assert "editable_instructions" not in eff
    assert "effective_prompt_text" not in eff
    assert "unexpected_future_key" not in eff
    dumped = json.dumps(summary, ensure_ascii=False)
    assert "SHOULD_NOT_LEAK" not in dumped
    assert "FULL_PROMPT_SHOULD_NOT_LEAK" not in dumped


def test_e6_prompt_composition_summary_includes_effective_prompt_redacted() -> None:
    full = {
        "prompt_hash": "abc",
        "enrichments_applied": ["supplier_editable_instructions_e4"],
        "effective_prompt": {
            "supplier_instructions_applied": True,
            "fallback_used": False,
            "resolution_status": "resolved",
            "supplier_prompt_config_id": "cfg-1",
            "effective_prompt_hash": "effh",
        },
    }
    summary = prompt_composition_summary_for_execution_log(full, final_prompt_char_len=100)
    assert summary.get("effective_prompt", {}).get("supplier_instructions_applied") is True
    assert summary["effective_prompt"]["resolution_status"] == "resolved"


def test_e6_unique_supplier_instruction_not_in_effective_prompt_metadata() -> None:
    secret = "UNIQUE_SUPPLIER_SECRET_TEST_INSTRUCTION"
    res = _resolution(
        resolution_status="resolved",
        editable_instructions=secret,
        supplier_prompt_config_id="cfg-x",
        supplier_prompt_config_version=1,
    )
    run_ctx = _minimal_run_context(supplier_prompt_resolution=res)
    prompt_text, comp = build_hybrid_analysis_prompt_with_traceability(run_ctx)
    assert secret in prompt_text
    merged = apply_execution_layer_to_composition(
        comp,
        resolved_llm_provider_key="gemini",
        model_name="gemini-2.0-flash",
    )
    req = LLMRequest(
        job_id="job-1",
        frames=[Path("/tmp/f0.jpg")],
        frame_refs=["f0"],
        prompt=prompt_text,
        schema_version="v2.1",
        metadata={"prompt_composition": merged},
    )
    pc = req.metadata["prompt_composition"]
    eff = pc.get("effective_prompt") or {}
    assert secret not in json.dumps(eff, ensure_ascii=False)
    assert SUPPLIER_EDITABLE_INSTRUCTIONS_ENRICHMENT_ID in (pc.get("enrichments_applied") or [])


def test_e6_attachment_summary_primary_plus_visual(tmp_path: Path) -> None:
    from PIL import Image

    p1 = tmp_path / "r1.png"
    Image.new("RGB", (4, 4)).save(p1)
    ac = AnalysisContext(
        primary_evidence=[],
        visual_references=[
            VisualReferenceContext(
                reference_id="r1",
                source_path=str(p1),
                mime_type="image/png",
                role="supplier_reference",
                resolved_path=str(p1),
            ),
            VisualReferenceContext(
                reference_id="r2",
                source_path=str(p1),
                mime_type="image/png",
                role="supplier_reference",
                resolved_path=str(p1),
            ),
        ],
        instructions=["x"],
        metadata=None,
    )
    loaded, visual_atts, _ = prepare_visual_reference_inputs(ac, job_id="j1")
    primary = build_primary_evidence_attachments(
        [tmp_path / "a.jpg", tmp_path / "b.jpg", tmp_path / "c.jpg"],
        ["1", "2", "3"],
    )
    primary_count = len(primary)
    visual_count = len(loaded)
    assert primary_count == 3
    assert visual_count == 2
    assert primary_count + visual_count == 5
    assert all(a["role"] == "visual_reference" for a in visual_atts)
    assert all(a["role"] == "primary_evidence" for a in primary)


def test_e6_supplier_traceability_report_block_from_run_context() -> None:
    from datetime import datetime, timezone

    from src.domain.aisle.entities import Aisle, AisleStatus

    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    aisle = Aisle(
        id="aisle-99",
        inventory_id="inv-99",
        code="A",
        status=AisleStatus.CREATED,
        created_at=now,
        updated_at=now,
        client_supplier_id="sup-1",
    )
    spr = SupplierPromptResolution(
        inventory_id=aisle.inventory_id,
        aisle_id=aisle.id,
        client_id="c1",
        client_supplier_id="sup-1",
        provider_name="gemini",
        model_name=None,
        supplier_prompt_config_id="cfg",
        supplier_prompt_config_version=3,
        editable_instructions="secret-do-not-leak",
        fallback_used=False,
        fallback_reason=None,
        resolution_status="resolved",
    )
    ac = AnalysisContext(
        primary_evidence=[],
        visual_references=[],
        instructions=[],
        metadata={
            "reference_source": "supplier_reference_images",
            "client_supplier_id": "sup-1",
            "supplier_reference_resolution_status": "resolved",
            "supplier_reference_image_count": 2,
        },
    )
    ctx = RunContext(
        job_id="j1",
        run_id="r1",
        workspace_path=Path("/tmp"),
        run_dir=Path("/tmp/j1/r1"),
        job_input=JobInput(video_path="", metadata={}),
        settings=MagicMock(),
        logger=logging.getLogger("t"),
        supplier_prompt_resolution=spr,
        analysis_context=ac,
    )
    block = build_supplier_traceability_report_block(ctx)
    assert block is not None
    assert "secret" not in json.dumps(block)
    assert block["supplier_prompt"]["supplier_prompt_config_id"] == "cfg"
    assert block["supplier_references"]["image_count"] == 2
    assert block["supplier_references"]["reference_source"] == "supplier_reference_images"
