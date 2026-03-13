"""
Stage 3 — Typed exceptions for global analysis flow.

Enables callers to distinguish validation (structure/schema) from parsing (JSON decode).
"""


class GlobalAnalysisValidationError(Exception):
    """Raised when the global analysis response fails structural/schema validation."""

    pass


class GlobalAnalysisParsingError(Exception):
    """Raised when the raw response cannot be parsed as JSON (e.g. invalid JSON)."""

    pass
