"""Stage 2.2.A — Validate and persist photo inputs (form-data uploads) for create-inventory."""

import json
import logging
from pathlib import Path
from typing import Any, List, Tuple

from src.io.sanitize import photo_stored_filename

logger = logging.getLogger(__name__)


def _validate_image_bytes(raw: bytes) -> str:
    """Validate bytes as image (cv2.imdecode). Returns error message or empty string."""
    if not raw:
        return "empty image bytes"
    try:
        import cv2
        import numpy as np
        nparr = np.frombuffer(raw, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return "decoded bytes are not a valid image"
    except Exception as e:
        return f"image validation failed: {e}"
    return ""


async def persist_photos_from_uploads(
    job_dir: Path,
    uploads: List[Any],
    max_total_bytes: int,
    chunk_size: int = 1024 * 1024,
) -> Tuple[dict, str, str]:
    """Read uploads (UploadFile-like), validate as images, write to job_dir/run/input_photos/, write manifest.

    Each item in uploads must have .filename and .read() (e.g. Starlette UploadFile).
    Enforces max_total_bytes across all files (streaming).

    Returns:
        (manifest_dict, input_manifest_path_rel, photos_dir_rel) where paths are relative to job_dir.
    Raises:
        ValueError: validation error (count, size, or image validity).
    """
    run_dir = job_dir / "run"
    input_photos_dir = run_dir / "input_photos"
    input_photos_dir.mkdir(parents=True, exist_ok=True)
    total_bytes = 0
    manifest_photos: List[dict] = []
    for i, upload in enumerate(uploads, start=1):
        if not hasattr(upload, "read") or not callable(getattr(upload, "read")):
            raise ValueError("each photo must be a file upload")
        chunks: List[bytes] = []
        size_so_far = 0
        while True:
            chunk = await upload.read(chunk_size)
            if not chunk:
                break
            size_so_far += len(chunk)
            if size_so_far > max_total_bytes:
                raise ValueError(
                    f"total photo bytes exceed limit ({max_total_bytes})"
                )
            chunks.append(chunk)
        raw = b"".join(chunks)
        total_bytes += len(raw)
        if total_bytes > max_total_bytes:
            raise ValueError(
                f"total photo bytes ({total_bytes}) exceed limit ({max_total_bytes})"
            )
        err = _validate_image_bytes(raw)
        if err:
            raise ValueError(err)
        original_filename = getattr(upload, "filename", None) or f"photo_{i}.jpg"
        if not isinstance(original_filename, str):
            original_filename = str(original_filename)
        stored_name = photo_stored_filename(original_filename.strip() or f"photo_{i}.jpg", i)
        out_path = input_photos_dir / stored_name
        out_path.write_bytes(raw)
        manifest_photos.append({
            "index": i,
            "original_filename": original_filename,
            "stored_filename": stored_name,
            "bytes": len(raw),
        })
    manifest = {
        "input_type": "photos",
        "total_photos": len(uploads),
        "total_bytes_original": total_bytes,
        "photos": manifest_photos,
    }
    manifest_path = run_dir / "input_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    input_manifest_path_rel = "run/input_manifest.json"
    photos_dir_rel = "run/input_photos"
    return manifest, input_manifest_path_rel, photos_dir_rel
