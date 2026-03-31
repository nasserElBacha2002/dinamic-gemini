from __future__ import annotations


class PipelineCancellationRequestedError(RuntimeError):
    """Raised when cooperative job cancellation should stop the current pipeline run."""

    def __init__(self, message: str = "Job cancellation requested") -> None:
        super().__init__(message)
