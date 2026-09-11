"""Field-level merge: deterministic CODE_SCAN fields + Vision/OCR enrichment only for gaps."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

_DETERMINISTIC_SOURCES = frozenset({"CODE_SCAN", "TXT", "CSV", "PARSER", "GS1"})
_ENRICHMENT_SOURCES = frozenset({"VISION", "OCR", "EXTERNAL", "EXTERNAL_PROVIDER"})


@dataclass(frozen=True)
class FieldMergeResult:
    fields: dict[str, Any]
    field_sources: dict[str, str]
    overwritten_blocked: tuple[str, ...]
    filled_from_enrichment: tuple[str, ...]


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


def merge_recognition_fields(
    *,
    confirmed: Mapping[str, Any],
    confirmed_sources: Mapping[str, str] | None,
    enrichment: Mapping[str, Any],
    enrichment_source: str = "VISION",
    missing_fields: tuple[str, ...] | list[str] | None = None,
    preserve_confirmed: bool = True,
) -> FieldMergeResult:
    """Merge enrichment into confirmed fields without replacing deterministic identity.

    - Confirmed deterministic values always win when ``preserve_confirmed``.
    - Enrichment may only fill keys listed in ``missing_fields`` (or any absent key
      when ``missing_fields`` is None).
    - Conflicting enrichment identity when confirmed identity exists is ignored
      (recorded in ``overwritten_blocked``).
    """
    out: dict[str, Any] = {
        str(k): v for k, v in confirmed.items() if _present(v) or v == 0
    }
    sources: dict[str, str] = {
        str(k): str(v)
        for k, v in (confirmed_sources or {}).items()
        if str(k) in out
    }
    for key in out:
        sources.setdefault(key, "CODE_SCAN")

    allowed = (
        {str(f).strip().lower() for f in missing_fields}
        if missing_fields is not None
        else None
    )
    blocked: list[str] = []
    filled: list[str] = []
    enrich_src = (enrichment_source or "VISION").strip().upper() or "VISION"

    for raw_key, raw_value in enrichment.items():
        key = str(raw_key).strip().lower()
        if not key or (not _present(raw_value) and raw_value != 0):
            continue
        if allowed is not None and key not in allowed:
            if _present(out.get(key)) and preserve_confirmed:
                blocked.append(key)
            continue
        existing = out.get(key)
        existing_source = (sources.get(key) or "").strip().upper()
        if _present(existing) and preserve_confirmed:
            if existing_source in _DETERMINISTIC_SOURCES or existing_source == "":
                if existing != raw_value:
                    blocked.append(key)
                continue
        out[key] = raw_value
        sources[key] = enrich_src
        filled.append(key)

    return FieldMergeResult(
        fields=out,
        field_sources=sources,
        overwritten_blocked=tuple(dict.fromkeys(blocked)),
        filled_from_enrichment=tuple(dict.fromkeys(filled)),
    )
