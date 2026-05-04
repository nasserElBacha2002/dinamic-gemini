"""
ArtifactStorage port — save/retrieve/list artifacts (Stage 2.3.B).

Introduced in Stage B as a preparatory abstraction. The main pipeline still writes artifacts
through existing logic (reporting/evidence modules); this port is not yet the source of truth
for artifact writes. Future stages may refactor pipeline/reporting to use ArtifactStorage.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class ArtifactStorage(Protocol):
    """
    Port for artifact storage (preparatory in Stage B).

    Adapters write to filesystem or object storage under a base path. The main pipeline,
    reporting, and evidence flows do not use this port yet; artifact writes remain in existing modules.
    """

    def write_json(self, relative_path: str, payload: dict[str, Any]) -> Path:
        """Write payload as JSON at base_path / relative_path; return path written."""
        ...

    def write_bytes(
        self, relative_path: str, content: bytes, content_type: str = "application/octet-stream"
    ) -> Path:
        """Write raw bytes at relative_path; return path written."""
        ...

    def exists(self, relative_path: str) -> bool:
        """Return True if relative_path exists under base."""
        ...

    def list_artifacts(self) -> list[str]:
        """List relative paths of artifacts under base (optional)."""
        ...
