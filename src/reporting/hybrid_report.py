"""
Stage 4 — Build deterministic hybrid report dict.

Includes low-confidence flagging (no behavior change; flag only).
Stage 6: metrics (global_calls, fallback_attempts, fallback_success, total_calls) and confidence_threshold.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from src.domain.pallet import Pallet

LOW_CONFIDENCE_FLAG_THRESHOLD = 0.50


def build_hybrid_report(
    video_path: str,
    pallets: List[Pallet],
    frames_selected: int,
    prompt_version: str = "global_min_v1",
    metrics: Optional[Dict[str, int]] = None,
    confidence_threshold: Optional[float] = None,
) -> Dict[str, Any]:
    """Build the authoritative hybrid report dict.

    Args:
        video_path: Path to the source video.
        pallets: List of pallets with processing_mode/final_quantity/source set.
        frames_selected: Number of representative frames sent to Gemini.
        prompt_version: Prompt version identifier.
        metrics: Optional dict with global_calls, fallback_attempts, fallback_success, total_calls (Stage 6).
        confidence_threshold: Optional threshold used for fallback trigger (Stage 6).

    Returns:
        Report dict with video, mode, prompt_version, frames_selected,
        total_pallets_detected, pallets, flags; optionally metrics and confidence_threshold.
    """
    path_obj = Path(video_path)
    low_confidence = [
        p.pallet_id for p in pallets
        if p.confidence < LOW_CONFIDENCE_FLAG_THRESHOLD
    ]
    flags: Dict[str, Any] = {"low_confidence_pallets": low_confidence}
    if not pallets:
        flags["no_pallets_detected"] = True

    report: Dict[str, Any] = {
        "video": {"path": video_path, "name": path_obj.name},
        "mode": "hybrid",
        "prompt_version": prompt_version,
        "frames_selected": frames_selected,
        "total_pallets_detected": len(pallets),
        "pallets": [
            {
                "pallet_id": p.pallet_id,
                "has_label": p.has_label,
                "internal_code": p.internal_code,
                "quantity": p.quantity,
                "final_quantity": p.final_quantity,
                "source": p.source,
                "confidence": p.confidence,
                "fallback_used": p.fallback_used,
            }
            for p in pallets
        ],
        "flags": flags,
    }
    if metrics is not None:
        report["metrics"] = metrics
    if confidence_threshold is not None:
        report["confidence_threshold"] = confidence_threshold
    return report
