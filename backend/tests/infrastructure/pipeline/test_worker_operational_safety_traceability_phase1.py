"""WKR Phase 1 — frame cap, reference images, and source_image_id traceability tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from src.application.services.result_context_resolver import ResultContextResolver
from src.application.use_cases.pipeline.persist_aisle_result import (
    PersistAisleResultCommand,
    PersistAisleResultUseCase,
)
from src.application.use_cases.positions.list_aisle_positions import (
    ListAislePositionsCommand,
    ListAislePositionsUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.entity import Entity
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
from src.domain.traceability import (
    TRACEABILITY_INVALID,
    TRACEABILITY_VALID,
    apply_traceability_validation,
)
from src.infrastructure.pipeline.hybrid_report_to_domain_adapter import (
    default_map_hybrid_report_to_domain,
)
from src.infrastructure.pipeline.v3_report_mapper import map_hybrid_report_to_domain
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_evidence_repository import MemoryEvidenceRepository
from src.infrastructure.repositories.memory_final_count_repository import MemoryFinalCountRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository
from src.infrastructure.repositories.memory_normalized_label_repository import (
    MemoryNormalizedLabelRepository,
)
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
from tests.support.worker_phase1.executor_harness import FixedClock, build_recompute_use_case


def _photos_job_input(manifest_path: str, photos_dir: str) -> MagicMock:
    ji = MagicMock()
    ji.input_type = "photos"
    ji.input_manifest_path = manifest_path
    ji.photos_dir = photos_dir
    ji.video_path = ""
    ji.mode = "hybrid"
    return ji


def _run_context(tmp_path: Path, job_id: str) -> MagicMock:
    context = MagicMock(spec=RunContext)
    context.job_id = job_id
    context.logger = MagicMock()
    context.run_dir = tmp_path
    context.job_input = _photos_job_input("input_manifest.json", "photos")
    context.check_cancellation = MagicMock()
    context.emit_stage_event = MagicMock()
    context.metadata = {}
    return context


def _primary_ids_from_order(order: list[dict]) -> list[str]:
    return [
        str(e.get("source_image_id"))
        for e in order
        if e.get("kind") == "primary_evidence" and e.get("source_image_id")
    ]


# --- WKR-P1-T009: at or below frame cap ---------------------------------------


def test_wkr_p1_t009_below_frame_cap_manifest_matches_sent_ids(tmp_path: Path) -> None:
    """WKR-P1-T009: all manifest images sent when count <= cap."""
    images = [
        JobImage(f"asset-{i}", f"p{i}.jpg", i, f"stored_{i}.jpg") for i in range(1, 4)
    ]
    sent = [img.image_id for img in images]
    prompt = enrich_prompt_with_sent_image_ids("BASE", images, sent)
    for img in images:
        assert img.image_id in prompt
    assert prompt.index("asset-1") < prompt.index("asset-2") < prompt.index("asset-3")

    nd = np.zeros((4, 4, 3), dtype=np.uint8)
    _parts, order = build_openai_vision_content_parts(
        main_prompt_text=prompt,
        context_images=[],
        reference_image_ids=[],
        primary_frames_nd=[nd, nd, nd],
        frame_refs=sent,
    )
    primary_labels = [
        p for p in _parts if p.get("type") == "text" and ROLE_PRIMARY_EVIDENCE in p["text"]
    ]
    assert len(primary_labels) == 3
    assert _primary_ids_from_order(order) == sent


# --- WKR-P1-T010: above frame cap ---------------------------------------------


def test_wkr_p1_t010_above_frame_cap_truncates_deterministically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WKR-P1-T010: selected frames, manifest IDs, and provider payload IDs are identical."""
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
    context = _run_context(tmp_path, "job-cap")
    context.settings = settings

    monkeypatch.setattr(
        "src.pipeline.stages.frame_acquisition_stage.get_frame_source",
        lambda _t: frame_source,
    )
    monkeypatch.setattr(
        "src.pipeline.stages.frame_acquisition_stage.cv2.imread",
        lambda _p: np.zeros((8, 8, 3), dtype=np.uint8),
    )

    acquired = FrameAcquisitionStage().run(context, prepared)

    expected_selected = refs[:HYBRID_MAX_FRAMES_LOAD_CAP]
    expected_dropped = refs[HYBRID_MAX_FRAMES_LOAD_CAP:]
    assert len(acquired.frame_refs) == HYBRID_MAX_FRAMES_LOAD_CAP
    assert acquired.frame_refs == expected_selected
    assert expected_dropped == [f"asset-{i}" for i in range(49, 59)]

    manifest_images = [
        JobImage(ref, f"{ref}.jpg", idx + 1, f"stored_{ref}.jpg")
        for idx, ref in enumerate(acquired.frame_refs)
    ]
    manifest_ids = [img.image_id for img in manifest_images]
    assert manifest_ids == acquired.frame_refs

    prompt = enrich_prompt_with_sent_image_ids("BASE PROMPT", manifest_images, manifest_ids)
    for dropped_id in expected_dropped:
        assert dropped_id not in prompt

    _parts, order = build_openai_vision_content_parts(
        main_prompt_text=prompt,
        context_images=[],
        reference_image_ids=[],
        primary_frames_nd=acquired.frames_nd,
        frame_refs=acquired.frame_refs,
    )
    provider_primary_ids = _primary_ids_from_order(order)
    assert acquired.frame_refs == manifest_ids == provider_primary_ids

    dropped_entity = Entity(
        entity_uid="j_E_DROP",
        entity_type="PALLET",
        model_entity_id="E_DROP",
        source_image_id=expected_dropped[0],
    )
    apply_traceability_validation(
        [dropped_entity],
        frozenset(acquired.frame_refs),
        manifest_image_ids=frozenset(refs),
    )
    assert dropped_entity.traceability_status == TRACEABILITY_INVALID

    emit_calls = [c.kwargs.get("details") or {} for c in context.emit_stage_event.call_args_list]
    load_details = next(
        (d for d in emit_calls if d.get("frames_to_load") == HYBRID_MAX_FRAMES_LOAD_CAP),
        None,
    )
    assert load_details is not None
    assert load_details.get("available_frames") == total


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
    assert _primary_ids_from_order(o_order) == refs

    _g_contents, g_order = build_gemini_interleaved_contents(
        main_prompt_text="P",
        context_images=[],
        reference_image_ids=[],
        primary_pil_images=[object(), object(), object()],
        frame_refs=refs,
    )
    assert _primary_ids_from_order(g_order) == refs

    _a_parts, a_order = build_anthropic_message_content_parts(
        main_prompt_text="P",
        context_images=[],
        reference_image_ids=[],
        primary_frames_nd=frames,
        frame_refs=refs,
    )
    assert _primary_ids_from_order(a_order) == refs


# --- WKR-P1-T011: reference image separation ----------------------------------


def test_wkr_p1_t011_reference_images_labeled_separate_from_primary_evidence() -> None:
    """WKR-P1-T011: reference images cannot become operational source_image_id in payload."""
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
    assert not any(
        e.get("source_image_id") == "sup-ref-1" and e.get("kind") == "primary_evidence"
        for e in order
    )

    ctx = AnalysisContext(
        primary_evidence=[],
        visual_references=[
            VisualReferenceContext(
                reference_id="sup-ref-1",
                source_path="ref.jpg",
                mime_type="image/jpeg",
                role="supplier_reference",
                created_at=datetime(2026, 6, 12, tzinfo=timezone.utc).isoformat(),
            )
        ],
        instructions=[],
    )
    assert ctx.visual_references[0].reference_id == "sup-ref-1"
    assert all(v.reference_id != "asset-1" for v in ctx.visual_references)


def test_wkr_p1_t011b_reference_id_returned_as_provider_source_is_traceability_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WKR-P1-T011B: provider returning supplier reference ID is rejected at resolution."""
    primary_id = "asset-1"
    reference_id = "sup-ref-1"
    now = datetime(2026, 6, 12, tzinfo=timezone.utc)

    nd = np.zeros((4, 4, 3), dtype=np.uint8)
    prompt = enrich_prompt_with_sent_image_ids(
        "Analyze",
        [JobImage(primary_id, "p1.jpg", 1, "p1.jpg")],
        [primary_id],
    )
    _parts, order = build_openai_vision_content_parts(
        main_prompt_text=prompt,
        context_images=[nd],
        reference_image_ids=[reference_id],
        primary_frames_nd=[nd],
        frame_refs=[primary_id],
    )
    provider_primary_ids = _primary_ids_from_order(order)
    assert provider_primary_ids == [primary_id]

    provider_source_id = reference_id
    assert provider_source_id not in provider_primary_ids

    context = _run_context(tmp_path, "job-ref-neg")
    sent_ids = provider_primary_ids
    analysis = AnalysisStageResult(
        parsed_json={
            "total_entities_detected": 1,
            "entities": [
                {
                    "entity_uid": "e-ref",
                    "entity_type": "PALLET",
                    "model_entity_id": "E1",
                    "internal_code": "SKU-REF",
                    "final_quantity": 1,
                    "confidence": 0.9,
                    "count_status": "COUNTED",
                    "source_image_id": provider_source_id,
                }
            ],
        },
        provider_name="gemini",
        prompt_composition={
            "frames_sent_ids": sent_ids,
            "prompt_listed_image_ids": sent_ids,
        },
    )

    monkeypatch.setattr(
        "src.pipeline.stages.entity_resolution_stage.load_job_images_from_manifest",
        lambda _mp, _pd: [JobImage(primary_id, "p1.jpg", 1, "p1.jpg")],
    )
    resolved = EntityResolutionStage().run(context, analysis)
    entity = resolved.entities[0]
    assert entity.source_image_id == provider_source_id
    assert entity.traceability_status == TRACEABILITY_INVALID

    report = {
        "entities": [
            {
                "entity_uid": entity.entity_uid,
                "entity_type": entity.entity_type,
                "model_entity_id": entity.model_entity_id,
                "internal_code": "SKU-REF",
                "final_quantity": 1,
                "confidence": 0.9,
                "count_status": entity.count_status,
                "evidence_path": "evidence/crop.jpg",
                "source_image_id": entity.source_image_id,
            }
        ]
    }

    aisle_repo = MemoryAisleRepository()
    inv_repo = MemoryInventoryRepository()
    pos_repo = MemoryPositionRepository()
    prod_repo = MemoryProductRecordRepository()
    ev_repo = MemoryEvidenceRepository()
    raw_repo = MemoryRawLabelRepository()
    job_repo = MemoryJobRepository()

    aisle_repo.save(
        Aisle("aisle-ref", "inv-ref", "A", AisleStatus.PROCESSING, now, now, operational_job_id="job-ref-neg")
    )
    inv_repo.save(Inventory("inv-ref", "X", InventoryStatus.PROCESSING, now, now))
    job_repo.save(
        Job(
            "job-ref-neg",
            "aisle",
            "aisle-ref",
            "process_aisle",
            JobStatus.SUCCEEDED,
            {"aisle_id": "aisle-ref"},
            now,
            now,
        )
    )

    persist = PersistAisleResultUseCase(
        position_repo=pos_repo,
        product_record_repo=prod_repo,
        evidence_repo=ev_repo,
        clock=FixedClock(now),
        hybrid_mapper=default_map_hybrid_report_to_domain,
        aisle_repo=aisle_repo,
        raw_label_repo=raw_repo,
        recompute_consolidated_uc=build_recompute_use_case(
            raw_repo=raw_repo,
            norm_repo=MemoryNormalizedLabelRepository(),
            final_repo=MemoryFinalCountRepository(),
            product_repo=prod_repo,
            position_repo=pos_repo,
        ),
    )
    persist.execute(
        PersistAisleResultCommand(
            aisle_id="aisle-ref",
            job_id="job-ref-neg",
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
            inventory_id="inv-ref", aisle_id="aisle-ref", page=1, page_size=10
        )
    )
    assert len(result.positions) == 1
    summary = result.positions[0].detected_summary_json or {}
    assert summary.get("source_image_id") == provider_source_id
    assert summary.get("source_image_id") != primary_id


# --- WKR-P1-T013: end-to-end source_image_id ----------------------------------


def test_wkr_p1_t013_source_image_id_preserved_through_persist_and_read_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WKR-P1-T013: one source identity flows asset → manifest → payload → persist → read model."""
    source_id = "asset-trace-1"
    now = datetime(2026, 6, 12, tzinfo=timezone.utc)
    job_id = "job-tr"

    stored_asset = JobImage(source_id, "trace.jpg", 1, f"stored/{source_id}.jpg")
    acquired_frame_refs = [source_id]
    manifest_images = [stored_asset]
    manifest_ids = [img.image_id for img in manifest_images]
    assert manifest_ids == acquired_frame_refs == [source_id]

    prompt = enrich_prompt_with_sent_image_ids("BASE", manifest_images, manifest_ids)
    assert source_id in prompt

    nd = np.zeros((4, 4, 3), dtype=np.uint8)
    _parts, order = build_openai_vision_content_parts(
        main_prompt_text=prompt,
        context_images=[],
        reference_image_ids=[],
        primary_frames_nd=[nd],
        frame_refs=acquired_frame_refs,
    )
    provider_primary_ids = _primary_ids_from_order(order)
    assert provider_primary_ids == [source_id]

    provider_source_id = provider_primary_ids[0]
    context = _run_context(tmp_path, job_id)
    analysis = AnalysisStageResult(
        parsed_json={
            "total_entities_detected": 1,
            "entities": [
                {
                    "entity_uid": "e-tr",
                    "entity_type": "PALLET",
                    "model_entity_id": "E1",
                    "internal_code": "SKU-TR",
                    "final_quantity": 1,
                    "confidence": 0.95,
                    "count_status": "COUNTED",
                    "source_image_id": provider_source_id,
                }
            ],
        },
        provider_name="gemini",
        prompt_composition={
            "frames_sent_ids": provider_primary_ids,
            "prompt_listed_image_ids": provider_primary_ids,
        },
    )

    monkeypatch.setattr(
        "src.pipeline.stages.entity_resolution_stage.load_job_images_from_manifest",
        lambda _mp, _pd: [stored_asset],
    )
    resolved = EntityResolutionStage().run(context, analysis)
    assert resolved.entities[0].source_image_id == source_id
    assert resolved.entities[0].traceability_status == TRACEABILITY_VALID

    report_entity = resolved.entities[0]
    report = {
        "entities": [
            {
                "entity_uid": report_entity.entity_uid,
                "entity_type": report_entity.entity_type,
                "model_entity_id": report_entity.model_entity_id,
                "internal_code": "SKU-TR",
                "final_quantity": 1,
                "confidence": 0.95,
                "count_status": report_entity.count_status,
                "evidence_path": "evidence/crop.jpg",
                "source_image_id": report_entity.source_image_id,
            }
        ]
    }

    mapped = map_hybrid_report_to_domain(
        aisle_id="aisle-tr",
        report=report,
        run_dir=tmp_path,
        run_id="run",
        job_id=job_id,
        now=now,
        inventory_id="inv-tr",
    )
    assert (mapped.positions[0].detected_summary_json or {}).get("source_image_id") == source_id

    aisle_repo = MemoryAisleRepository()
    inv_repo = MemoryInventoryRepository()
    pos_repo = MemoryPositionRepository()
    prod_repo = MemoryProductRecordRepository()
    ev_repo = MemoryEvidenceRepository()
    raw_repo = MemoryRawLabelRepository()
    job_repo = MemoryJobRepository()

    aisle_repo.save(
        Aisle("aisle-tr", "inv-tr", "A", AisleStatus.PROCESSING, now, now, operational_job_id=job_id)
    )
    inv_repo.save(Inventory("inv-tr", "X", InventoryStatus.PROCESSING, now, now))
    job_repo.save(
        Job(
            job_id,
            "aisle",
            "aisle-tr",
            "process_aisle",
            JobStatus.SUCCEEDED,
            {"aisle_id": "aisle-tr"},
            now,
            now,
        )
    )

    persist = PersistAisleResultUseCase(
        position_repo=pos_repo,
        product_record_repo=prod_repo,
        evidence_repo=ev_repo,
        clock=FixedClock(now),
        hybrid_mapper=default_map_hybrid_report_to_domain,
        aisle_repo=aisle_repo,
        raw_label_repo=raw_repo,
        recompute_consolidated_uc=build_recompute_use_case(
            raw_repo=raw_repo,
            norm_repo=MemoryNormalizedLabelRepository(),
            final_repo=MemoryFinalCountRepository(),
            product_repo=prod_repo,
            position_repo=pos_repo,
        ),
    )
    persist.execute(
        PersistAisleResultCommand(
            aisle_id="aisle-tr",
            job_id=job_id,
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
