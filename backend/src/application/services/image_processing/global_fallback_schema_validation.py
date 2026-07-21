"""Strict GlobalEntityResponseV21 validation for GLOBAL_BATCH."""

from __future__ import annotations

from typing import Any

from src.application.services.image_processing.external_fallback_mode import (
    GLOBAL_FALLBACK_SCHEMA_VERSION,
)
from src.exceptions.global_analysis_exceptions import GlobalAnalysisValidationError
from src.validation.global_analysis_schema import validate_global_analysis_structure_v21

_ALLOWED_SCHEMA_VERSIONS = frozenset({"v2.1", "2.1", "v21"})


class GlobalFallbackSchemaError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def normalize_schema_version(raw: str | None) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    lower = text.lower().replace("_", ".")
    if lower in ("v2.1", "2.1", "v21", "global_v21"):
        return GLOBAL_FALLBACK_SCHEMA_VERSION
    return text


def validate_global_fallback_report(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate GLOBAL_BATCH provider report; return entities.

    Accepts only v2.1 family schemas. Rejects external_fallback_* and unknown versions.
    Prefers full ``validate_global_analysis_structure_v21``; if the report is a
    post-normalized operational shape (internal_code/quantity/source_image_id) without
    pallet entity_type fields, applies a strict operational subset check instead.
    """
    if not isinstance(report, dict):
        raise GlobalFallbackSchemaError(
            "EXTERNAL_SCHEMA_CONTRACT_MISMATCH", "report must be an object"
        )

    schema_raw = report.get("schema_version")
    if schema_raw is not None:
        raw_s = str(schema_raw).strip()
        if "external_fallback" in raw_s.lower():
            raise GlobalFallbackSchemaError(
                "EXTERNAL_SCHEMA_CONTRACT_MISMATCH",
                f"GLOBAL_BATCH rejects single-label schema {raw_s!r}",
            )
        normalized = normalize_schema_version(raw_s)
        if normalized not in _ALLOWED_SCHEMA_VERSIONS and normalized != GLOBAL_FALLBACK_SCHEMA_VERSION:
            # Allow missing/implicit when pipeline omits schema_version but still V21 body.
            if raw_s:
                raise GlobalFallbackSchemaError(
                    "EXTERNAL_SCHEMA_CONTRACT_MISMATCH",
                    f"GLOBAL_BATCH requires schema v2.1; got {raw_s!r}",
                )

    if "entities" not in report or not isinstance(report.get("entities"), list):
        raise GlobalFallbackSchemaError(
            "EXTERNAL_SCHEMA_CONTRACT_MISMATCH",
            "GlobalEntityResponseV21 requires entities[]",
        )

    entities = [e for e in report["entities"] if isinstance(e, dict)]
    # Normalize total for downstream checks.
    if "total_entities_detected" not in report:
        report = {**report, "total_entities_detected": len(entities)}
    elif report["total_entities_detected"] != len(report["entities"]):
        raise GlobalFallbackSchemaError(
            "EXTERNAL_SCHEMA_CONTRACT_MISMATCH",
            "total_entities_detected inconsistent with entities length",
        )

    # Full V21 when entities look like pallet contract.
    looks_v21 = any("entity_type" in e or "model_entity_id" in e for e in entities)
    if looks_v21 or not entities:
        try:
            validate_global_analysis_structure_v21(report)
        except GlobalAnalysisValidationError as exc:
            raise GlobalFallbackSchemaError(
                "EXTERNAL_SCHEMA_CONTRACT_MISMATCH", str(exc)
            ) from exc
        return entities

    # Operational subset (normalized hybrid → inventory fields).
    for i, e in enumerate(entities):
        code = e.get("internal_code")
        qty = e.get("quantity", e.get("product_label_quantity"))
        if code is not None and not isinstance(code, str):
            raise GlobalFallbackSchemaError(
                "EXTERNAL_SCHEMA_CONTRACT_MISMATCH",
                f"entities[{i}].internal_code must be string or null",
            )
        if qty is not None:
            if isinstance(qty, bool) or not isinstance(qty, (int, float)):
                raise GlobalFallbackSchemaError(
                    "EXTERNAL_SCHEMA_CONTRACT_MISMATCH",
                    f"entities[{i}].quantity must be number or null",
                )
            if float(qty) < 0:
                raise GlobalFallbackSchemaError(
                    "EXTERNAL_SCHEMA_CONTRACT_MISMATCH",
                    f"entities[{i}].quantity must be >= 0",
                )
    return entities
