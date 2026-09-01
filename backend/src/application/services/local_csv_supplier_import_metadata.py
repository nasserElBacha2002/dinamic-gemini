"""Typed parser for mobile CSV ``notes.supplier_import`` handoff metadata."""

from __future__ import annotations

import json
from dataclasses import dataclass

from src.domain.label_profiles.kinds import LabelKind, parse_label_kind

_MAX_RAW_PAYLOAD = 512
_MAX_ID_LENGTH = 128


@dataclass(frozen=True)
class SupplierImportMetadata:
    client_supplier_id: str
    label_kind: LabelKind
    profile_id: str
    profile_version: int
    raw_payload: str


@dataclass(frozen=True)
class SupplierImportNotesParseResult:
    """Outcome of parsing optional supplier handoff metadata from CSV notes."""

    metadata: SupplierImportMetadata | None
    errors: tuple[str, ...]
    supplier_import_present: bool


def parse_supplier_import_notes(notes: str) -> SupplierImportNotesParseResult:
    """Parse ``notes`` JSON for ``supplier_import`` without treating plain text as JSON."""
    text = (notes or "").strip()
    if not text:
        return SupplierImportNotesParseResult(None, (), False)
    if not text.startswith("{"):
        return SupplierImportNotesParseResult(None, (), False)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return SupplierImportNotesParseResult(None, (), False)
    if not isinstance(payload, dict):
        return SupplierImportNotesParseResult(None, (), False)
    block = payload.get("supplier_import")
    if block is None:
        return SupplierImportNotesParseResult(None, (), False)
    if not isinstance(block, dict):
        return SupplierImportNotesParseResult(
            None,
            ("supplier_import:invalid_shape",),
            True,
        )
    errors: list[str] = []
    client_supplier_id = _require_str(
        block.get("client_supplier_id"), "client_supplier_id", errors, max_len=_MAX_ID_LENGTH
    )
    profile_id = _require_str(
        block.get("profile_id"), "profile_id", errors, max_len=_MAX_ID_LENGTH
    )
    profile_version = _require_int(block.get("profile_version"), "profile_version", errors)
    raw_payload = _require_str(
        block.get("raw_payload"), "raw_payload", errors, max_len=_MAX_RAW_PAYLOAD
    )
    label_kind: LabelKind | None = None
    kind_raw = block.get("label_kind")
    if kind_raw is None or not str(kind_raw).strip():
        errors.append("supplier_import:missing_label_kind")
    else:
        try:
            label_kind = parse_label_kind(str(kind_raw))
        except ValueError:
            errors.append("supplier_import:invalid_label_kind")
    if errors or label_kind is None:
        return SupplierImportNotesParseResult(None, tuple(errors), True)
    assert client_supplier_id and profile_id and raw_payload is not None and profile_version is not None
    return SupplierImportNotesParseResult(
        SupplierImportMetadata(
            client_supplier_id=client_supplier_id,
            label_kind=label_kind,
            profile_id=profile_id,
            profile_version=int(profile_version),
            raw_payload=raw_payload,
        ),
        (),
        True,
    )


def _require_str(
    value: object,
    field: str,
    errors: list[str],
    *,
    max_len: int,
) -> str | None:
    if value is None or not str(value).strip():
        errors.append(f"supplier_import:missing_{field}")
        return None
    text = str(value).strip()
    if len(text) > max_len:
        errors.append(f"supplier_import:{field}_too_long")
        return None
    return text


def _require_int(value: object, field: str, errors: list[str]) -> int | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        errors.append(f"supplier_import:missing_{field}")
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        errors.append(f"supplier_import:invalid_{field}")
        return None
    if parsed < 1:
        errors.append(f"supplier_import:invalid_{field}")
        return None
    return parsed
