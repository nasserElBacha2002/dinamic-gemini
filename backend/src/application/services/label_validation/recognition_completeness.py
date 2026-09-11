"""Profile-driven recognition completeness (identity / completion / persistence).

Derives required field sets from the effective extraction profile — no hardcoded
supplier prefixes and no quantity-only completeness.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from src.application.services.label_validation.quantity_completeness import (
    QuantityCompletenessDecision,
    decide_quantity_completeness_from_config,
)
from src.domain.client_supplier.extraction_profile import ExtractionProfileConfiguration
from src.domain.label_profiles.kinds import LabelKind

_POSITION_IDENTITY_FIELDS: frozenset[str] = frozenset({"position_id"})
_ITEM_IDENTITY_FIELDS: frozenset[str] = frozenset({"label_id", "sku", "internal_code"})


@dataclass(frozen=True)
class RecognitionCompleteness:
    identity_complete: bool
    completion_complete: bool
    persistence_complete: bool
    missing_identity_fields: tuple[str, ...]
    missing_completion_fields: tuple[str, ...]
    missing_persistence_fields: tuple[str, ...]
    fallback_eligible: bool = False

    def to_diagnostics(self) -> dict[str, Any]:
        return {
            "identity_complete": self.identity_complete,
            "completion_complete": self.completion_complete,
            "persistence_complete": self.persistence_complete,
            "missing_identity_fields": list(self.missing_identity_fields),
            "missing_completion_fields": list(self.missing_completion_fields),
            "missing_persistence_fields": list(self.missing_persistence_fields),
            "enrichment_complete": self.completion_complete,
            "fallback_eligible": self.fallback_eligible,
        }


def _normalize_fields(fields: Mapping[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not fields:
        return out
    for key, value in fields.items():
        name = str(key).strip().lower()
        if not name:
            continue
        if value is None:
            out[name] = None
            continue
        if isinstance(value, str):
            text = value.strip()
            out[name] = text if text else None
            continue
        out[name] = value
    # Alias internal_code ↔ sku for presence checks when only one is set.
    if out.get("sku") and not out.get("internal_code"):
        out["internal_code"] = out["sku"]
    if out.get("internal_code") and not out.get("sku"):
        out["sku"] = out["internal_code"]
    return out


def _field_present(normalized: Mapping[str, Any], name: str) -> bool:
    value = normalized.get(name)
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


def _identity_required(kind: LabelKind, config: ExtractionProfileConfiguration) -> tuple[str, ...]:
    required = {f.strip().lower() for f in config.required_fields if f and str(f).strip()}
    allowed = _POSITION_IDENTITY_FIELDS if kind is LabelKind.POSITION else _ITEM_IDENTITY_FIELDS
    identity = tuple(sorted(f for f in required if f in allowed))
    if identity:
        return identity
    if kind is LabelKind.POSITION:
        return ("position_id",)
    if config.is_minimal():
        return ("label_id",)
    if "internal_code" in required or "sku" in required:
        return tuple(f for f in ("internal_code", "sku") if f in required) or ("internal_code",)
    return ("label_id",)


def _completion_required(
    kind: LabelKind,
    config: ExtractionProfileConfiguration,
    decision: QuantityCompletenessDecision,
) -> tuple[str, ...]:
    identity = list(_identity_required(kind, config))
    required = {f.strip().lower() for f in config.required_fields if f and str(f).strip()}
    extras = [f for f in sorted(required) if f not in identity and f != "quantity"]
    fields = identity + extras
    if kind is LabelKind.ITEM and decision.quantity_required_for_completion:
        if "quantity" not in fields:
            fields.append("quantity")
    return tuple(fields)


def evaluate_recognition_completeness(
    *,
    kind: LabelKind,
    configuration: ExtractionProfileConfiguration | None,
    fields: Mapping[str, Any] | None,
) -> RecognitionCompleteness:
    """Evaluate identity / completion / persistence from profile + semantic fields."""
    if configuration is None:
        return RecognitionCompleteness(
            identity_complete=False,
            completion_complete=False,
            persistence_complete=False,
            missing_identity_fields=("profile",),
            missing_completion_fields=("profile",),
            missing_persistence_fields=("profile",),
            fallback_eligible=False,
        )

    decision = decide_quantity_completeness_from_config(kind=kind, configuration=configuration)
    normalized = _normalize_fields(fields)
    identity_req = _identity_required(kind, configuration)
    completion_req = _completion_required(kind, configuration, decision)
    persistence_req = completion_req

    missing_identity = tuple(f for f in identity_req if not _field_present(normalized, f))
    if (
        kind is LabelKind.ITEM
        and missing_identity
        and "label_id" in identity_req
        and _field_present(normalized, "label_id")
    ):
        missing_identity = tuple(f for f in missing_identity if f != "label_id")

    missing_completion = tuple(f for f in completion_req if not _field_present(normalized, f))
    missing_persistence = tuple(f for f in persistence_req if not _field_present(normalized, f))
    identity_complete = not missing_identity
    quantity_present = _field_present(normalized, "quantity")

    return RecognitionCompleteness(
        identity_complete=identity_complete,
        completion_complete=not missing_completion,
        persistence_complete=not missing_persistence,
        missing_identity_fields=missing_identity,
        missing_completion_fields=missing_completion,
        missing_persistence_fields=missing_persistence,
        fallback_eligible=decision.fallback_eligible(
            identity_complete=identity_complete,
            quantity_present=quantity_present,
        ),
    )
