"""Resolve OCR extraction profile once per asset (invalid ≠ absent)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from src.application.services.image_processing.extraction_profile_configuration import (
    ExtractionProfileConfigurationError,
)
from src.application.services.image_processing.field_candidate_set import (
    configuration_from_job_snapshot,
)
from src.domain.client_supplier.extraction_profile import (
    ExtractionProfileConfiguration,
    default_extraction_configuration,
)


class OcrProfileResolveStatus(str, Enum):
    VALID = "VALID"
    ABSENT = "ABSENT"
    INVALID = "INVALID"


@dataclass(frozen=True)
class OcrProfileContext:
    """Single resolved profile configuration for extractor/mapper/ranking/validator/evidence."""

    status: OcrProfileResolveStatus
    configuration: ExtractionProfileConfiguration
    error_code: str | None = None
    error_message: str | None = None

    @property
    def is_invalid(self) -> bool:
        return self.status is OcrProfileResolveStatus.INVALID


def resolve_ocr_profile_context(
    supplier_extraction_profile: dict[str, Any] | None,
) -> OcrProfileContext:
    """Parse the job snapshot once.

    * Missing / non-dict snapshot → ABSENT with safe defaults (allowed).
    * Present but unparseable → INVALID (must fail closed; never treat as ABSENT).
    * Present and valid → VALID with that configuration instance.
    """
    if not isinstance(supplier_extraction_profile, dict):
        return OcrProfileContext(
            status=OcrProfileResolveStatus.ABSENT,
            configuration=default_extraction_configuration(),
        )
    try:
        configuration = configuration_from_job_snapshot(supplier_extraction_profile)
    except ExtractionProfileConfigurationError as exc:
        message = str(getattr(exc, "message", None) or exc)
        return OcrProfileContext(
            status=OcrProfileResolveStatus.INVALID,
            configuration=default_extraction_configuration(),
            error_code="PROFILE_SNAPSHOT_INVALID",
            error_message=message,
        )
    return OcrProfileContext(
        status=OcrProfileResolveStatus.VALID,
        configuration=configuration,
    )


__all__ = [
    "OcrProfileContext",
    "OcrProfileResolveStatus",
    "resolve_ocr_profile_context",
]
