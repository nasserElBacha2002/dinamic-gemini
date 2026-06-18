"""Phase 4.7 — traceability artifact generation errors."""


class TraceabilityArtifactError(Exception):
    """Base error for durable traceability artifact generation."""

    def __init__(self, message: str, *, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class TraceabilityEvidenceMissingError(TraceabilityArtifactError):
    """Structural result_evidence rows required but absent."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="TRACEABILITY_EVIDENCE_MISSING")
