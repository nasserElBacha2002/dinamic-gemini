"""Stage 2.1.D — Evidence pack generator.

Per entity: overview frames; when bbox present, localized position/product label crops.
When bbox missing or invalid: evidence_localization = UNLOCALIZED, overview only.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from src.config import load_settings
from src.domain.entity import Entity
from src.evidence.paths import entity_evidence_path, slug
from src.evidence.scoring import dedupe_indexed_by_hash, score_frame_sharpness

logger = logging.getLogger(__name__)

EVIDENCE_LOCALIZED = "LOCALIZED"
EVIDENCE_UNLOCALIZED = "UNLOCALIZED"


def parse_bbox_to_pixels(
    bbox: Optional[List[float]],
    frame_w: int,
    frame_h: int,
) -> Optional[Tuple[int, int, int, int]]:
    """Convert bbox to pixel coords (x1, y1, x2, y2). Clamped, x2>x1, y2>y1.

    - If all coords <= 1.0: treat as normalized [0..1].
    - Else: treat as pixel coordinates.
    - Returns None if bbox invalid or result would be empty.
    """
    if not bbox or not isinstance(bbox, list) or len(bbox) != 4 or frame_w <= 0 or frame_h <= 0:
        return None
    try:
        x1, y1, x2, y2 = [float(x) for x in bbox]
    except (TypeError, ValueError):
        return None
    if all(c <= 1.0 for c in (x1, y1, x2, y2)):
        x1_px = max(0, min(frame_w, int(x1 * frame_w)))
        y1_px = max(0, min(frame_h, int(y1 * frame_h)))
        x2_px = max(0, min(frame_w, int(x2 * frame_w)))
        y2_px = max(0, min(frame_h, int(y2 * frame_h)))
    else:
        x1_px = max(0, min(frame_w, int(x1)))
        y1_px = max(0, min(frame_h, int(y1)))
        x2_px = max(0, min(frame_w, int(x2)))
        y2_px = max(0, min(frame_h, int(y2)))
    if x1_px >= x2_px or y1_px >= y2_px:
        return None
    return (x1_px, y1_px, x2_px, y2_px)


def _crop_bbox(frame: np.ndarray, bbox: List[float]) -> Optional[np.ndarray]:
    """Crop frame to bbox (normalized or pixel). Returns None if invalid."""
    h, w = frame.shape[:2]
    px = parse_bbox_to_pixels(bbox, w, h)
    if px is None:
        return None
    x1, y1, x2, y2 = px
    return frame[y1:y2, x1:x2].copy()


def _select_overview_frames(
    frames: List[np.ndarray],
    k: int,
    hash_threshold: int = 10,
) -> List[Tuple[int, np.ndarray]]:
    """Select up to k best (sharpest, set-deduped) frames. Returns list of (index, frame)."""
    if not frames or k <= 0:
        return []
    scored = [(i, frame, score_frame_sharpness(frame)) for i, frame in enumerate(frames)]
    scored.sort(key=lambda x: x[2], reverse=True)
    items = [(i, frame) for i, frame, _ in scored]
    return dedupe_indexed_by_hash(items, threshold=hash_threshold)[:k]


def _select_best_crop_candidates(
    frames: List[np.ndarray],
    bbox: List[float],
    k: int,
    hash_threshold: int = 8,
) -> List[Tuple[int, np.ndarray]]:
    """Crop bbox from each frame, score by sharpness, set-dedupe, return up to k (index, crop)."""
    crops: List[Tuple[int, np.ndarray, float]] = []
    for i, frame in enumerate(frames):
        crop = _crop_bbox(frame, bbox)
        if crop is not None and crop.size > 0:
            crops.append((i, crop, score_frame_sharpness(crop)))
    crops.sort(key=lambda x: x[2], reverse=True)
    items = [(idx, crop) for idx, crop, _ in crops]
    return dedupe_indexed_by_hash(items, threshold=hash_threshold)[:k]


def generate_evidence_pack(
    job_id: str,
    run_dir: Path,
    frames: List[np.ndarray],
    metadata: Dict[str, Any],
    entities: List[Entity],
) -> Dict[str, Any]:
    """Generate evidence pack per entity and write run/evidence/ and run/evidence_index.json.

    - Overview: sharpness + dedupe, limit K_OVERVIEW.
    - If position_label_bbox/product_label_bbox present and parse_bbox_to_pixels returns
      valid pixel coords: localized crops; evidence_localization = LOCALIZED.
    - Else (bbox missing, invalid, or degenerate): only overview; evidence_localization = UNLOCALIZED.
    - Enforce EVIDENCE_MAX_IMAGES_PER_PALLET per entity.
    - Mutates each entity: evidence_path, evidence_localization.

    Returns:
        Evidence index dict (job_id, mode, entities with evidence paths). All paths inside
        the index are relative to run_dir (same directory as evidence_index.json).
    """
    settings = load_settings()
    k_overview = getattr(settings, "evidence_k_overview", 3)
    k_pos = getattr(settings, "evidence_k_pos_candidates", 5)
    k_prod = getattr(settings, "evidence_k_prod_candidates", 5)
    max_images = getattr(settings, "evidence_max_images_per_pallet", 25)
    jpeg_quality = getattr(settings, "evidence_jpeg_quality", 85)

    run_dir = Path(run_dir)
    evidence_root = run_dir / "evidence"
    evidence_root.mkdir(parents=True, exist_ok=True)

    frame_h, frame_w = (frames[0].shape[:2]) if frames else (0, 0)

    index_entities: List[Dict[str, Any]] = []

    for entity in entities:
        entity_dir = entity_evidence_path(run_dir, entity.entity_uid)
        entity_dir.mkdir(parents=True, exist_ok=True)
        rel_evidence_dir = f"evidence/{slug(entity.entity_uid)}"
        entity.evidence_path = rel_evidence_dir

        has_pos_bbox = (
            entity.position_label_bbox is not None
            and parse_bbox_to_pixels(entity.position_label_bbox, frame_w, frame_h) is not None
        )
        has_prod_bbox = (
            entity.product_label_bbox is not None
            and parse_bbox_to_pixels(entity.product_label_bbox, frame_w, frame_h) is not None
        )
        localized = has_pos_bbox or has_prod_bbox
        entity.evidence_localization = EVIDENCE_LOCALIZED if localized else EVIDENCE_UNLOCALIZED

        evidence: Dict[str, Any] = {"overview": []}
        image_count = 0
        path_prefix = rel_evidence_dir

        # 1) Overview frames
        overview_list = _select_overview_frames(frames, k_overview)
        for idx, (frame_idx, frame) in enumerate(overview_list):
            if image_count >= max_images:
                break
            name = f"overview_{idx:02d}.jpg"
            rel_path = f"{path_prefix}/{name}"
            path = entity_dir / name
            if cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality]):
                evidence["overview"].append(rel_path)
                image_count += 1

        if localized:
            # 2) Position label crops
            if has_pos_bbox and entity.position_label_bbox:
                candidates = _select_best_crop_candidates(
                    frames, entity.position_label_bbox, k_pos
                )
                for i, (_, crop) in enumerate(candidates):
                    if image_count >= max_images:
                        break
                    name = f"position_label_{i:02d}.jpg"
                    rel_path = f"{path_prefix}/{name}"
                    path = entity_dir / name
                    if cv2.imwrite(str(path), crop, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality]):
                        if i == 0:
                            evidence["position_label_best"] = rel_path
                        if "position_label_candidates" not in evidence:
                            evidence["position_label_candidates"] = []
                        evidence["position_label_candidates"].append(rel_path)
                        image_count += 1
                if "position_label_best" not in evidence and evidence.get("position_label_candidates"):
                    evidence["position_label_best"] = evidence["position_label_candidates"][0]

            # 3) Product label crops
            if has_prod_bbox and entity.product_label_bbox:
                candidates = _select_best_crop_candidates(
                    frames, entity.product_label_bbox, k_prod
                )
                for i, (_, crop) in enumerate(candidates):
                    if image_count >= max_images:
                        break
                    name = f"product_label_{i:02d}.jpg"
                    rel_path = f"{path_prefix}/{name}"
                    path = entity_dir / name
                    if cv2.imwrite(str(path), crop, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality]):
                        if i == 0:
                            evidence["product_label_best"] = rel_path
                        if "product_label_candidates" not in evidence:
                            evidence["product_label_candidates"] = []
                        evidence["product_label_candidates"].append(rel_path)
                        image_count += 1
                if "product_label_best" not in evidence and evidence.get("product_label_candidates"):
                    evidence["product_label_best"] = evidence["product_label_candidates"][0]
        else:
            # UNLOCALIZED: label fields absent in index
            pass

        index_entities.append({
            "entity_uid": entity.entity_uid,
            "pallet_id": entity.pallet_id,
            "entity_type": entity.entity_type,
            "count_status": entity.count_status,
            "evidence_localization": entity.evidence_localization,
            "evidence": evidence,
        })

    index = {
        "job_id": job_id,
        "mode": "hybrid_v2.1",
        "paths_relative_to": "run_dir",
        "entities": index_entities,
    }
    index_path = run_dir / "evidence_index.json"
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
    logger.info("Evidence pack written: %s (%d entities)", index_path, len(entities))
    return index
