"""Pipeline adapters and mappers for v3 integration — Épica 6."""

from src.infrastructure.pipeline.v3_report_mapper import (
    MappedAisleResult,
    map_hybrid_report_to_domain,
)

__all__ = [
    "MappedAisleResult",
    "map_hybrid_report_to_domain",
]
