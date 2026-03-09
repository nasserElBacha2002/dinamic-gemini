"""
FileSystemArtifactStorage — implements ArtifactStorage under a base path (Stage 2.3.B).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from src.reporting.artifacts import write_json as _write_json


class FileSystemArtifactStorage:
    """
    Writes artifacts under base_path (e.g. context.run_dir).

    This adapter is not yet used by the main pipeline or reporting; the latter still write
    through existing logic. It is available for tests and future Stage C integration.
    """

    def __init__(self, base_path: Path) -> None:
        self._base_path = Path(base_path)

    def write_json(self, relative_path: str, payload: Dict[str, Any]) -> Path:
        path = self._base_path / relative_path
        _write_json(path, payload)
        return path

    def write_bytes(
        self, relative_path: str, content: bytes, content_type: str = "application/octet-stream"
    ) -> Path:
        path = self._base_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def exists(self, relative_path: str) -> bool:
        return (self._base_path / relative_path).exists()

    def list_artifacts(self) -> List[str]:
        if not self._base_path.exists():
            return []
        out: List[str] = []
        for p in self._base_path.rglob("*"):
            if p.is_file():
                try:
                    rel = p.relative_to(self._base_path)
                    if ".." not in str(rel):
                        out.append(str(rel))
                except ValueError:
                    pass
        return sorted(out)
