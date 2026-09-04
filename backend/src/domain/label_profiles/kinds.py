"""Strong domain types for label recognition profile selection (Phase 1)."""

from __future__ import annotations

from enum import Enum


class LabelKind(str, Enum):
    """Physical label category handled independently in recognition profiles."""

    ITEM = "ITEM"
    POSITION = "POSITION"


class LabelProfileSource(str, Enum):
    """Where effective recognition rules originate."""

    DINAMIC = "DINAMIC"
    SUPPLIER = "SUPPLIER"


def effective_label_kind(stored: LabelKind | None) -> LabelKind:
    """Legacy NULL rows and unset writes default to ITEM (Phase 1)."""
    return stored if stored is not None else LabelKind.ITEM


def parse_label_kind(value: str | LabelKind) -> LabelKind:
    if isinstance(value, LabelKind):
        return value
    raw = (value or "").strip().upper()
    if not raw:
        raise ValueError("label_kind must not be empty")
    try:
        return LabelKind(raw)
    except ValueError as exc:
        allowed = ", ".join(k.value for k in LabelKind)
        raise ValueError(f"Invalid label_kind {value!r}; expected one of: {allowed}") from exc


def parse_label_profile_source(value: str | LabelProfileSource) -> LabelProfileSource:
    if isinstance(value, LabelProfileSource):
        return value
    raw = (value or "").strip().upper()
    if not raw:
        raise ValueError("label_profile_source must not be empty")
    try:
        return LabelProfileSource(raw)
    except ValueError as exc:
        allowed = ", ".join(s.value for s in LabelProfileSource)
        raise ValueError(
            f"Invalid label_profile_source {value!r}; expected one of: {allowed}"
        ) from exc


def optional_label_profile_source_override(
    value: str | LabelProfileSource | None,
) -> LabelProfileSource | None:
    """Parse nullable aisle override; empty string is treated as NULL (inherit)."""
    if value is None:
        return None
    if isinstance(value, LabelProfileSource):
        return value
    raw = str(value).strip()
    if not raw:
        return None
    return parse_label_profile_source(raw)
