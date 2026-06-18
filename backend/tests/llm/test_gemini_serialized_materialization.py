"""Phase 4.4 hotfix — Gemini serialized payload image materialization."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
from google.genai import types
from PIL import Image

from src.domain.execution_image_manifest import (
    ExecutionImageEntry,
    ExecutionImageManifest,
    ExecutionImageRole,
)
from src.domain.prompt_image_projection import build_prompt_image_projection_from_manifest
from src.llm.gemini_global_analyzer import GeminiGlobalAnalyzer
from src.llm.prompt_composer.enrichments import enrich_prompt_with_execution_manifest
from src.llm.types import IMAGE_EXECUTION_CONTRACT_CANONICAL_MANIFEST, LLMRequest
from src.llm.vision_multimodal_payload import (
    build_gemini_contents_from_serialized,
    materialize_gemini_serialized_image,
    resolve_serialized_payload_for_adapter,
)
from src.pipeline.services.execution_image_manifest_payload import (
    bind_provider_payload_from_manifest,
    primary_lookups_from_acquired,
)
from src.pipeline.services.provider_execution_errors import (
    PROVIDER_IMAGE_SERIALIZATION_FAILED,
    PROVIDER_IMAGE_UNSUPPORTED_FORMAT,
    ProviderImageExecutionError,
)
from src.pipeline.services.provider_execution_request import build_provider_execution_request
from src.pipeline.services.provider_payload_serialization import (
    SerializedImagePayloadEntry,
    serialize_provider_images,
)


def _is_gemini_compatible_image_item(item: object) -> bool:
    if isinstance(item, Image.Image):
        return True
    if isinstance(item, types.Part):
        inline = getattr(item, "inline_data", None)
        if inline is not None and getattr(inline, "mime_type", None):
            return True
        file_data = getattr(item, "file_data", None)
        if file_data is not None:
            return bool(getattr(file_data, "file_uri", None)) and bool(
                getattr(file_data, "mime_type", None)
            )
    return False


def _five_photo_bundle(*, with_reference: bool = False):
    entries: list[ExecutionImageEntry] = []
    ordinal = 1
    ref_pil = Image.new("RGB", (4, 4), color=(10, 20, 30))
    ref_lookup: dict[str, object] = {}
    if with_reference:
        entries.append(
            ExecutionImageEntry(
                manifest_entry_id="REF_001",
                source_asset_id="ref-1",
                source_image_id="ref-1",
                role=ExecutionImageRole.REFERENCE_IMAGE,
                payload_ordinal=ordinal,
                storage_reference="ref.jpg",
            )
        )
        ref_lookup["ref-1"] = ref_pil
        ordinal += 1

    paths: list[Path] = []
    refs: list[str] = []
    nds: list[np.ndarray] = []
    for i in range(1, 6):
        entries.append(
            ExecutionImageEntry(
                manifest_entry_id=f"IMG_{i:03d}",
                source_asset_id=f"asset-{i}",
                source_image_id=f"img_{i:03d}",
                role=ExecutionImageRole.PRIMARY_EVIDENCE,
                payload_ordinal=ordinal,
                storage_reference=f"p{i}.jpg",
            )
        )
        ordinal += 1
        paths.append(Path(f"p{i}.jpg"))
        refs.append(f"img_{i:03d}")
        nds.append(np.full((8, 8, 3), i, dtype=np.uint8))

    manifest = ExecutionImageManifest(job_id="job-5", entries=tuple(entries), excluded_entries=())
    path_by, nd_by = primary_lookups_from_acquired(paths, refs, nds)
    bound = bind_provider_payload_from_manifest(
        manifest,
        primary_path_by_source_id=path_by,
        primary_nd_by_source_id=nd_by,
        reference_image_by_source_id=ref_lookup,
    )
    prompt, projection = enrich_prompt_with_execution_manifest("BASE", manifest)
    req = build_provider_execution_request(
        job_id="job-5",
        prompt=prompt,
        manifest=manifest,
        bound_payload=bound,
    )
    serialized = serialize_provider_images(req, prompt_projection=projection)
    return manifest, req, serialized, ref_pil


def test_primary_ndarray_materializes_to_pil() -> None:
    _, _, serialized, _ = _five_photo_bundle()
    primary = next(e for e in serialized.entries if e.role == ExecutionImageRole.PRIMARY_EVIDENCE)
    result = materialize_gemini_serialized_image(primary, job_id="job-5")
    assert isinstance(result, Image.Image)


def test_reference_pil_image_accepted() -> None:
    _, _, serialized, _ = _five_photo_bundle(with_reference=True)
    ref = next(e for e in serialized.entries if e.role == ExecutionImageRole.REFERENCE_IMAGE)
    result = materialize_gemini_serialized_image(ref, job_id="job-5")
    assert isinstance(result, Image.Image)


def test_bytes_with_mime_materializes_to_part() -> None:
    entry = SerializedImagePayloadEntry(
        manifest_entry_id="IMG_001",
        source_image_id="asset-1",
        role=ExecutionImageRole.PRIMARY_EVIDENCE,
        payload_ordinal=1,
        provider_image_position=0,
        mime_type="image/png",
        encoded_resource=b"\x89PNG\r\n\x1a\n",
    )
    result = materialize_gemini_serialized_image(entry, job_id="job-5")
    assert isinstance(result, types.Part)
    assert result.inline_data is not None
    assert result.inline_data.mime_type == "image/png"


def test_bytes_without_mime_fails() -> None:
    entry = SerializedImagePayloadEntry(
        manifest_entry_id="IMG_001",
        source_image_id="asset-1",
        role=ExecutionImageRole.PRIMARY_EVIDENCE,
        payload_ordinal=1,
        provider_image_position=0,
        mime_type="",
        encoded_resource=b"raw",
    )
    with pytest.raises(ProviderImageExecutionError) as exc:
        materialize_gemini_serialized_image(entry, job_id="job-5")
    assert exc.value.code == PROVIDER_IMAGE_SERIALIZATION_FAILED


def test_unsupported_mime_fails() -> None:
    entry = SerializedImagePayloadEntry(
        manifest_entry_id="IMG_001",
        source_image_id="asset-1",
        role=ExecutionImageRole.PRIMARY_EVIDENCE,
        payload_ordinal=1,
        provider_image_position=0,
        mime_type="image/tiff",
        encoded_resource=b"raw",
    )
    with pytest.raises(ProviderImageExecutionError) as exc:
        materialize_gemini_serialized_image(entry, job_id="job-5")
    assert exc.value.code == PROVIDER_IMAGE_UNSUPPORTED_FORMAT


def test_unsupported_resource_type_fails() -> None:
    entry = SerializedImagePayloadEntry(
        manifest_entry_id="IMG_001",
        source_image_id="asset-1",
        role=ExecutionImageRole.PRIMARY_EVIDENCE,
        payload_ordinal=1,
        provider_image_position=0,
        mime_type="image/jpeg",
        encoded_resource=object(),
    )
    with pytest.raises(ProviderImageExecutionError) as exc:
        materialize_gemini_serialized_image(entry, job_id="job-5")
    assert exc.value.code == PROVIDER_IMAGE_SERIALIZATION_FAILED


def test_build_contents_preserves_order_and_metadata() -> None:
    _, _, serialized, _ = _five_photo_bundle(with_reference=True)
    contents, order = build_gemini_contents_from_serialized(
        main_prompt_text="PROMPT",
        serialized=serialized,
        job_id="job-5",
    )
    image_order = [
        e for e in order if e.get("kind") in ("reference", "primary_evidence")
    ]
    assert [e["manifest_entry_id"] for e in image_order] == [
        e.manifest_entry_id for e in serialized.entries
    ]
    assert all("source_image_id" in e for e in image_order)
    assert all("provider_image_position" in e for e in image_order)


def test_build_contents_has_no_raw_ndarray() -> None:
    _, _, serialized, _ = _five_photo_bundle()
    contents, _ = build_gemini_contents_from_serialized(
        main_prompt_text="PROMPT",
        serialized=serialized,
        job_id="job-5",
    )
    for item in contents:
        assert not isinstance(item, np.ndarray)
    image_items = [c for c in contents if not isinstance(c, str)]
    assert len(image_items) == 5
    assert all(_is_gemini_compatible_image_item(item) for item in image_items)


def test_five_photo_canonical_job_shape_regression() -> None:
    """Reproduce reported V3 photo job: 5 frames, canonical provider request, serialized path."""
    manifest, req, serialized, _ = _five_photo_bundle()
    projection = build_prompt_image_projection_from_manifest(manifest)
    llm_request = LLMRequest(
        job_id="job-5",
        frames=[],
        frame_refs=list(manifest.primary_source_image_ids()),
        prompt="PROMPT",
        schema_version="v2.1",
        metadata={
            "prompt_composition": {
                "execution_image_manifest": manifest.to_dict(),
                "prompt_image_projection": projection.to_dict(),
            }
        },
        frames_nd=[np.zeros((4, 4, 3), dtype=np.uint8) for _ in range(5)],
        canonical_provider_payload_required=True,
        image_execution_contract=IMAGE_EXECUTION_CONTRACT_CANONICAL_MANIFEST,
        provider_execution_request=req,
    )

    resolved = resolve_serialized_payload_for_adapter(llm_request, provider="gemini")
    assert resolved is not None
    contents, _ = build_gemini_contents_from_serialized(
        main_prompt_text="PROMPT",
        serialized=resolved,
        job_id="job-5",
    )
    image_items = [c for c in contents if not isinstance(c, str)]
    assert len(image_items) == 5
    assert all(_is_gemini_compatible_image_item(item) for item in image_items)

    mock_client = MagicMock()
    mock_client.generate_global_analysis_structured.return_value = (
        '{"total_entities_detected": 0, "entities": []}'
    )
    analyzer = GeminiGlobalAnalyzer(mock_client, prompt_text="PROMPT")
    analyzer.analyze_video_frames(
        [np.zeros((8, 8, 3), dtype=np.uint8) for _ in range(5)],
        frame_refs=list(manifest.primary_source_image_ids()),
        request_metadata=llm_request.metadata,
        llm_request=llm_request,
    )
    sent_contents = mock_client.generate_global_analysis_structured.call_args.kwargs["contents"]
    sent_images = [c for c in sent_contents if not isinstance(c, str)]
    assert len(sent_images) == 5
    assert all(_is_gemini_compatible_image_item(item) for item in sent_images)
    assert not any(isinstance(item, np.ndarray) for item in sent_contents)
