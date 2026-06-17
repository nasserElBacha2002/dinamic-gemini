"""
Phase 1 — labeled vision payloads and multimodal order metadata for global analysis.

Shared construction for OpenAI, Claude, and Gemini so primary evidence images carry explicit
``source_image_id`` labels and supplier references are marked REFERENCE_ONLY.
"""

from __future__ import annotations

from typing import Any

ROLE_REFERENCE_ONLY = "REFERENCE_ONLY"
ROLE_PRIMARY_EVIDENCE = "PRIMARY_EVIDENCE"

LLM_METADATA_KEY_FRAMES_SENT_IDS = "frames_sent_ids"
LLM_METADATA_KEY_PROMPT_LISTED_IMAGE_IDS = "prompt_listed_image_ids"
LLM_METADATA_KEY_REFERENCE_IMAGE_IDS = "reference_image_ids"
LLM_METADATA_KEY_MULTIMODAL_ORDER = "multimodal_order"
MULTIMODAL_ORDER_STATUS_PENDING = "pending_adapter_materialization"

PRIMARY_FRAME_REFS_MISMATCH = "PRIMARY_FRAME_REFS_MISMATCH"


def _validate_provider_lists_against_request_manifest(
    metadata: dict[str, Any] | None,
    frame_refs: list[str],
    reference_image_ids: list[str],
) -> None:
    """When request metadata embeds a manifest, adapter lists must match it exactly."""
    from src.pipeline.services.execution_image_manifest_payload import (
        manifest_from_request_metadata,
        validate_provider_lists_against_manifest,
    )

    manifest = manifest_from_request_metadata(metadata)
    if manifest is None:
        return
    validate_provider_lists_against_manifest(
        manifest,
        frame_refs=frame_refs,
        reference_image_ids=reference_image_ids,
    )


def validate_primary_frame_refs(
    primary_frames_nd: list[Any],
    frame_refs: list[str],
) -> None:
    """
    Ensure every primary frame has a non-empty ``source_image_id`` before building provider payloads.

    Raises:
        ValueError: When counts differ or any frame ref is empty/whitespace.
    """
    n_frames = len(primary_frames_nd)
    n_refs = len(frame_refs)
    empty_indices = [i for i, ref in enumerate(frame_refs) if not (ref or "").strip()]
    if n_frames != n_refs or empty_indices:
        raise ValueError(
            f"{PRIMARY_FRAME_REFS_MISMATCH}: primary_frame_count={n_frames}, "
            f"frame_ref_count={n_refs}, empty_ref_indices={empty_indices}"
        )


def reference_image_label(reference_id: str) -> str:
    """Text block immediately before a supplier/reference vision part."""
    rid = (reference_id or "").strip() or "unknown"
    return (
        "Reference image\n"
        f"reference_id: {rid}\n"
        f"role: {ROLE_REFERENCE_ONLY}\n"
        "Do not use this image as source_image_id."
    )


def primary_image_label(source_image_id: str, index: int) -> str:
    """Text block immediately before a primary evidence vision part."""
    sid = (source_image_id or "").strip()
    return (
        "Primary evidence image\n"
        f"source_image_id: {sid}\n"
        f"role: {ROLE_PRIMARY_EVIDENCE}\n"
        f"index: {index}"
    )


def _append_order_entry(
    order: list[dict[str, Any]],
    *,
    index: int,
    role: str,
    kind: str,
    **extra: Any,
) -> None:
    entry: dict[str, Any] = {"index": index, "role": role, "kind": kind}
    entry.update(extra)
    order.append(entry)


def build_openai_vision_content_parts(
    *,
    main_prompt_text: str,
    context_images: list[Any],
    reference_image_ids: list[str],
    primary_frames_nd: list[Any],
    frame_refs: list[str],
    request_metadata: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    OpenAI Chat Completions user ``content`` parts: main text, then labeled reference and primary pairs.
    """
    _validate_provider_lists_against_request_manifest(
        request_metadata, frame_refs, reference_image_ids
    )
    validate_primary_frame_refs(primary_frames_nd, frame_refs)
    content: list[dict[str, Any]] = [{"type": "text", "text": main_prompt_text}]
    order: list[dict[str, Any]] = []
    idx = 0
    _append_order_entry(
        order, index=idx, role="text", kind="main_prompt", char_len=len(main_prompt_text)
    )
    idx += 1

    for i, im in enumerate(context_images):
        ref_id = reference_image_ids[i] if i < len(reference_image_ids) else ""
        label = reference_image_label(ref_id)
        content.append({"type": "text", "text": label})
        _append_order_entry(
            order,
            index=idx,
            role="text",
            kind="reference_image_label",
            reference_id=ref_id or None,
        )
        idx += 1
        content.append({"type": "image_placeholder", "_image": im})
        _append_order_entry(
            order,
            index=idx,
            role="image",
            kind="reference",
            reference_id=ref_id or None,
        )
        idx += 1

    for i, nd in enumerate(primary_frames_nd):
        ref = str(frame_refs[i]).strip()
        label = primary_image_label(ref, i)
        content.append({"type": "text", "text": label})
        _append_order_entry(
            order,
            index=idx,
            role="text",
            kind="primary_image_label",
            source_image_id=ref or None,
        )
        idx += 1
        content.append({"type": "image_placeholder", "_image": nd, "_bgr": True})
        _append_order_entry(
            order,
            index=idx,
            role="image",
            kind="primary_evidence",
            source_image_id=ref or None,
        )
        idx += 1

    return content, order


def materialize_openai_content_parts(
    parts: list[dict[str, Any]],
    *,
    image_to_data_url: Any,
    bgr_to_data_url: Any,
    max_side: int,
) -> list[dict[str, Any]]:
    """Replace ``image_placeholder`` entries with OpenAI ``image_url`` parts."""
    out: list[dict[str, Any]] = []
    for part in parts:
        if part.get("type") == "image_placeholder":
            im = part["_image"]
            if part.get("_bgr"):
                url = bgr_to_data_url(im, max_side)
            else:
                url = image_to_data_url(im, max_side)
            out.append({"type": "image_url", "image_url": {"url": url, "detail": "auto"}})
        else:
            out.append(part)
    return out


def build_anthropic_message_content_parts(
    *,
    main_prompt_text: str,
    context_images: list[Any],
    reference_image_ids: list[str],
    primary_frames_nd: list[Any],
    frame_refs: list[str],
    request_metadata: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Claude message content: same labeled interleaving as OpenAI (text + image blocks)."""
    _validate_provider_lists_against_request_manifest(
        request_metadata, frame_refs, reference_image_ids
    )
    validate_primary_frame_refs(primary_frames_nd, frame_refs)
    content: list[dict[str, Any]] = [{"type": "text", "text": main_prompt_text}]
    order: list[dict[str, Any]] = []
    idx = 0
    _append_order_entry(
        order, index=idx, role="text", kind="main_prompt", char_len=len(main_prompt_text)
    )
    idx += 1

    for i, im in enumerate(context_images):
        ref_id = reference_image_ids[i] if i < len(reference_image_ids) else ""
        content.append({"type": "text", "text": reference_image_label(ref_id)})
        _append_order_entry(
            order,
            index=idx,
            role="text",
            kind="reference_image_label",
            reference_id=ref_id or None,
        )
        idx += 1
        content.append({"type": "image_placeholder", "_image": im})
        _append_order_entry(
            order,
            index=idx,
            role="image",
            kind="reference",
            reference_id=ref_id or None,
        )
        idx += 1

    for i, nd in enumerate(primary_frames_nd):
        ref = str(frame_refs[i]).strip()
        content.append({"type": "text", "text": primary_image_label(ref, i)})
        _append_order_entry(
            order,
            index=idx,
            role="text",
            kind="primary_image_label",
            source_image_id=ref or None,
        )
        idx += 1
        content.append({"type": "image_placeholder", "_image": nd, "_bgr": True})
        _append_order_entry(
            order,
            index=idx,
            role="image",
            kind="primary_evidence",
            source_image_id=ref or None,
        )
        idx += 1

    return content, order


def materialize_anthropic_content_parts(
    parts: list[dict[str, Any]],
    *,
    image_to_jpeg_bytes: Any,
    bgr_to_jpeg_bytes: Any,
    max_side: int,
    jpeg_block_factory: Any,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for part in parts:
        if part.get("type") == "image_placeholder":
            im = part["_image"]
            if part.get("_bgr"):
                data = bgr_to_jpeg_bytes(im, max_side)
            else:
                data = image_to_jpeg_bytes(im, max_side)
            out.append(jpeg_block_factory(data))
        else:
            out.append(part)
    return out


def build_gemini_interleaved_contents(
    *,
    main_prompt_text: str,
    context_images: list[Any],
    reference_image_ids: list[str],
    primary_pil_images: list[Any],
    frame_refs: list[str],
    request_metadata: dict[str, Any] | None = None,
) -> tuple[list[Any], list[dict[str, Any]]]:
    """
    Gemini ``contents``: main prompt text first, then labeled reference and primary pairs (PIL images).
    """
    _validate_provider_lists_against_request_manifest(
        request_metadata, frame_refs, reference_image_ids
    )
    validate_primary_frame_refs(primary_pil_images, frame_refs)
    contents: list[Any] = [main_prompt_text]
    order: list[dict[str, Any]] = []
    idx = 0
    _append_order_entry(
        order, index=idx, role="text", kind="main_prompt", char_len=len(main_prompt_text)
    )
    idx += 1

    for i, im in enumerate(context_images):
        ref_id = reference_image_ids[i] if i < len(reference_image_ids) else ""
        contents.append(reference_image_label(ref_id))
        _append_order_entry(
            order,
            index=idx,
            role="text",
            kind="reference_image_label",
            reference_id=ref_id or None,
        )
        idx += 1
        contents.append(im)
        _append_order_entry(
            order,
            index=idx,
            role="image",
            kind="reference",
            reference_id=ref_id or None,
        )
        idx += 1

    for i, pil in enumerate(primary_pil_images):
        ref = str(frame_refs[i]).strip()
        contents.append(primary_image_label(ref, i))
        _append_order_entry(
            order,
            index=idx,
            role="text",
            kind="primary_image_label",
            source_image_id=ref or None,
        )
        idx += 1
        contents.append(pil)
        _append_order_entry(
            order,
            index=idx,
            role="image",
            kind="primary_evidence",
            source_image_id=ref or None,
        )
        idx += 1

    return contents, order


def traceability_metadata_payload(
    *,
    frames_sent_ids: list[str],
    prompt_listed_image_ids: list[str],
    reference_image_ids: list[str],
    multimodal_order: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        LLM_METADATA_KEY_FRAMES_SENT_IDS: list(frames_sent_ids),
        LLM_METADATA_KEY_PROMPT_LISTED_IMAGE_IDS: list(prompt_listed_image_ids),
        LLM_METADATA_KEY_REFERENCE_IMAGE_IDS: list(reference_image_ids),
        LLM_METADATA_KEY_MULTIMODAL_ORDER: list(multimodal_order),
    }
