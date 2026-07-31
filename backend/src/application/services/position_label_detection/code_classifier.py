"""Classify decoded codes as POSITION / ITEM / UNKNOWN (Phase 3)."""

from __future__ import annotations

import json
from typing import Any

from src.domain.aisle_location.label_entities import POSITIONING_LABEL_TYPE
from src.domain.position_label_detection.entities import DetectedCode, ImageCodeKind


def try_parse_json_object(raw: str, *, max_bytes: int) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text or len(text.encode("utf-8")) > max_bytes:
        return None
    if not (text.startswith("{") and text.endswith("}")):
        return None
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


class CodeClassifier:
    """Route each decoded symbol without consulting repositories."""

    def __init__(self, *, max_payload_bytes: int) -> None:
        self._max_payload_bytes = max(256, int(max_payload_bytes))

    def classify(self, code: DetectedCode) -> ImageCodeKind:
        payload = try_parse_json_object(code.raw_value, max_bytes=self._max_payload_bytes)
        if payload is None:
            return ImageCodeKind.ITEM if (code.raw_value or "").strip() else ImageCodeKind.UNKNOWN
        type_value = str(payload.get("type") or "").strip()
        if type_value == POSITIONING_LABEL_TYPE:
            return ImageCodeKind.POSITION
        # JSON that is not a positioning label is not an item pipe-label either.
        return ImageCodeKind.UNKNOWN

    def peek_position_payload(self, code: DetectedCode) -> dict[str, Any] | None:
        payload = try_parse_json_object(code.raw_value, max_bytes=self._max_payload_bytes)
        if payload is None:
            return None
        if str(payload.get("type") or "").strip() != POSITIONING_LABEL_TYPE:
            return None
        return payload
