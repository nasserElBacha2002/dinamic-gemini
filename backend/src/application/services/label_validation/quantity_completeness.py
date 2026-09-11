"""Single quantity completeness decision table shared with mobile.

The algorithm is documented and vectorized in
``contracts/offline-recognition/v1/quantity-completeness-matrix.json``.
Do not re-implement this policy in CODE_SCAN / Vision / TXT callers.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.domain.client_supplier.extraction_profile import (
    ExtractionProfileConfiguration,
    MissingQuantityAction,
    QuantityPresence,
)
from src.domain.label_profiles.kinds import LabelKind

_MATRIX_RELATIVE = Path("contracts/offline-recognition/v1/quantity-completeness-matrix.json")


def quantity_completeness_matrix_path() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / _MATRIX_RELATIVE
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"quantity completeness matrix not found: {_MATRIX_RELATIVE}")


def load_quantity_completeness_matrix() -> dict[str, Any]:
    path = quantity_completeness_matrix_path()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"quantity completeness matrix must be an object: {path}")
    return payload


def _enum_value(value: object | None) -> str:
    if value is None:
        return ""
    raw = getattr(value, "value", value)
    return str(raw or "").strip().upper()


@dataclass(frozen=True)
class QuantityCompletenessDecision:
    quantity_required_for_completion: bool
    fallback_policy: bool

    def fallback_eligible(
        self,
        *,
        identity_complete: bool,
        quantity_present: bool,
    ) -> bool:
        return (
            identity_complete
            and not quantity_present
            and self.quantity_required_for_completion
            and self.fallback_policy
        )


def decide_quantity_completeness(
    *,
    kind: LabelKind | str,
    required: bool,
    expected_presence: QuantityPresence | str | None,
    missing_quantity_action: MissingQuantityAction | str | None,
    allow_external_fallback: bool,
    required_fields: Sequence[str] | None = None,
) -> QuantityCompletenessDecision:
    """Evaluate the shared quantity decision table.

    ``fallback_policy`` is independent of whether quantity is currently present;
    ``fallback_eligible`` additionally requires missing quantity + complete identity.
    """
    kind_value = kind.value if isinstance(kind, LabelKind) else str(kind).strip().upper()
    if kind_value == LabelKind.POSITION.value:
        return QuantityCompletenessDecision(
            quantity_required_for_completion=False,
            fallback_policy=False,
        )

    presence = _enum_value(expected_presence)
    action = _enum_value(missing_quantity_action) or MissingQuantityAction.PENDING_MANUAL_REVIEW.value
    required_set = {
        str(field).strip().lower()
        for field in (required_fields or ())
        if field and str(field).strip()
    }
    explicitly_required = bool(required) or presence == QuantityPresence.ALWAYS.value or "quantity" in required_set
    fallback_policy = bool(allow_external_fallback) or action == MissingQuantityAction.EXTERNAL_FALLBACK.value

    if action == MissingQuantityAction.RESOLVE_CODE_ONLY.value and not explicitly_required:
        return QuantityCompletenessDecision(
            quantity_required_for_completion=False,
            fallback_policy=False,
        )
    if explicitly_required:
        return QuantityCompletenessDecision(
            quantity_required_for_completion=True,
            fallback_policy=fallback_policy,
        )
    if presence == QuantityPresence.OPTIONAL.value and not required:
        return QuantityCompletenessDecision(
            quantity_required_for_completion=fallback_policy,
            fallback_policy=fallback_policy,
        )
    if action == MissingQuantityAction.EXTERNAL_FALLBACK.value:
        return QuantityCompletenessDecision(
            quantity_required_for_completion=True,
            fallback_policy=True,
        )
    if action in {
        MissingQuantityAction.PENDING_MANUAL_REVIEW.value,
        MissingQuantityAction.UNRECOGNIZED.value,
    }:
        return QuantityCompletenessDecision(
            quantity_required_for_completion=True,
            fallback_policy=fallback_policy,
        )
    return QuantityCompletenessDecision(
        quantity_required_for_completion=bool(allow_external_fallback),
        fallback_policy=fallback_policy,
    )


def decide_quantity_completeness_from_config(
    *,
    kind: LabelKind,
    configuration: ExtractionProfileConfiguration,
) -> QuantityCompletenessDecision:
    rules = configuration.quantity_rules
    return decide_quantity_completeness(
        kind=kind,
        required=bool(rules.required),
        expected_presence=rules.expected_presence,
        missing_quantity_action=rules.missing_quantity_action,
        allow_external_fallback=bool(rules.allow_external_fallback),
        required_fields=configuration.required_fields,
    )


def matrix_row_to_decision(row: Mapping[str, Any]) -> QuantityCompletenessDecision:
    return decide_quantity_completeness(
        kind=str(row["kind"]),
        required=bool(row["required"]),
        expected_presence=str(row["expected_presence"]),
        missing_quantity_action=str(row["missing_quantity_action"]),
        allow_external_fallback=bool(row["allow_external_fallback"]),
        required_fields=list(row.get("required_fields") or []),
    )
