"""Job-scoped label validation context — domain contract (no application imports)."""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.client_supplier.extraction_profile import ExtractionProfileConfiguration
from src.domain.label_profiles.entities import ResolvedLabelProfiles


@dataclass(frozen=True)
class LabelValidationContext:
    """Immutable job-scoped validation inputs (from snapshot, not live active config)."""

    resolved_profiles: ResolvedLabelProfiles | None
    item_extraction_configuration: ExtractionProfileConfiguration | None = None
    position_extraction_configuration: ExtractionProfileConfiguration | None = None
    job_id: str | None = None
    client_id: str | None = None
