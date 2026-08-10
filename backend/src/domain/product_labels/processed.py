"""Typed product-label outcomes for CODE_SCAN (domain contract — no I/O)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ProductLabelOutcomeStatus(str, Enum):
    """Validation / registry resolution status for one physical product label."""

    VALID = "VALID"
    NOT_OUR_FORMAT = "NOT_OUR_FORMAT"
    CHECKSUM_FAILED = "CHECKSUM_FAILED"
    MALFORMED = "MALFORMED"
    UNKNOWN_VERSION = "UNKNOWN_VERSION"
    UNKNOWN_LABEL = "UNKNOWN_LABEL"
    CLIENT_MISMATCH = "CLIENT_MISMATCH"
    PAYLOAD_MISMATCH = "PAYLOAD_MISMATCH"
    QUANTITY_INVALID = "QUANTITY_INVALID"
    LABEL_ID_INVALID = "LABEL_ID_INVALID"
    DUPLICATE = "DUPLICATE"
    CONFIG_ERROR = "CONFIG_ERROR"


@dataclass(frozen=True)
class ProcessedProductLabel:
    """One physical product label candidate or counted result (0..N per image)."""

    label_id: str | None
    internal_code: str | None
    quantity: int | None
    format_version: str | None
    checksum: str | None
    validation_status: ProductLabelOutcomeStatus
    selected_detection_index: int | None = None
    duplicate_detection_count: int = 1
    symbology: str | None = None
    raw_payload: str | None = None
    normalized_payload: str | None = None
    detail: str | None = None

    def to_dict(self) -> dict:
        return {
            "label_id": self.label_id,
            "internal_code": self.internal_code,
            "quantity": self.quantity,
            "format_version": self.format_version,
            "checksum": self.checksum,
            "validation_status": self.validation_status.value,
            "selected_detection_index": self.selected_detection_index,
            "duplicate_detection_count": self.duplicate_detection_count,
            "symbology": self.symbology,
            "raw_payload": self.raw_payload,
            "normalized_payload": self.normalized_payload,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ProcessedProductLabel:
        status_raw = data.get("validation_status") or ProductLabelOutcomeStatus.MALFORMED.value
        try:
            status = ProductLabelOutcomeStatus(str(status_raw))
        except ValueError:
            status = ProductLabelOutcomeStatus.MALFORMED
        qty = data.get("quantity")
        return cls(
            label_id=(str(data["label_id"]).strip().upper() if data.get("label_id") else None),
            internal_code=(str(data["internal_code"]).strip() if data.get("internal_code") else None),
            quantity=int(qty) if isinstance(qty, int) or (isinstance(qty, str) and qty.isdigit()) else None,
            format_version=(str(data["format_version"]) if data.get("format_version") else None),
            checksum=(str(data["checksum"]).upper() if data.get("checksum") else None),
            validation_status=status,
            selected_detection_index=(
                int(data["selected_detection_index"])
                if data.get("selected_detection_index") is not None
                else None
            ),
            duplicate_detection_count=int(data.get("duplicate_detection_count") or 1),
            symbology=(str(data["symbology"]) if data.get("symbology") else None),
            raw_payload=(str(data["raw_payload"]) if data.get("raw_payload") else None),
            normalized_payload=(
                str(data["normalized_payload"]) if data.get("normalized_payload") else None
            ),
            detail=(str(data["detail"]) if data.get("detail") else None),
        )


__all__ = [
    "ProcessedProductLabel",
    "ProductLabelOutcomeStatus",
]
