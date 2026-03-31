"""
RunContext — execution-level context for a pipeline run (v2.3.A).

RunContext MUST contain only:
- Run metadata (run_id, job_id)
- Job identifiers and references (job_input)
- Configuration snapshot (settings)
- Logging context (logger)
- Artifact paths (workspace_path, run_dir)
- Optional progress callback and metadata dict

RunContext MUST NOT be used as a shared mutable container for stage outputs.
Stage outputs must flow via explicit typed result objects returned by each stage.

The metadata dict is only for tracing, metrics, or runtime diagnostics (e.g. timestamps,
counters). It must NOT be used to pass stage outputs between stages.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from src.jobs.models import JobInput

JobExecutionObserver = Callable[[str, Optional[str], str, Optional[Dict[str, Any]]], None]

if TYPE_CHECKING:
    from src.pipeline.execution_log import ExecutionLogWriter
    from src.pipeline.contracts.analysis_context import AnalysisContext


@dataclass
class RunContext:
    """
    Execution context for a single pipeline run.

    Passed to all pipeline stages. Read for paths, settings, logger, progress.
    Do not attach stage outputs here; use stage return values instead.
    metadata is only for tracing, metrics, or runtime diagnostics—not for stage results.
    execution_log: optional writer for structured job execution log (v3.1.1).
    """

    job_id: str
    run_id: str
    workspace_path: Path
    run_dir: Path
    job_input: JobInput
    settings: Any  # Settings from src.config; avoid circular import
    logger: logging.Logger
    progress_callback: Optional[Callable[[str, int], None]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    execution_log: Optional["ExecutionLogWriter"] = None
    execution_observer: Optional[JobExecutionObserver] = None
    # Phase 3/4/5: typed, provider-agnostic analysis context prepared upstream.
    # This is *input* to analysis, not a stage output; avoids relying on raw metadata dicts.
    analysis_context: Optional["AnalysisContext"] = None

    def emit_stage_event(
        self,
        *,
        stage: str,
        event: str,
        substep: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[int] = None,
        level: str = "info",
    ) -> None:
        if self.execution_log is not None:
            metadata = self.job_input.metadata or {}
            self.execution_log.structured_event(
                job_id=self.job_id,
                inventory_id=metadata.get("inventory_id"),
                aisle_id=metadata.get("aisle_id"),
                attempt=int(metadata.get("attempt_count") or 1),
                stage=stage,
                substep=substep,
                event=event,
                duration_ms=duration_ms,
                details=details,
                level=level,
            )
        if self.execution_observer is not None:
            self.execution_observer(stage, substep, event, details)
