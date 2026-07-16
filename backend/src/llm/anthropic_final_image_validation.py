"""Final-gate validation of Anthropic Messages API image blocks.

Inspects the exact base64 bytes that will be passed to ``messages.create``.
Never trusts intermediate NormalizedImage metadata, filename, or prep-layer sizes.
"""

from __future__ import annotations

import base64
import io
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageOps

from src.llm.multimodal_image_normalization import (
    MultimodalNormalizationContext,
    ProviderImageNormalizationError,
    ProviderImagePolicy,
    normalize_multimodal_image,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AnthropicImageBlockMetadata:
    """Parallel metadata for one Anthropic ``type=image`` content block (not sent to SDK)."""

    content_index: int
    role: str
    source_id: str | None
    manifest_entry_id: str | None
    reference_id: str | None


@dataclass(frozen=True)
class ValidatedImageBlock:
    content_index: int
    width: int
    height: int
    byte_len: int
    media_type: str
    was_finally_repaired: bool
    role: str
    source_id: str | None
    original_mime_type: str | None
    final_media_type: str


def _order_entry_for_index(
    multimodal_order: Sequence[dict[str, Any]], content_index: int
) -> dict[str, Any] | None:
    for entry in multimodal_order:
        if int(entry.get("index", -1)) == content_index:
            return entry
    return None


def _role_and_ids_from_order(
    order_entry: dict[str, Any] | None,
) -> tuple[str, str | None, str | None, str | None]:
    if not order_entry:
        return "unknown", None, None, None
    kind = str(order_entry.get("kind") or "")
    if kind in {"reference", "visual_reference"}:
        role = "visual_reference"
    elif kind in {"primary_evidence", "primary"}:
        role = "primary_evidence"
    else:
        role = kind or "unknown"
    source_id = order_entry.get("source_image_id")
    if source_id is not None:
        source_id = str(source_id)
    reference_id = order_entry.get("reference_id")
    if reference_id is not None:
        reference_id = str(reference_id)
    if role == "visual_reference" and not reference_id and source_id:
        reference_id = source_id
    manifest_entry_id = order_entry.get("manifest_entry_id")
    if manifest_entry_id is not None:
        manifest_entry_id = str(manifest_entry_id)
    return role, source_id, manifest_entry_id, reference_id


def measure_base64_image_dimensions(base64_data: str) -> tuple[int, int, bytes]:
    """Decode base64 → EXIF-aware dimensions of the exact bytes that would be sent."""
    try:
        raw = base64.b64decode(base64_data, validate=True)
    except Exception as exc:  # noqa: BLE001
        raise ProviderImageNormalizationError(
            f"invalid base64 image data: {exc}",
            code="PROVIDER_IMAGE_NORMALIZATION_FAILED",
        ) from exc
    if not raw:
        raise ProviderImageNormalizationError(
            "empty decoded image bytes",
            code="PROVIDER_IMAGE_NORMALIZATION_FAILED",
        )
    try:
        with Image.open(io.BytesIO(raw)) as image:
            checked = ImageOps.exif_transpose(image)
            work = checked if checked is not None else image
            width, height = work.size
            work.load()
    except ProviderImageNormalizationError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ProviderImageNormalizationError(
            f"failed to inspect final image bytes: {exc}",
            code="PROVIDER_IMAGE_NORMALIZATION_FAILED",
        ) from exc
    if width <= 0 or height <= 0:
        raise ProviderImageNormalizationError(
            "non-positive final image dimensions",
            code="PROVIDER_IMAGE_NORMALIZATION_FAILED",
        )
    return width, height, raw


def _sniff_original_mime(raw: bytes, declared: str | None) -> str | None:
    try:
        with Image.open(io.BytesIO(raw)) as image:
            fmt = (image.format or "").upper()
    except Exception:  # noqa: BLE001
        return declared
    mapping = {
        "JPEG": "image/jpeg",
        "JPG": "image/jpeg",
        "PNG": "image/png",
        "WEBP": "image/webp",
        "GIF": "image/gif",
    }
    return mapping.get(fmt) or declared


def normalize_and_validate_anthropic_content(
    content: list[dict[str, Any]],
    *,
    policy: ProviderImagePolicy,
    multimodal_order: Sequence[dict[str, Any]] | None = None,
    ctx: MultimodalNormalizationContext | None = None,
) -> tuple[list[dict[str, Any]], list[ValidatedImageBlock], list[AnthropicImageBlockMetadata]]:
    """Ensure every final ``type=image`` block complies with ``policy.max_dimension``.

    Oversized blocks are defensively re-normalized; if still over limit, raises
    ``ProviderImageNormalizationError`` with ``PROVIDER_IMAGE_DIMENSION_EXCEEDED``.
    """
    order = list(multimodal_order or ())
    local_ctx = ctx or MultimodalNormalizationContext()
    out: list[dict[str, Any]] = []
    validated: list[ValidatedImageBlock] = []
    meta_blocks: list[AnthropicImageBlockMetadata] = []

    for index, block in enumerate(content):
        if not isinstance(block, dict) or block.get("type") != "image":
            out.append(block)
            continue

        source = block.get("source")
        if not isinstance(source, dict):
            raise ProviderImageNormalizationError(
                f"content[{index}] image block missing source",
                code="PROVIDER_INVALID_MULTIMODAL_REQUEST",
            )
        media_type = str(source.get("media_type") or "")
        b64 = source.get("data")
        if not isinstance(b64, str) or not b64:
            raise ProviderImageNormalizationError(
                f"content[{index}] image block missing base64 data",
                code="PROVIDER_INVALID_MULTIMODAL_REQUEST",
            )

        order_entry = _order_entry_for_index(order, index)
        role, source_id, manifest_entry_id, reference_id = _role_and_ids_from_order(order_entry)
        identity = source_id or reference_id or manifest_entry_id

        width, height, raw = measure_base64_image_dimensions(b64)
        original_mime = _sniff_original_mime(raw, media_type or None)
        was_repaired = False
        final_media_type = media_type or "image/jpeg"
        final_b64 = b64
        final_width, final_height = width, height
        final_raw = raw

        if max(width, height) > policy.max_dimension:
            normalized = normalize_multimodal_image(
                raw,
                source_id=identity,
                role=role,
                policy=policy,
                mime_type_hint=original_mime,
                ctx=local_ctx,
                use_cache=True,
            )
            final_raw = normalized.data
            final_b64 = base64.standard_b64encode(final_raw).decode("ascii")
            final_width, final_height = normalized.width, normalized.height
            final_media_type = normalized.mime_type
            was_repaired = True
            # Re-measure exact bytes about to be sent (never trust NormalizedImage alone).
            re_w, re_h, re_raw = measure_base64_image_dimensions(final_b64)
            final_width, final_height, final_raw = re_w, re_h, re_raw
            if max(final_width, final_height) > policy.max_dimension:
                raise ProviderImageNormalizationError(
                    f"final image content[{index}] still exceeds max_dimension="
                    f"{policy.max_dimension} after repair ({final_width}x{final_height})",
                    code="PROVIDER_IMAGE_DIMENSION_EXCEEDED",
                    source_id=identity,
                    role=role,
                )

        if max(final_width, final_height) > policy.max_dimension:
            raise ProviderImageNormalizationError(
                f"final image content[{index}] exceeds max_dimension="
                f"{policy.max_dimension} ({final_width}x{final_height})",
                code="PROVIDER_IMAGE_DIMENSION_EXCEEDED",
                source_id=identity,
                role=role,
            )

        new_block = {
            "type": "image",
            "source": {
                "type": str(source.get("type") or "base64"),
                "media_type": final_media_type,
                "data": final_b64,
            },
        }
        out.append(new_block)
        meta = AnthropicImageBlockMetadata(
            content_index=index,
            role=role,
            source_id=source_id,
            manifest_entry_id=manifest_entry_id,
            reference_id=reference_id,
        )
        meta_blocks.append(meta)
        validated.append(
            ValidatedImageBlock(
                content_index=index,
                width=final_width,
                height=final_height,
                byte_len=len(final_raw),
                media_type=final_media_type,
                was_finally_repaired=was_repaired,
                role=role,
                source_id=source_id,
                original_mime_type=original_mime,
                final_media_type=final_media_type,
            )
        )
        logger.info(
            "anthropic_final_image_validated",
            extra={
                "event": "anthropic_final_image_validated",
                "content_index": index,
                "role": role,
                "source_id": source_id,
                "manifest_entry_id": manifest_entry_id,
                "reference_id": reference_id,
                "width": final_width,
                "height": final_height,
                "bytes": len(final_raw),
                "media_type": final_media_type,
                "original_mime_type": original_mime,
                "final_media_type": final_media_type,
                "was_finally_repaired": was_repaired,
                "max_dimension_allowed": policy.max_dimension,
            },
        )

    return out, validated, meta_blocks
