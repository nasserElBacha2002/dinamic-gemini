"""Phase 5 — request / correlation context (contextvars)."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

_request_id: ContextVar[str | None] = ContextVar("observability_request_id", default=None)
_correlation_id: ContextVar[str | None] = ContextVar("observability_correlation_id", default=None)
_job_id: ContextVar[str | None] = ContextVar("observability_job_id", default=None)
_execution_id: ContextVar[str | None] = ContextVar("observability_execution_id", default=None)


@dataclass(frozen=True, slots=True)
class ObservabilityContext:
    request_id: str | None = None
    correlation_id: str | None = None
    job_id: str | None = None
    execution_id: str | None = None

    def as_log_fields(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.request_id:
            out["request_id"] = self.request_id
        if self.correlation_id:
            out["correlation_id"] = self.correlation_id
        if self.job_id:
            out["job_id"] = self.job_id
        if self.execution_id:
            out["execution_id"] = self.execution_id
        return out


def get_request_id() -> str | None:
    return _request_id.get()


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def get_job_id() -> str | None:
    return _job_id.get()


def get_execution_id() -> str | None:
    return _execution_id.get()


def get_observability_context() -> ObservabilityContext:
    return ObservabilityContext(
        request_id=get_request_id(),
        correlation_id=get_correlation_id(),
        job_id=get_job_id(),
        execution_id=get_execution_id(),
    )


def bind_request_ids(*, request_id: str, correlation_id: str) -> tuple[Any, Any]:
    """Bind HTTP IDs; returns tokens for reset."""
    t1 = _request_id.set(request_id)
    t2 = _correlation_id.set(correlation_id)
    return t1, t2


def reset_request_ids(tokens: tuple[Any, Any]) -> None:
    _request_id.reset(tokens[0])
    _correlation_id.reset(tokens[1])


def bind_job_context(*, job_id: str | None = None, execution_id: str | None = None) -> tuple[Any, Any]:
    t1 = _job_id.set(job_id)
    t2 = _execution_id.set(execution_id)
    return t1, t2


def reset_job_context(tokens: tuple[Any, Any]) -> None:
    _job_id.reset(tokens[0])
    _execution_id.reset(tokens[1])


def bind_correlation_id(correlation_id: str | None) -> Any:
    return _correlation_id.set(correlation_id)


def reset_correlation_id(token: Any) -> None:
    _correlation_id.reset(token)
