"""
PipelineStage — homogeneous interface for pipeline stages (v2.3.A).

Each stage receives RunContext and input data, returns result explicitly.
Types are permissive (Any) in 2.3.A; can be hardened to DTOs in 2.3.B.
"""

from __future__ import annotations

from typing import Any, Protocol

from src.pipeline.context.run_context import RunContext


class PipelineStage(Protocol):
    """
    Protocol for a single pipeline stage.

    Stages must not mutate RunContext with stage outputs; data flows via return values.
    """

    def run(self, context: RunContext, data: Any) -> Any:
        """
        Execute the stage.

        Args:
            context: Run-level context (paths, settings, logger, progress).
            data: Input from the previous stage (or None for the first stage).

        Returns:
            Result for the next stage. Type is stage-specific (e.g. PreparedInput).
        """
        ...
