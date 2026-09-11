"""Profile-driven recognition completeness (identity / completion / persistence).

Derives required field sets from the effective extraction profile — no hardcoded
supplier prefixes and no quantity-only completeness.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from src.domain.client_supplier.extraction_profile import (
    ExtractionProfileConfiguration,
    MissingQuantityAction,
    QuantityPresence,
)
from src.domain.label_profiles.kinds import LabelKind

_IDENTITY_FIELD_CANDIDATES: frozenset[str] = frozenset(
    {
        "label_id",
        "position_id",
        "sku",
        "internal_code",
    }
)
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

    def to_diagnostics(self) -> dict[str, Any]:
        return {
            "identity_complete": self.identity_complete,
            "completion_complete": self.completion_complete,
            "persistence_complete": self.persistence_complete,
            "missing_identity_fields": list(self.missing_identity_fields),
            "missing_completion_fields": list(self.missing_completion_fields),
            "missing_persistence_fields": list(self.missing_persistence_fields),
            "enrichment_complete": self.completion_complete,
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
    # Minimal profiles: primary identity from kind.
    if kind is LabelKind.POSITION:
        return ("position_id",)
    if config.is_minimal():
        return ("label_id",)
    # Legacy FULL defaults often require internal_code.
    if "internal_code" in required or "sku" in required:
        return tuple(f for f in ("internal_code", "sku") if f in required) or ("internal_code",)
    return ("label_id",)


def _quantity_required_for_completion(config: ExtractionProfileConfiguration) -> bool:
    rules = config.quantity_rules
    if rules.required:
        return True
    if rules.expected_presence is QuantityPresence.ALWAYS:
        return True
    required = {f.strip().lower() for f in config.required_fields if f and str(f).strip()}
    if "quantity" in required:
        return True
    # Identity-only resolve: absence is valid.
    if rules.missing_quantity_action is MissingQuantityAction.RESOLVE_CODE_ONLY:
        return False
    # Optional quantity must not force incomplete just because the profile says
    # PENDING_MANUAL_REVIEW (legacy defaults). Only enrichment / always-required
    # policies keep quantity on the completion checklist.
    if rules.expected_presence is QuantityPresence.OPTIONAL and not rules.required:
        if rules.missing_quantity_action is MissingQuantityAction.EXTERNAL_FALLBACK:
            return True
        if rules.allow_external_fallback:
            return True
        return False
    if rules.missing_quantity_action is MissingQuantityAction.EXTERNAL_FALLBACK:
        return True
    if rules.missing_quantity_action is MissingQuantityAction.PENDING_MANUAL_REVIEW:
        return True
    return bool(rules.allow_external_fallback)


def _completion_required(kind: LabelKind, config: ExtractionProfileConfiguration) -> tuple[str, ...]:
    identity = list(_identity_required(kind, config))
    required = {f.strip().lower() for f in config.required_fields if f and str(f).strip()}
    extras = [
        f
        for f in sorted(required)
        if f not in identity and f != "quantity"
    ]
    fields = identity + extras
    if kind is LabelKind.ITEM and _quantity_required_for_completion(config):
        if "quantity" not in fields:
            fields.append("quantity")
    return tuple(fields)


def _persistence_required(kind: LabelKind, config: ExtractionProfileConfiguration) -> tuple[str, ...]:
    """Productive ProductRecord requires completion fields (incl. quantity when required)."""
    return _completion_required(kind, config)


def evaluate_recognition_completeness(
    *,
    kind: LabelKind,
    configuration: ExtractionProfileConfiguration | None,
    fields: Mapping[str, Any] | None,
    field_sources: Mapping[str, Any] | None = None,
) -> RecognitionCompleteness:
    """Evaluate identity / completion / persistence from profile + semantic fields.

    ``field_sources`` is accepted for contract parity / future policy and does not
    change presence checks.
    """
    del field_sources  # reserved for provenance-aware policies
    if configuration is None:
        # Fail-closed without a profile: treat as incomplete.
        return RecognitionCompleteness(
            identity_complete=False,
            completion_complete=False,
            persistence_complete=False,
            missing_identity_fields=("profile",),
            missing_completion_fields=("profile",),
            missing_persistence_fields=("profile",),
        )

    normalized = _normalize_fields(fields)
    identity_req = _identity_required(kind, configuration)
    completion_req = _completion_required(kind, configuration)
    persistence_req = _persistence_required(kind, configuration)

    missing_identity = tuple(f for f in identity_req if not _field_present(normalized, f))
    # label_id-only identity: allow sku/internal_code as alternate when label_id missing
    # only when required set includes them — already encoded in identity_req.

    # For ITEM identity, either label_id OR (sku/internal_code) may satisfy when
    # required_fields listed alternatives — handled by listing both in required.
    if (
        kind is LabelKind.ITEM
        and missing_identity
        and "label_id" in identity_req
        and _field_present(normalized, "label_id")
    ):
        missing_identity = tuple(f for f in missing_identity if f != "label_id")

    missing_completion = tuple(f for f in completion_req if not _field_present(normalized, f))
    missing_persistence = tuple(f for f in persistence_req if not _field_present(normalized, f))

    return RecognitionCompleteness(
        identity_complete=not missing_identity,
        completion_complete=not missing_completion,
        persistence_complete=not missing_persistence,
        missing_identity_fields=missing_identity,
        missing_completion_fields=missing_completion,
        missing_persistence_fields=missing_persistence,
    )


class RecognitionCompletenessEvaluator:
    """Cohesive evaluator API shared by CODE_SCAN / Vision / TXT / CSV / persister."""

    def evaluate(
        self,
        *,
        kind: LabelKind,
        configuration: ExtractionProfileConfiguration | None,
        fields: Mapping[str, Any] | None,
        field_sources: Mapping[str, Any] | None = None,
    ) -> RecognitionCompleteness:
        return evaluate_recognition_completeness(
            kind=kind,
            configuration=configuration,
            fields=fields,
            field_sources=field_sources,
        )
