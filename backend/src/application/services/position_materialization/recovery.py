"""Recover pending materialization associations from exact durable evidence."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.application.ports.position_materialization_unit_of_work import (
    PositionMaterializationUnitOfWork,
)
from src.domain.position_materialization.entities import (
    PositionMaterializationAssociationClaim,
    PositionMaterializationEvidenceStatus,
)
from src.domain.position_materialization.errors import PositionMaterializationRetryableError
from src.observability.metrics.instruments import (
    PositionMaterializationMetricComponent,
    PositionMaterializationMetricMode,
    PositionMaterializationMetricOutcome,
    PositionMaterializationMetricReason,
    PositionMaterializationMetricSource,
    record_position_materialization,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PositionMaterializationRecoveryConfig:
    lease: timedelta
    batch_size: int
    max_attempts: int
    backoff_base: timedelta
    backoff_max: timedelta

    def __post_init__(self) -> None:
        if (
            self.lease.total_seconds() <= 0
            or self.batch_size < 1
            or self.max_attempts < 1
            or self.backoff_base.total_seconds() <= 0
            or self.backoff_max < self.backoff_base
        ):
            raise ValueError("Invalid materialization recovery configuration")


class PositionMaterializationAssociationRecoveryService:
    def __init__(
        self,
        unit_of_work: PositionMaterializationUnitOfWork,
        *,
        config: PositionMaterializationRecoveryConfig,
    ) -> None:
        self._uow = unit_of_work
        self._config = config

    def run_once(self, *, owner: str, now: datetime) -> int:
        self._uow.release_expired_associations(now=now)
        claims = self._uow.claim_due_associations(
            owner=owner,
            now=now,
            lease=self._config.lease,
            batch=self._config.batch_size,
            max_attempts=self._config.max_attempts,
        )
        completed = 0
        for claim in claims:
            if self._recover_claim(claim, now=now):
                completed += 1
        return completed

    def _recover_claim(
        self, claim: PositionMaterializationAssociationClaim, *, now: datetime
    ) -> bool:
        try:
            evidence = self._uow.inspect_association_evidence(claim.request_id)
        except PositionMaterializationRetryableError:
            logger.exception(
                "position_materialization_evidence_query_failed request_id=%s",
                claim.request_id,
            )
            return self._retry_or_exhaust(claim, now=now, error_code="EVIDENCE_QUERY_FAILED")
        if evidence.status is PositionMaterializationEvidenceStatus.PRESENT:
            completed = self._uow.complete_claimed(
                request_id=claim.request_id, owner=claim.owner, now=now
            )
            if completed:
                self._record(
                    PositionMaterializationMetricOutcome.ASSOCIATION_RECOVERED,
                    PositionMaterializationMetricReason.NONE,
                )
            return completed
        if evidence.status is PositionMaterializationEvidenceStatus.CONTRADICTION:
            exhausted = self._uow.exhaust_claimed(
                request_id=claim.request_id,
                owner=claim.owner,
                now=now,
                error_code="EVIDENCE_CONTRADICTION",
            )
            if exhausted:
                self._record(
                    PositionMaterializationMetricOutcome.RETRY_EXHAUSTED,
                    PositionMaterializationMetricReason.EVIDENCE_CONTRADICTION,
                )
            return exhausted
        return self._retry_or_exhaust(claim, now=now, error_code="ASSOCIATION_EVIDENCE_ABSENT")

    def _retry_or_exhaust(
        self,
        claim: PositionMaterializationAssociationClaim,
        *,
        now: datetime,
        error_code: str,
    ) -> bool:
        next_attempt = claim.attempt_count + 1
        if next_attempt >= self._config.max_attempts:
            exhausted = self._uow.exhaust_claimed(
                request_id=claim.request_id,
                owner=claim.owner,
                now=now,
                error_code=error_code,
            )
            if exhausted:
                self._record(
                    PositionMaterializationMetricOutcome.RETRY_EXHAUSTED,
                    PositionMaterializationMetricReason.MAX_ATTEMPTS,
                )
            return exhausted
        multiplier = 2 ** max(0, claim.attempt_count)
        delay = min(
            self._config.backoff_base * multiplier,
            self._config.backoff_max,
        )
        rescheduled = self._uow.reschedule_claimed(
            request_id=claim.request_id,
            owner=claim.owner,
            now=now,
            next_retry_at=now + delay,
            error_code=error_code,
        )
        if rescheduled:
            reason = (
                PositionMaterializationMetricReason.EVIDENCE_QUERY_FAILED
                if error_code == "EVIDENCE_QUERY_FAILED"
                else PositionMaterializationMetricReason.ASSOCIATION_EVIDENCE_ABSENT
            )
            self._record(PositionMaterializationMetricOutcome.TECHNICAL_RETRY, reason)
        return rescheduled

    @staticmethod
    def _record(
        outcome: PositionMaterializationMetricOutcome,
        reason: PositionMaterializationMetricReason,
    ) -> None:
        record_position_materialization(
            component=PositionMaterializationMetricComponent.RECOVERY,
            source=PositionMaterializationMetricSource.RECOVERY,
            mode=PositionMaterializationMetricMode.DINAMIC,
            outcome=outcome,
            reason_code=reason,
        )
