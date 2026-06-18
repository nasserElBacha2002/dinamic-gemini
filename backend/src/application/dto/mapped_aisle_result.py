"""DTO for mapping a pipeline hybrid report to v3 domain rows (one pass, aligned lists)."""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.evidence.entities import Evidence
from src.domain.labels.entities import RawLabel
from src.domain.positions.entities import Position
from src.domain.products.entities import ProductRecord
from src.domain.result_evidence.entities import ResultEvidenceRecord


@dataclass
class MappedAisleResult:
    """Result of mapping a hybrid report to v3 domain for one aisle. v3.2.3: includes raw_labels."""

    positions: list[Position]
    product_records: list[ProductRecord]
    evidences: list[Evidence]
    raw_labels: list[RawLabel]
    result_evidence_records: list[ResultEvidenceRecord]
