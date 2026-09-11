"""Canonical validation/normalization for manual image-result operator input."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.services.position_recognition import (
    CANONICAL_POSITION_CODE_MAX_LENGTH,
)
from src.application.services.position_recognition import (
    normalize_position_code as normalize_canonical_position_code,
)

SKU_MAX_LENGTH = 128
DESCRIPTION_MAX_LENGTH = 512
POSITION_CODE_MAX_LENGTH = CANONICAL_POSITION_CODE_MAX_LENGTH


@dataclass(frozen=True)
class ManualImageResultInput:
    sku: str
    quantity: int
    description: str | None
    position_code: str | None


def normalize_sku(raw: str) -> str:
    return (raw or "").strip()


def normalize_description(raw: str | None) -> str | None:
    if raw is None:
        return None
    clean = raw.strip()
    return clean or None


def normalize_position_code(raw: str | None) -> str | None:
    if raw is None:
        return None
    clean = raw.strip()
    return clean or None


def validate_manual_image_result_input(
    *,
    sku: str,
    quantity: int,
    description: str | None = None,
    position_code: str | None = None,
) -> ManualImageResultInput:
    normalized_sku = normalize_sku(sku)
    if not normalized_sku:
        raise ValueError("sku is required")
    if len(normalized_sku) > SKU_MAX_LENGTH:
        raise ValueError(f"sku must be at most {SKU_MAX_LENGTH} characters")

    if quantity <= 0:
        raise ValueError("quantity must be greater than zero")

    normalized_description = normalize_description(description)
    if normalized_description is not None and len(normalized_description) > DESCRIPTION_MAX_LENGTH:
        raise ValueError(f"description must be at most {DESCRIPTION_MAX_LENGTH} characters")

    normalized_position_code = normalize_position_code(position_code)
    if normalized_position_code is not None:
        normalize_canonical_position_code(normalized_position_code)

    return ManualImageResultInput(
        sku=normalized_sku,
        quantity=quantity,
        description=normalized_description,
        position_code=normalized_position_code,
    )


def build_manual_product_record_fields(quantity: int) -> dict[str, object]:
    return {
        "qty_source": "manual_review",
        "qty_parse_status": "valid_positive",
        "detected_quantity": quantity,
        "corrected_quantity": quantity,
        "raw_qty": quantity,
    }
