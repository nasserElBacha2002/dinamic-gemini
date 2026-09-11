"""Atomic persistence boundary for canonical physical positions."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol

from src.application.dto.position_materialization import MaterializePositionCommand
from src.domain.position_materialization.entities import (
    MaterializePositionResult,
    PositionMaterializationAssociationClaim,
    PositionMaterializationAssociationEvidence,
    PositionMaterializationAssociationStatus,
)


class PositionMaterializationUnitOfWork(Protocol):
    def lookup_replay(
        self,
        *,
        client_id: str,
        idempotency_key: str,
        request_hash: str,
    ) -> MaterializePositionResult | None: ...

    def materialize(
        self,
        command: MaterializePositionCommand,
        *,
        request_hash: str,
        now: datetime,
    ) -> MaterializePositionResult: ...

    def complete_association(
        self,
        request_id: str,
        *,
        target: PositionMaterializationAssociationStatus,
        error_code: str | None,
        now: datetime,
    ) -> bool: ...

    def get_association_status(
        self,
        request_id: str,
    ) -> PositionMaterializationAssociationStatus | None: ...

    def claim_due_associations(
        self,
        *,
        owner: str,
        now: datetime,
        lease: timedelta,
        batch: int,
        max_attempts: int,
    ) -> list[PositionMaterializationAssociationClaim]: ...

    def inspect_association_evidence(
        self, request_id: str
    ) -> PositionMaterializationAssociationEvidence: ...

    def complete_claimed(self, *, request_id: str, owner: str, now: datetime) -> bool: ...

    def reschedule_claimed(
        self,
        *,
        request_id: str,
        owner: str,
        now: datetime,
        next_retry_at: datetime,
        error_code: str,
    ) -> bool: ...

    def exhaust_claimed(
        self, *, request_id: str, owner: str, now: datetime, error_code: str
    ) -> bool: ...

    def release_expired_associations(self, *, now: datetime) -> int: ...
