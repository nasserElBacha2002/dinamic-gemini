"""
Shared visual-reference attachment preparation for global analysis (provider-neutral).

Extracted from the Gemini strategy so other pipeline providers can reuse the same attachment model.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2

from src.pipeline.contracts.analysis_context import AnalysisContext

logger = logging.getLogger(__name__)


def attachment_name_from_path(path: Path) -> str:
    name = path.name.strip()
    return name or str(path)


def build_primary_evidence_attachments(
    frame_paths: List[Path],
    frame_refs: List[str],
) -> List[Dict[str, Any]]:
    attachments: List[Dict[str, Any]] = []
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
    """Load image from path as PIL RGB; return None if missing or unreadable."""
    try:
        from PIL import Image
    except ImportError:
        raise ImportError("Pillow required for visual reference loading. Install with: pip install pillow")
    img = cv2.imread(str(path))
    if img is None:
        return None
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


def prepare_visual_reference_inputs(
    analysis_context: Optional[AnalysisContext],
    *,
    job_id: str,
) -> tuple[List[Any], List[Dict[str, Any]], List[str]]:
    if not analysis_context or not analysis_context.visual_references:
        return [], [], []

    loaded_images: List[Any] = []
    attachments: List[Dict[str, Any]] = []
    resolved_reference_ids: List[str] = []
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
