"""Pipeline adapters and mappers for v3 integration — Épica 6."""

from src.application.dto.mapped_aisle_result import MappedAisleResult
from src.infrastructure.pipeline.v3_report_mapper import map_hybrid_report_to_domain

__all__ = [
    "MappedAisleResult",
    "map_hybrid_report_to_domain",
]
