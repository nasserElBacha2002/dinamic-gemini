"""Evidence scoring utilities: sharpness (Laplacian) and deduplication (dHash)."""

from typing import Callable, List, TypeVar, Tuple

import cv2
import numpy as np

T = TypeVar("T")


def _dedupe_by_hash_set(
    items: List[T],
    get_hash: Callable[[T], int],
    threshold: int = 10,
) -> List[T]:
    """Set-based dedupe: keep item only if its hash is > threshold Hamming distance from ALL already selected.
    Deterministic (order preserved; first occurrence wins). Single implementation for all callers."""
    if not items:
        return []
    out: List[T] = [items[0]]
    selected_hashes: List[int] = [get_hash(items[0])]
    for i in range(1, len(items)):
        h = get_hash(items[i])
        min_d = min(hamming_distance(h, sh) for sh in selected_hashes)
        if min_d > threshold:
            out.append(items[i])
            selected_hashes.append(h)
    return out


def score_frame_sharpness(frame: np.ndarray) -> float:
    """Variance of Laplacian; higher = sharper. Deterministic.

    Args:
        frame: BGR image (H, W, C).

    Returns:
        float >= 0. Same frame always yields same value.
    """
    if frame is None or frame.size == 0:
        return 0.0
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def dhash_int(frame: np.ndarray, size: Tuple[int, int] = (9, 8)) -> int:
    """64-bit dHash (left-right gradient). Deterministic. Public for reuse."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, size, interpolation=cv2.INTER_AREA)
    diff = resized[:, 1:] > resized[:, :-1]
    bits = np.packbits(diff.astype(np.uint8))
    return int.from_bytes(bits.tobytes()[:8], byteorder="big")


def hamming_distance(h1: int, h2: int) -> int:
    """Number of bit differences between two 64-bit hashes."""
    return (h1 ^ h2).bit_count()


def dedupe_by_hash(
    images: List[np.ndarray],
    threshold: int = 10,
) -> List[np.ndarray]:
    """Remove visually duplicate frames by dHash. Set-based: compare to ALL selected hashes.

    Args:
        images: List of BGR frames.
        threshold: Hamming distance <= this → considered duplicate.

    Returns:
        Subset of images with duplicates removed (order preserved).
    """
    return _dedupe_by_hash_set(images, dhash_int, threshold)


def dedupe_indexed_by_hash(
    items: List[Tuple[int, np.ndarray]],
    threshold: int = 10,
) -> List[Tuple[int, np.ndarray]]:
    """Dedupe list of (index, frame) by dHash; set-based (min distance to any selected). Deterministic.

    Args:
        items: List of (index, frame).
        threshold: Hamming distance <= this → duplicate.

    Returns:
        Subset with duplicates removed, order preserved.
    """
    return _dedupe_by_hash_set(items, lambda item: dhash_int(item[1]), threshold)
