"""Legal finalization stage status transitions — Phase 3.3."""

from __future__ import annotations

from src.domain.jobs.finalization_evidence import StageStatus

_ALLOWED: dict[StageStatus, frozenset[StageStatus]] = {
    StageStatus.UNKNOWN: frozenset(
        {
            StageStatus.NOT_STARTED,
            StageStatus.IN_PROGRESS,
            StageStatus.VERIFICATION_REQUIRED,
            StageStatus.UNKNOWN,
        }
    ),
    StageStatus.NOT_STARTED: frozenset(
        {StageStatus.IN_PROGRESS, StageStatus.COMPLETED, StageStatus.CANCELED, StageStatus.UNKNOWN}
    ),
    StageStatus.IN_PROGRESS: frozenset(
        {
            StageStatus.COMPLETED,
            StageStatus.FAILED,
            StageStatus.CANCELED,
            StageStatus.VERIFICATION_REQUIRED,
        }
    ),
    StageStatus.FAILED: frozenset({StageStatus.VERIFICATION_REQUIRED, StageStatus.FAILED}),
    StageStatus.CANCELED: frozenset({StageStatus.CANCELED}),
    StageStatus.VERIFICATION_REQUIRED: frozenset(
        {StageStatus.COMPLETED, StageStatus.FAILED, StageStatus.VERIFICATION_REQUIRED}
    ),
    StageStatus.COMPLETED: frozenset({StageStatus.COMPLETED, StageStatus.VERIFICATION_REQUIRED}),
}


class InvalidStageTransitionError(ValueError):
    pass


def assert_stage_transition_allowed(current: StageStatus, new: StageStatus) -> None:
    allowed = _ALLOWED.get(current, frozenset())
    if new not in allowed:
        raise InvalidStageTransitionError(
            f"Illegal finalization stage transition: {current.value} -> {new.value}"
        )


def is_stage_transition_allowed(current: StageStatus, new: StageStatus) -> bool:
    try:
        assert_stage_transition_allowed(current, new)
        return True
    except InvalidStageTransitionError:
        return False
