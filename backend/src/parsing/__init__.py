"""Parsing y validación de respuestas (v2.0 global analysis)."""

from src.parsing.global_analysis_parser import (
    GlobalAnalysisParseError,
    parse_global_analysis,
)

__all__ = ["parse_global_analysis", "GlobalAnalysisParseError"]
