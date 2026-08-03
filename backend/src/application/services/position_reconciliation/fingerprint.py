"""Deterministic semantic fingerprint for Phase 4 inputs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from src.domain.position_reconciliation.entities import (
    RECONCILIATION_VERSION,
    OrderedImageFrame,
)


@dataclass(frozen=True)
class PositionReconciliationInputSnapshot:
    frames: Sequence[OrderedImageFrame]
    sequence_version: int | None
    reconciliation_version: str = RECONCILIATION_VERSION


def _value(value: str | Enum) -> str:
    return str(value.value if isinstance(value, Enum) else value)


def compute_input_fingerprint(snapshot: PositionReconciliationInputSnapshot) -> str:
    frames = sorted(
        snapshot.frames,
        key=lambda frame: (
            frame.sequence_number is None,
            frame.sequence_number or 0,
            frame.client_image_id or "",
            frame.source_asset_id,
        ),
    )
    payload = {
        "frames": [
            {
                "client_image_id": frame.client_image_id,
                "detections": sorted(
                    (
                        {
                            "detector_version": detection.detector_version,
                            "id": detection.id,
                            "position_label_id": detection.position_label_id,
                            "signature_status": _value(detection.signature_status),
                            "status": _value(detection.detection_status),
                        }
                        for detection in frame.position_detections
                    ),
                    key=lambda detection: (
                        detection["id"],
                        detection["status"],
                        detection["signature_status"],
                        detection["position_label_id"] or "",
                        detection["detector_version"] or "",
                    ),
                ),
                "ordered_capture_session_id": frame.ordered_capture_session_id,
                "result_ids": sorted(item.result_id for item in frame.item_results),
                "sequence_number": frame.sequence_number,
                "source_asset_id": frame.source_asset_id,
            }
            for frame in frames
        ],
        "reconciliation_version": snapshot.reconciliation_version,
        "sequence_version": snapshot.sequence_version,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_fingerprint_from_frames(
    frames: Sequence[OrderedImageFrame],
    *,
    sequence_version: int | None,
) -> str:
    return compute_input_fingerprint(
        PositionReconciliationInputSnapshot(
            frames=frames,
            sequence_version=sequence_version,
        )
    )
