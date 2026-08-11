"""Minimal DB cursor protocol for shared-transaction repository calls."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol


class SqlCursorLike(Protocol):
    """Cursor surface used when repositories join an outer Unit of Work transaction."""

    def execute(self, *args: Any, **kwargs: Any) -> Any: ...

    def executemany(self, *args: Any, **kwargs: Any) -> Any: ...

    def fetchone(self) -> Any: ...

    def fetchall(self) -> Sequence[Any]: ...

    @property
    def rowcount(self) -> int: ...
