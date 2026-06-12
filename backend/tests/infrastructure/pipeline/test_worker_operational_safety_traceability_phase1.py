"""WKR Phase 1 — frame cap, reference images, and source_image_id traceability tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np

from src.application.services.result_context_resolver import ResultContextResolver
from src.application.use_cases.pipeline.persist_aisle_result import PersistAisleResultCommand
from src.application.use_cases.positions.list_aisle_positions import (
    ListAislePositionsCommand,
    ListAislePositionsUseCase,
)
from src.domain.traceability import TRACEABILITY_INVALID, TRACEABILITY_VALID
from src.infrastructure.pipeline.v3_report_mapper import map_hybrid_report_to_domain
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_evidence_repository import MemoryEvidenceRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.repositories.memory_product_record_repository import (
    MemoryProductRecordRepository,
)
from src.infrastructure.repositories.memory_raw_label_repository import MemoryRawLabelRepository
from src.jobs.image_identity import JobImage
from src.llm.prompt_composer.enrichments import enrich_prompt_with_sent_image_ids
from src.llm.vision_multimodal_payload import (
    ROLE_PRIMARY_EVIDENCE,
    ROLE_REFERENCE_ONLY,
    build_anthropic_message_content_parts,
    build_gemini_interleaved_contents,
    build_openai_vision_content_parts,
)
from src.pipeline.context.run_context import RunContext
from src.pipeline.contracts.analysis_context import AnalysisContext, VisualReferenceContext
from src.pipeline.stages.analysis_stage import AnalysisStageResult
from src.pipeline.stages.entity_resolution_stage import EntityResolutionStage
from src.pipeline.stages.frame_acquisition_stage import (
    HYBRID_MAX_FRAMES_LOAD_CAP,
    FrameAcquisitionStage,
)
from src.pipeline.stages.input_preparation_stage import PreparedInput
from tests.support.worker_phase1.executor_harness import build_recompute_use_case


def _photos_job_input(manifest_path: str, photos_dir: str) -> MagicMock:
    ji = MagicMock()
    ji.input_type = "photos"
    ji.input_manifest_path = manifest_path
    ji.photos_dir = photos_dir
    ji.video_path = ""
    ji.mode = "hybrid"
    return ji


# --- WKR-P1-T009: at or below frame cap ---------------------------------------


def test_wkr_p1_t009_below_frame_cap_manifest_matches_sent_ids(tmp_path: Path) -> None:
    """WKR-P1-T009: all manifest images sent when count <= cap."""
    images = [
        JobImage(f"asset-{i}", f"p{i}.jpg", i, f"stored_{i}.jpg") for i in range(1, 4)
    ]  # image_id, original_filename, upload_order, storage_path
    sent = [img.image_id for img in images]
    prompt = enrich_prompt_with_sent_image_ids("BASE", images, sent)
    for img in images:
        assert img.image_id in prompt
    assert prompt.index("asset-1") < prompt.index("asset-2") < prompt.index("asset-3")

    nd = np.zeros((4, 4, 3), dtype=np.uint8)
    parts, order = build_openai_vision_content_parts(
        main_prompt_text=prompt,
        context_images=[],
        reference_image_ids=[],
        primary_frames_nd=[nd, nd, nd],
        frame_refs=sent,
    )
    primary_labels = [p for p in parts if p.get("type") == "text" and ROLE_PRIMARY_EVIDENCE in p["text"]]
    assert len(primary_labels) == 3
    assert [e.get("source_image_id") for e in order if e["kind"] == "primary_evidence"] == sent


# --- WKR-P1-T010: above frame cap ---------------------------------------------


def test_wkr_p1_t010_above_frame_cap_truncates_deterministically(tmp_path: Path) -> None:
    """WKR-P1-T010: FrameAcquisitionStage keeps first N frames per hybrid_max_frames cap."""
    total = HYBRID_MAX_FRAMES_LOAD_CAP + 10
    photos_dir = tmp_path / "photos"
    photos_dir.mkdir()
    frame_paths = []
    refs = []
    for i in range(1, total + 1):
        p = photos_dir / f"{i:04d}_asset-{i}.jpg"
        p.write_bytes(b"\xff\xd8\xff")
        frame_paths.append(p)
        refs.append(f"asset-{i}")

    bundle = MagicMock()
    bundle.frames = frame_paths
    bundle.frame_refs = refs
    bundle.metadata = {"source": "photos", "frame_indices": list(range(total))}

    frame_source = MagicMock()
    frame_source.get_frames.return_value = bundle

    settings = MagicMock()
    settings.hybrid_max_frames = HYBRID_MAX_FRAMES_LOAD_CAP

    prepared = PreparedInput(
        job_id="job-cap",
        input_type="photos",
        job_input=_photos_job_input("input_manifest.json", "photos"),
    )
    context = MagicMock(spec=RunContext)
    context.settings = settings
    context.job_id = "job-cap"
    context.run_dir = tmp_path
    context.logger = MagicMock()
    context.check_cancellation = MagicMock()
    context.emit_stage_event = MagicMock()
    context.metadata = {}

    import cv2

    original_imread = cv2.imread

    def _fake_imread(_p: str) -> np.ndarray:
        return np.zeros((8, 8, 3), dtype=np.uint8)

    import src.pipeline.stages.frame_acquisition_stage as fas

    original_get = fas.get_frame_source
    fas.get_frame_source = lambda _t: frame_source
    fas.cv2.imread = _fake_imread
    try:
        acquired = FrameAcquisitionStage().run(context, prepared)
    finally:
        fas.get_frame_source = original_get
        fas.cv2.imread = original_imread

    assert len(acquired.frame_refs) == HYBRID_MAX_FRAMES_LOAD_CAP
    assert acquired.frame_refs == refs[:HYBRID_MAX_FRAMES_LOAD_CAP]
    dropped = set(refs[HYBRID_MAX_FRAMES_LOAD_CAP:])
    assert "asset-050" in dropped or len(dropped) > 0

    sent = acquired.frame_refs
    entities = [
        __import__("src.domain.entity", fromlist=["Entity"]).Entity(
            entity_uid="j_E1",
            entity_type="PALLET",
            model_entity_id="E1",
            source_image_id=dropped.pop() if dropped else "asset-999",
        )
    ]
    __import__(
        "src.domain.traceability", fromlist=["apply_traceability_validation"]
    ).apply_traceability_validation(entities, frozenset(sent), manifest_image_ids=frozenset(refs))
    assert entities[0].traceability_status == TRACEABILITY_INVALID


# --- WKR-P1-T010B: provider adapter ordering ----------------------------------


def test_wkr_p1_t010b_provider_adapters_preserve_primary_frame_ref_order() -> None:
    """WKR-P1-T010B: OpenAI, Gemini, Anthropic payloads keep manifest order."""
    nd = np.zeros((4, 4, 3), dtype=np.uint8)
    refs = ["asset-a", "asset-b", "asset-c"]
    frames = [nd, nd, nd]

    _o_parts, o_order = build_openai_vision_content_parts(
        main_prompt_text="P",
        context_images=[],
        reference_image_ids=[],
        primary_frames_nd=frames,
        frame_refs=refs,
    )
    o_primary = [
        e.get("source_image_id")
        for e in o_order
        if e.get("kind") == "primary_evidence"
    ]
    assert o_primary == refs

    _g_contents, g_order = build_gemini_interleaved_contents(
        main_prompt_text="P",
        context_images=[],
        reference_image_ids=[],
        primary_pil_images=[object(), object(), object()],
        frame_refs=refs,
    )
    g_primary = [
        e.get("source_image_id")
        for e in g_order
        if e.get("kind") == "primary_evidence"
    ]
    assert g_primary == refs

    _a_parts, a_order = build_anthropic_message_content_parts(
        main_prompt_text="P",
        context_images=[],
        reference_image_ids=[],
        primary_frames_nd=frames,
        frame_refs=refs,
    )
    a_primary = [
        e.get("source_image_id")
        for e in a_order
        if e.get("kind") == "primary_evidence"
    ]
    assert a_primary == refs


# --- WKR-P1-T011: reference image separation ----------------------------------


def test_wkr_p1_t011_reference_images_labeled_separate_from_primary_evidence() -> None:
    """WKR-P1-T011: reference images cannot become operational source_image_id."""
    nd = np.zeros((4, 4, 3), dtype=np.uint8)
    parts, order = build_openai_vision_content_parts(
        main_prompt_text="Analyze",
        context_images=[nd],
        reference_image_ids=["sup-ref-1"],
        primary_frames_nd=[nd],
        frame_refs=["asset-1"],
    )
    ref_labels = [p for p in parts if p.get("type") == "text" and ROLE_REFERENCE_ONLY in p["text"]]
    pri_labels = [p for p in parts if p.get("type") == "text" and ROLE_PRIMARY_EVIDENCE in p["text"]]
    assert ref_labels and pri_labels
    assert "sup-ref-1" in ref_labels[0]["text"]
    assert "asset-1" in pri_labels[0]["text"]
    assert not any(e.get("ref") == "sup-ref-1" and e.get("kind") == "primary_evidence" for e in order)

    ctx = AnalysisContext(
        primary_evidence=[],
        visual_references=[
            VisualReferenceContext(
                reference_id="sup-ref-1",
                source_path="ref.jpg",
                mime_type="image/jpeg",
                role="supplier_reference",
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        ],
        instructions=[],
    )
    assert ctx.visual_references[0].reference_id == "sup-ref-1"
    assert all(v.reference_id != "asset-1" for v in ctx.visual_references)


# --- WKR-P1-T013: end-to-end source_image_id ----------------------------------


def test_wkr_p1_t013_source_image_id_preserved_through_persist_and_read_model(
    tmp_path: Path,
) -> None:
    """WKR-P1-T013: asset id → report → persistence → list read model."""
    source_id = "asset-trace-1"
    now = datetime.now(timezone.utc)
    report = {
        "entities": [
                {
                    "entity_uid": "e-tr",
                    "entity_type": "PALLET",
                    "model_entity_id": "E1",
                    "internal_code": "SKU-TR",
                    "final_quantity": 1,
                    "confidence": 0.95,
                    "count_status": "COUNTED",
                    "evidence_path": "evidence/crop.jpg",
                    "source_image_id": source_id,
                }
        ]
    }

    context = MagicMock(spec=RunContext)
    context.job_id = "job-tr"
    context.logger = MagicMock()
    context.run_dir = tmp_path
    context.job_input = _photos_job_input("input_manifest.json", "photos")

    analysis = AnalysisStageResult(
        parsed_json={
            "total_entities_detected": 1,
            "entities": report["entities"],
        },
        provider_name="gemini",
        prompt_composition={
            "frames_sent_ids": [source_id],
            "prompt_listed_image_ids": [source_id],
        },
    )
    import src.pipeline.stages.entity_resolution_stage as ers

    original_load = ers.load_job_images_from_manifest
    ers.load_job_images_from_manifest = lambda _mp, _pd: [
        JobImage(source_id, "trace.jpg", 1, "trace.jpg")
    ]
    try:
        resolved = EntityResolutionStage().run(context, analysis)
    finally:
        ers.load_job_images_from_manifest = original_load
    assert resolved.entities[0].source_image_id == source_id
    assert resolved.entities[0].traceability_status == TRACEABILITY_VALID

    mapped = map_hybrid_report_to_domain(
        aisle_id="aisle-tr",
        report=report,
        run_dir=tmp_path,
        run_id="run",
        job_id="job-tr",
        now=now,
        inventory_id="inv-tr",
    )
    summary = mapped.positions[0].detected_summary_json or {}
    assert summary.get("source_image_id") == source_id

    aisle_repo = MemoryAisleRepository()
    inv_repo = MemoryInventoryRepository()
    pos_repo = MemoryPositionRepository()
    prod_repo = MemoryProductRecordRepository()
    ev_repo = MemoryEvidenceRepository()
    raw_repo = MemoryRawLabelRepository()
    job_repo = MemoryJobRepository()

    from src.domain.aisle.entities import Aisle, AisleStatus
    from src.domain.inventory.entities import Inventory, InventoryStatus
    from src.domain.jobs.entities import Job, JobStatus

    aisle_repo.save(
        Aisle("aisle-tr", "inv-tr", "A", AisleStatus.PROCESSING, now, now, operational_job_id="job-tr")
    )
    inv_repo.save(Inventory("inv-tr", "X", InventoryStatus.PROCESSING, now, now))
    job_repo.save(
        Job(
            "job-tr",
            "aisle",
            "aisle-tr",
            "process_aisle",
            JobStatus.SUCCEEDED,
            {"aisle_id": "aisle-tr"},
            now,
            now,
        )
    )

    clock = MagicMock()
    clock.now.return_value = now
    from src.application.use_cases.pipeline.persist_aisle_result import PersistAisleResultUseCase
    from src.infrastructure.pipeline.hybrid_report_to_domain_adapter import (
        default_map_hybrid_report_to_domain,
    )

    persist = PersistAisleResultUseCase(
        position_repo=pos_repo,
        product_record_repo=prod_repo,
        evidence_repo=ev_repo,
        clock=clock,
        hybrid_mapper=default_map_hybrid_report_to_domain,
        aisle_repo=aisle_repo,
        raw_label_repo=raw_repo,
        recompute_consolidated_uc=build_recompute_use_case(
            raw_repo=raw_repo,
            norm_repo=__import__(
                "src.infrastructure.repositories.memory_normalized_label_repository",
                fromlist=["MemoryNormalizedLabelRepository"],
            ).MemoryNormalizedLabelRepository(),
            final_repo=__import__(
                "src.infrastructure.repositories.memory_final_count_repository",
                fromlist=["MemoryFinalCountRepository"],
            ).MemoryFinalCountRepository(),
            product_repo=prod_repo,
            position_repo=pos_repo,
        ),
    )
    persist.execute(
        PersistAisleResultCommand(
            aisle_id="aisle-tr",
            job_id="job-tr",
            report=report,
            run_dir=tmp_path,
            run_id="run",
        )
    )

    list_uc = ListAislePositionsUseCase(
        inv_repo,
        aisle_repo,
        pos_repo,
        ResultContextResolver(job_repo, pos_repo),
        prod_repo,
        positions_aisle_raw_cap=500,
    )
    result = list_uc.execute(
        ListAislePositionsCommand(
            inventory_id="inv-tr", aisle_id="aisle-tr", page=1, page_size=10
        )
    )
    assert len(result.positions) == 1
    assert (result.positions[0].detected_summary_json or {}).get("source_image_id") == source_id
