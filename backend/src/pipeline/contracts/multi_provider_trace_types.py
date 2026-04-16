"""
Phase 7 — explicit shapes for ``provider_metadata['multi_provider_execution']`` trace payloads.

Runtime values are plain ``dict`` instances compatible with job JSON and execution logs; these
``TypedDict`` definitions document invariants for maintainers and static checkers.
"""

from __future__ import annotations

from typing import Literal, TypedDict, Union


class MultiProviderRunRowOk(TypedDict):
    """One successful provider branch in a multi-provider run."""

    provider_key: str
    status: Literal["ok"]
    provider_name: str
    model: str | None


class MultiProviderRunRowSkipped(TypedDict):
    """Sequential fallback: provider not attempted after an earlier success."""

    provider_key: str
    status: Literal["skipped"]
    reason: Literal["prior_provider_succeeded"]


class MultiProviderRunRowError(TypedDict):
    """Failed attempt row (``LLMProviderError`` or unexpected error before sequential gives up)."""

    provider_key: str
    status: Literal["error"]
    error_class: str
    error_code: str | None
    message: str


MultiProviderRunRow = Union[MultiProviderRunRowOk, MultiProviderRunRowSkipped, MultiProviderRunRowError]


class MultiProviderExecutionTrace(TypedDict):
    """Canonical ``multi_provider_execution`` blob attached to the primary ``AnalysisResult``."""

    strategy_effective: str
    ordered_provider_keys: list[str]
    primary_provider_key: str
    runs: list[MultiProviderRunRow]
