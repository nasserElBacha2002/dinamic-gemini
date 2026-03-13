"""Epic 3.1.A — Image identity for job photos.

Provides stable image_id generation and helpers to load image metadata from
the input manifest for analysis request enrichment.

Persistence: Epic A stores image identity only through the manifest (input_manifest.json).
This is the current persistence mechanism for image metadata, not the final domain model.
Full traceability persistence (e.g. result-to-image mappings) is left for Epic 3.1.B.

No traceability parsing or response validation in this module.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class JobImage:
    """Metadata for one uploaded image in a job (Epic 3.1.A).

    Used for prompt enrichment. All fields are 1-based / user-facing where applicable.
    """

    image_id: str
    original_filename: str
    upload_order: int  # 1-based logical order
    storage_path: str


def generate_image_id(upload_order: int) -> str:
    """Generate a unique image_id for a photo within a job.

    Convention: img_001, img_002, ... (1-based, zero-padded to 3 digits).
    Stable and deterministic for a given upload order.

    Args:
        upload_order: 1-based index of the image in the upload batch.

    Returns:
        Image id string, e.g. "img_001".

    Raises:
        ValueError: If upload_order is not a positive integer.
    """
    if not isinstance(upload_order, int):
        raise ValueError(
            f"upload_order must be an int, got {type(upload_order).__name__!r}"
        )
    if upload_order < 1:
        raise ValueError(
            f"upload_order must be >= 1 (1-based), got {upload_order!r}"
        )
    return f"img_{upload_order:03d}"


def load_job_images_from_manifest(
    manifest_path: Path,
    photos_dir_rel: str,
) -> List[JobImage]:
    """Load job image metadata from input_manifest.json for prompt enrichment.

    Epic A uses the manifest as the source of truth for image identity. Entries
    without image_id (legacy manifests) are skipped and no enrichment is produced;
    this is intentional for backward compatibility.

    Args:
        manifest_path: Path to input_manifest.json.
        photos_dir_rel: Relative photos directory (e.g. "run/input_photos").

    Returns:
        List of JobImage in manifest order. Empty if manifest missing, not photos,
        or no entries have image_id (legacy).
    """
    if not manifest_path.exists():
        return []
    try:
        data = manifest_path.read_text(encoding="utf-8")
        manifest = json.loads(data)
    except (OSError, ValueError):
        return []
    if manifest.get("input_type") != "photos":
        return []
    photos_list = manifest.get("photos") or []
    result: List[JobImage] = []
    seen_ids: set[str] = set()
    for position_1based, entry in enumerate(
        sorted(photos_list, key=lambda x: x.get("index", 0)), start=1
    ):
        image_id = entry.get("image_id")
        if not image_id or not isinstance(image_id, str):
            logger.debug(
                "Manifest entry at position %s missing or invalid image_id (legacy manifest); skipping for Epic A enrichment",
                position_1based,
            )
            continue
        image_id = image_id.strip()
        if not image_id:
            continue
        if image_id in seen_ids:
            logger.warning(
                "Duplicate image_id %r in manifest at position %s; skipping duplicate",
                image_id,
                position_1based,
            )
            continue
        seen_ids.add(image_id)

        stored = entry.get("stored_filename") or ""
        if not stored:
            continue

        # upload_order: 1-based. Manifest "index" from our writer is 1-based; legacy may use 0-based.
        raw_index = entry.get("index")
        if isinstance(raw_index, (int, float)) and int(raw_index) >= 1:
            upload_order = int(raw_index)
        else:
            upload_order = position_1based

        original_filename = entry.get("original_filename") or stored
        storage_path = (
            f"{photos_dir_rel.rstrip('/')}/{stored}" if photos_dir_rel else stored
        )
        result.append(
            JobImage(
                image_id=image_id,
                original_filename=original_filename,
                upload_order=upload_order,
                storage_path=storage_path,
            )
        )
    return result
