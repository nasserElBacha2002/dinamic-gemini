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
from typing import Any, Callable, Dict, Optional

from src.jobs.models import JobInput


@dataclass
class RunContext:
    """
    Execution context for a single pipeline run.

    Passed to all pipeline stages. Read for paths, settings, logger, progress.
    Do not attach stage outputs here; use stage return values instead.
    metadata is only for tracing, metrics, or runtime diagnostics—not for stage results.
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
