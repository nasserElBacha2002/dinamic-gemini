"""Deterministic Phase 4 input fingerprint."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable

from src.domain.position_reconciliation.entities import RECONCILIATION_VERSION


def compute_input_fingerprint(
    *,
    ordered_capture_session_id: str | None,
    sequence_version: int | None,
    position_detection_version: str,
    result_ids: Iterable[str],
    reconciliation_version: str = RECONCILIATION_VERSION,
) -> str:
    result_set_version = hashlib.sha256(
        "\n".join(sorted(set(result_ids))).encode("utf-8")
    ).hexdigest()
    payload = {
        "ordered_capture_session_id": ordered_capture_session_id,
        "position_detection_version": position_detection_version,
        "reconciliation_version": reconciliation_version,
        "result_set_version": result_set_version,
        "sequence_version": sequence_version,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
