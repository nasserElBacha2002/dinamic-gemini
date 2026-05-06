"""Port for reading stored job artifacts (e.g. hybrid report) without coupling to HTTP or storage adapters."""

from __future__ import annotations

from typing import Any, Protocol


class StoredArtifactReader(Protocol):
    def load_hybrid_report_json_for_job(self, job_id: str) -> dict[str, Any] | None:
        """Load ``hybrid_report`` JSON for best-effort use; return ``None`` if unavailable."""


__all__ = ["StoredArtifactReader"]
