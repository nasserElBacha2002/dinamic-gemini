"""Stage 2.2.C — Photo normalization: resize, JPEG re-encode, enforce limits.

Pure helpers for decoding, resizing, and encoding images. Used by
normalize_photos_for_job to produce run_dir/input_photos_normalized/ and
update the manifest so the pipeline consumes only normalized images for photos jobs.

v3.1.1: HEIC/HEIF supported via pillow-heif; converted to pipeline-safe JPEG in normalization.
"""

import io
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

HEIC_EXTENSIONS = (".heic", ".heif")

_heif_opener_registered = False


def _decode_heic_to_bgr(raw: bytes) -> np.ndarray:
    """Decode HEIC/HEIF bytes to BGR ndarray using pillow-heif + Pillow.

    Normalized output is always written as JPEG via encode_jpeg; downstream
    stages consume run_dir/input_photos_normalized/*.jpg and manifest
    stored_normalized_filename (e.g. 0001_<slug>.jpg).

    Raises:
        ImportError: If pillow_heif is not installed.
        ValueError: If decode fails.
    """
    global _heif_opener_registered
    try:
        import pillow_heif  # noqa: F401
        from PIL import Image
    except ImportError as e:
        raise ValueError(
            "HEIC/HEIF conversion requires pillow-heif; install with: pip install pillow-heif"
        ) from e
    if not _heif_opener_registered:
        pillow_heif.register_heif_opener()
        _heif_opener_registered = True
    pil_rgb: Image.Image = Image.open(io.BytesIO(raw)).convert("RGB")
    arr = np.array(pil_rgb)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def decode_image_bytes(raw: bytes) -> np.ndarray:
    """Decode image bytes (JPEG/PNG/etc.) to BGR ndarray.

    Args:
        raw: Encoded image bytes.

    Returns:
        BGR image as numpy array (h, w, 3), uint8.

    Raises:
        ValueError: If bytes are empty or not a valid image.
    """
    if not raw:
        raise ValueError("empty image bytes")
    nparr = np.frombuffer(raw, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("decoded bytes are not a valid image")
    return img


def decode_image_bytes_or_heic(raw: bytes, src_path: Optional[Path] = None) -> Tuple[np.ndarray, bool]:
    """Decode image bytes to BGR ndarray. Tries OpenCV first; for .heic/.heif uses pillow-heif.

    Returns:
        (BGR ndarray, was_converted_from_heic).

    Raises:
        ValueError: If decode fails.
    """
    if not raw:
        raise ValueError("empty image bytes")
    nparr = np.frombuffer(raw, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is not None:
        return img, False
    suffix = (src_path.suffix or "").lower() if src_path else ""
    if suffix in HEIC_EXTENSIONS:
        bgr = _decode_heic_to_bgr(raw)
        return bgr, True
    raise ValueError("decoded bytes are not a valid image")


def normalize_image(
    img: np.ndarray,
    max_side: int,
    min_side: Optional[int] = None,
) -> np.ndarray:
    """Resize image so longest side <= max_side; optionally enforce min_side.

    Does not upscale. If both dimensions are already <= max_side, returns a copy
    unless min_side is set and a side is smaller (then raises).

    Args:
        img: BGR image (h, w, 3).
        max_side: Maximum allowed for the longest side (px).
        min_side: If set, both width and height must be >= min_side else ValueError.

    Returns:
        Resized BGR image (same dtype). May be the same as img if no resize needed.
    """
    h, w = img.shape[:2]
    min_side_val = int(min_side) if isinstance(min_side, (int, float)) else None
    if min_side_val is not None and (w < min_side_val or h < min_side_val):
        raise ValueError(
            f"image size {w}x{h} is below minimum side {min_side_val}"
        )
    max_side_val = int(max_side) if isinstance(max_side, (int, float)) else 1280
    longest = max(w, h)
    if longest <= max_side_val:
        return img.copy()
    scale = max_side_val / longest
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    return resized


def encode_jpeg(img: np.ndarray, quality: int) -> bytes:
    """Encode BGR image as JPEG bytes.

    Args:
        img: BGR image (h, w, 3), uint8.
        quality: JPEG quality 1–100.

    Returns:
        Encoded JPEG bytes.
    """
    quality = max(1, min(100, quality))
    encode_param = [cv2.IMWRITE_JPEG_QUALITY, quality]
    success, buf = cv2.imencode(".jpg", img, encode_param)
    if not success or buf is None:
        raise ValueError("cv2.imencode failed for JPEG")
    return buf.tobytes()


# Re-export so callers that import from frames.normalize keep working
from src.utils.validation import validate_relative_path  # noqa: F401

def normalize_photo_file(
    src_path: Path,
    dst_path: Path,
    max_side: int,
    jpeg_quality: int,
    min_side: Optional[int] = None,
    max_single_bytes: Optional[int] = None,
) -> Dict[str, Any]:
    """Read photo from src_path, normalize (resize + JPEG), write to dst_path.

    Args:
        src_path: Path to original image file.
        dst_path: Path to write normalized JPEG.
        max_side: Max longest side (px).
        jpeg_quality: JPEG quality 1–100.
        min_side: If set, fail when any side is smaller.
        max_single_bytes: If set, fail when original file size exceeds this (bytes).

    Returns:
        Metrics dict: original_bytes, normalized_bytes, original_w, original_h,
        normalized_w, normalized_h, resized (bool).

    Raises:
        ValueError: Decode error, too small, size over limit, or encode error.
        FileNotFoundError: src_path does not exist.
    """
    src_path = Path(src_path)
    dst_path = Path(dst_path)
    if dst_path.suffix.lower() not in (".jpg", ".jpeg"):
        raise ValueError(f"normalized output path must be .jpg/.jpeg for pipeline safety: {dst_path}")
    if not src_path.is_file():
        raise FileNotFoundError(f"photo file not found: {src_path}")

    raw = src_path.read_bytes()
    original_bytes = len(raw)
    if max_single_bytes is not None and original_bytes > max_single_bytes:
        raise ValueError(
            f"photo size {original_bytes} bytes exceeds limit {max_single_bytes}"
        )
    img, converted_from_heic = decode_image_bytes_or_heic(raw, src_path)
    h, w = img.shape[:2]

    resized_img = normalize_image(img, max_side, min_side)
    resized = resized_img.shape != img.shape or (
        (resized_img.shape[1], resized_img.shape[0]) != (w, h)
    )
    out_bytes = encode_jpeg(resized_img, jpeg_quality)

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    dst_path.write_bytes(out_bytes)

    nh, nw = resized_img.shape[:2]
    return {
        "original_bytes": original_bytes,
        "normalized_bytes": len(out_bytes),
        "original_w": w,
        "original_h": h,
        "normalized_w": nw,
        "normalized_h": nh,
        "resized": resized,
        "converted_from_heic": converted_from_heic,
        "original_filename": src_path.name,
        "normalized_filename": dst_path.name,
    }


def _normalized_filename_from_stored(stored_filename: str, index: int) -> str:
    """Derive deterministic normalized filename from stored_filename and index.

    Format 0001_<slug>.jpg; slug is stem of stored_filename, stripping leading index prefix if present.
    """
    stem = Path(stored_filename).stem
    prefix = f"{index:04d}_"
    if stem.startswith(prefix):
        slug = stem[len(prefix) :]
    else:
        slug = stem
    if not slug:
        slug = "image"
    return f"{index:04d}_{slug}.jpg"


def normalize_photos_for_job(
    run_dir: Path,
    settings: Any,
    manifest_path: Optional[Path] = None,
    photos_dir: Optional[Path] = None,
    normalized_dir: Optional[Path] = None,
    execution_log: Optional[Any] = None,
) -> None:
    """Read manifest, normalize each photo into input_photos_normalized/, update manifest.

    Uses run_dir/input_manifest.json and run_dir/input_photos/ by default.
    Writes to run_dir/input_photos_normalized/. Updates manifest with
    total_bytes_normalized, normalization config snapshot, and per-photo
    stored_normalized_filename, normalized_bytes, normalized_w/h, resized.
    Manifest is written atomically (temp file then replace).
    If execution_log is provided (ExecutionLogWriter), logs HEIC conversions.

    Raises:
        FileNotFoundError: Manifest or a listed photo missing.
        ValueError: Invalid image, too small, or decode/encode error.
    """
    run_dir = Path(run_dir)
    manifest_path = manifest_path or run_dir / "input_manifest.json"
    photos_dir = photos_dir or run_dir / "input_photos"
    normalized_dir = normalized_dir or run_dir / "input_photos_normalized"

    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest not found: {manifest_path}")
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    if manifest.get("input_type") != "photos":
        raise ValueError(f"manifest input_type is not 'photos': {manifest.get('input_type')}")

    photos_list = manifest.get("photos") or []
    current_snapshot = _normalization_config_snapshot(settings)
    if photos_list and photos_use_normalized(run_dir, manifest) and _normalization_snapshot_matches(
        manifest.get("normalization"), current_snapshot
    ):
        return

    if not photos_list:
        manifest["total_bytes_normalized"] = 0
        manifest["normalization"] = _normalization_config_snapshot(settings)
        _write_manifest_atomic(manifest_path, manifest)
        normalized_dir.mkdir(parents=True, exist_ok=True)
        return

    if not photos_dir.is_dir():
        raise FileNotFoundError(f"photos directory not found: {photos_dir}")

    max_side = getattr(settings, "photo_resize_max_side", 1280)
    jpeg_quality = getattr(settings, "photo_jpeg_quality", 85)
    min_side = getattr(settings, "photos_min_side", None) or 320
    if not isinstance(max_side, (int, float)):
        max_side = 1280
    max_side = int(max_side)
    if not isinstance(jpeg_quality, (int, float)):
        jpeg_quality = 85
    jpeg_quality = int(jpeg_quality)
    if not isinstance(min_side, (int, float)):
        min_side = 320
    min_side = int(min_side)
    max_single_bytes = getattr(settings, "photos_max_single_bytes", None)
    if max_single_bytes is not None and not isinstance(max_single_bytes, (int, float)):
        max_single_bytes = None
    if max_single_bytes is not None:
        max_single_bytes = int(max_single_bytes)

    total_bytes_normalized = 0
    total_bytes_original = manifest.get("total_bytes_original", 0)

    normalized_dir.mkdir(parents=True, exist_ok=True)

    for entry in sorted(photos_list, key=lambda x: x.get("index", 0)):
        index = entry.get("index", 0)
        stored = entry.get("stored_filename") or ""
        if not stored:
            raise ValueError("manifest photo entry missing stored_filename")
        src_path = photos_dir / stored
        stored_normalized = _normalized_filename_from_stored(stored, index)
        dst_path = normalized_dir / stored_normalized

        try:
            metrics = normalize_photo_file(
                src_path,
                dst_path,
                max_side=max_side,
                jpeg_quality=jpeg_quality,
                min_side=min_side,
                max_single_bytes=max_single_bytes,
            )
        except ValueError as e:
            raise ValueError(f"photo {stored}: {e}") from e

        if metrics.get("converted_from_heic") and execution_log:
            orig_name = metrics.get("original_filename", stored)
            norm_name = metrics.get("normalized_filename", stored_normalized)
            execution_log.info(
                "InputPreparationStage",
                f"Converted HEIC to JPG | original={orig_name} normalized={norm_name}",
                payload={"original": orig_name, "normalized": norm_name},
            )

        total_bytes_normalized += metrics["normalized_bytes"]
        entry["stored_normalized_filename"] = stored_normalized
        entry["normalized_bytes"] = metrics["normalized_bytes"]
        entry["normalized_w"] = metrics["normalized_w"]
        entry["normalized_h"] = metrics["normalized_h"]
        entry["resized"] = metrics["resized"]

    manifest["total_bytes_normalized"] = total_bytes_normalized
    if "total_bytes_original" not in manifest:
        manifest["total_bytes_original"] = total_bytes_original
    manifest["normalization"] = _normalization_config_snapshot(settings)

    _write_manifest_atomic(manifest_path, manifest)
    logger.info(
        "Photos normalized: %d files, original=%s bytes, normalized=%s bytes",
        len(photos_list),
        total_bytes_original,
        total_bytes_normalized,
    )


def _normalization_config_snapshot(settings: Any) -> Dict[str, Any]:
    """Build manifest snapshot of normalization config (values as int for comparison)."""
    def _int_val(val: Any, default: int) -> int:
        if isinstance(val, (int, float)):
            return int(val)
        return default
    return {
        "resize_max_side": _int_val(getattr(settings, "photo_resize_max_side", 1280), 1280),
        "jpeg_quality": _int_val(getattr(settings, "photo_jpeg_quality", 85), 85),
        "min_side": _int_val(getattr(settings, "photos_min_side", 320), 320),
    }


def _normalization_snapshot_matches(
    snapshot: Optional[Dict[str, Any]], current: Dict[str, Any]
) -> bool:
    """Return True if snapshot (from manifest) matches current config (same keys and values)."""
    if not snapshot or not isinstance(snapshot, dict):
        return False
    for key in ("resize_max_side", "jpeg_quality", "min_side"):
        if snapshot.get(key) != current.get(key):
            return False
    return True


def _write_manifest_atomic(manifest_path: Path, manifest: Dict[str, Any]) -> None:
    """Write manifest JSON atomically (temp file then replace). fd closed via fdopen."""
    manifest_path = Path(manifest_path)
    fd, tmp = tempfile.mkstemp(
        dir=manifest_path.parent,
        prefix="input_manifest.",
        suffix=".json",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        Path(tmp).replace(manifest_path)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise


def photos_use_normalized(run_dir: Path, manifest: Dict[str, Any]) -> bool:
    """Return True if all photos have stored_normalized_filename and normalized dir exists."""
    photos_list = manifest.get("photos") or []
    if not photos_list:
        return False
    for entry in photos_list:
        if not entry.get("stored_normalized_filename"):
            return False
    normalized_dir = run_dir / "input_photos_normalized"
    if not normalized_dir.is_dir():
        return False
    for entry in photos_list:
        name = entry.get("stored_normalized_filename")
        if name and not (normalized_dir / name).is_file():
            return False
    return True
