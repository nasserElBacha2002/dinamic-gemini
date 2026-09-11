"""Canonical, loss-aware normalization for position identity codes."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

# ``positions.corrected_position_code`` is VARCHAR(64). Imports previously
# accepted wider values, but Phase 1 must not admit a value that cannot be
# persisted by every existing position path.
CANONICAL_POSITION_CODE_MAX_LENGTH = 64


class PositionCodeNormalizationError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code


@dataclass(frozen=True)
class NormalizedPositionCode:
    raw_code: str
    normalized_code: str


def normalize_position_code(
    raw_code: str,
    *,
    max_length: int = CANONICAL_POSITION_CODE_MAX_LENGTH,
) -> NormalizedPositionCode:
    """Return the canonical comparison identity without truncating input.

    Rules: preserve the raw value, reject control/format characters, normalize
    Unicode to NFC, trim outer whitespace, preserve internal spaces and
    separators, and compare case-insensitively using Unicode upper-case.
    """

    if not isinstance(raw_code, str):
        raise PositionCodeNormalizationError(
            "POSITION_CODE_INVALID_TYPE", "Position code must be text"
        )
    if any(unicodedata.category(ch).startswith("C") for ch in raw_code):
        raise PositionCodeNormalizationError(
            "POSITION_CODE_CONTROL_CHARACTER",
            "Position code contains a control or format character",
        )
    normalized = unicodedata.normalize("NFC", raw_code).strip().upper()
    if not normalized:
        raise PositionCodeNormalizationError(
            "POSITION_CODE_REQUIRED", "Position code must not be empty"
        )
    if len(normalized) > max_length:
        raise PositionCodeNormalizationError(
            "POSITION_CODE_TOO_LONG",
            f"Position code exceeds the canonical maximum of {max_length}",
        )
    return NormalizedPositionCode(raw_code=raw_code, normalized_code=normalized)
