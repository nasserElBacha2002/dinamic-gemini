"""
Shared visual-reference attachment preparation for global analysis (provider-neutral).

Loads original images with EXIF orientation preserved. Provider-specific resize / JPEG
normalization happens once in the LLM adapter (not here) to avoid double re-compression.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.pipeline.contracts.analysis_context import AnalysisContext

logger = logging.getLogger(__name__)


def attachment_name_from_path(path: Path) -> str:
    name = path.name.strip()
    return name or str(path)


def build_primary_evidence_attachments(
    frame_paths: list[Path],
    frame_refs: list[str],
) -> list[dict[str, Any]]:
    attachments: list[dict[str, Any]] = []
    for index, path in enumerate(frame_paths):
        ref = frame_refs[index] if index < len(frame_refs) else ""
        attachments.append(
            {
                "role": "primary_evidence",
                "index": index,
                "frame_ref": ref or None,
                "filename": attachment_name_from_path(path),
            }
        )
    return attachments


def load_pil_from_path(path: Path) -> Any:  # PIL.Image.Image | None
    """Load image from path as PIL RGB with EXIF transpose; return None if unreadable.

    Prefer Pillow over OpenCV so EXIF orientation metadata is available before measuring size.
    """
    try:
        from PIL import Image, ImageOps
    except ImportError:
        raise ImportError(
            "Pillow required for visual reference loading. Install with: pip install pillow"
        )
    try:
        with Image.open(path) as opened:
            transposed = ImageOps.exif_transpose(opened)
            work = transposed if transposed is not None else opened
            img = work.convert("RGB")
            img.load()
            return img
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Visual reference load failed via Pillow: %s (%s)",
            path,
            exc,
        )
        return None


def prepare_visual_reference_inputs(
    analysis_context: AnalysisContext | None,
    *,
    job_id: str,
    image_policy: Any | None = None,
) -> tuple[list[Any], list[dict[str, Any]], list[str]]:
    """Load visual references for LLM context (original bytes / PIL, EXIF-aware).

    ``image_policy`` is accepted for call-site compatibility but sizing/JPEG conversion
    is deferred to the provider adapter (single normalize + final base64 validation).

    Policy for corrupt / missing references (domain-aligned with missing-file skips):
    - Log a warning, mark ``resolved=False``, omit from ``loaded_images``.
    - Do **not** attach unreadable bytes.
    - Primary evidence failures remain blocking at the adapter encode path.
    """
    del image_policy  # sizing is provider-adapter responsibility
    if not analysis_context or not analysis_context.visual_references:
        return [], [], []

    loaded_images: list[Any] = []
    attachments: list[dict[str, Any]] = []
    resolved_reference_ids: list[str] = []
    for index, ref in enumerate(analysis_context.visual_references):
        source_path = (ref.source_path or "").strip()
        resolved_path = (ref.resolved_path or "").strip() or None
        resolved = False
        if resolved_path:
            path = Path(resolved_path)
            if path.is_file():
                pil_img = load_pil_from_path(path)
                if pil_img is not None:
                    loaded_images.append(pil_img)
                    resolved = True
                    resolved_reference_ids.append(ref.reference_id)
            else:
                logger.warning(
                    "Visual reference file not found, skipping: %s",
                    path,
                    extra={"job_id": job_id},
                )
        attachments.append(
            {
                "role": "visual_reference",
                "index": index,
                "reference_id": ref.reference_id,
                "filename": Path(source_path).name or source_path or ref.reference_id,
                "mime_type": ref.mime_type,
                "resolved": resolved,
            }
        )
    return loaded_images, attachments, resolved_reference_ids
