"""Application orchestration for canonical physical-position materialization."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime, timezone

from src.application.dto.position_materialization import (
    MaterializePositionCommand,
    build_fingerprint_v1,
)
from src.application.ports.position_materialization_unit_of_work import (
    PositionMaterializationUnitOfWork,
)
from src.domain.position_materialization.entities import (
    MAX_ACTOR_LENGTH,
    MAX_ID_LENGTH,
    MAX_IDEMPOTENCY_KEY_LENGTH,
    MAX_NORMALIZED_CODE_LENGTH,
    MAX_RAW_CODE_LENGTH,
    MaterializePositionResult,
    PositionMaterializationAssociationStatus,
    PositionMaterializationStatus,
)
from src.domain.position_materialization.errors import (
    PositionMaterializationConflictError,
    PositionMaterializationInvariantError,
    PositionMaterializationInventoryStateError,
    PositionMaterializationRetryableError,
    PositionMaterializationScopeError,
)
from src.domain.position_recognition.entities import PositionRecognitionSource
from src.observability.metrics.instruments import (
    PositionMaterializationMetricComponent,
    PositionMaterializationMetricMode,
    PositionMaterializationMetricOutcome,
    PositionMaterializationMetricReason,
    PositionMaterializationMetricSource,
    record_position_materialization,
)

logger = logging.getLogger(__name__)

_IDEMPOTENCY_CONFLICT_CODES = frozenset({"IDEMPOTENCY_KEY_CONFLICT"})
_IDENTITY_CONFLICT_CODES = frozenset(
    {
        "INACTIVE_POSITION_IDENTITY",
        "POSITION_IDENTITY_CONFLICT",
    }
)


def canonical_request_fingerprint(command: MaterializePositionCommand) -> str:
    """Return SHA-256 over the versioned semantic request payload."""
    payload = asdict(build_fingerprint_v1(command))
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _nonempty_with_limit(value: str | None, *, field: str, limit: int) -> str | None:
    if value is None:
        return None
    if not value.strip():
        raise ValueError(f"{field} must not be blank")
    if len(value) > limit:
        raise ValueError(f"{field} exceeds {limit} characters")
    return value


def _validate(command: MaterializePositionCommand) -> None:
    _nonempty_with_limit(command.inventory_id, field="inventory_id", limit=MAX_ID_LENGTH)
    _nonempty_with_limit(command.aisle_id, field="aisle_id", limit=MAX_ID_LENGTH)
    _nonempty_with_limit(
        command.idempotency_key,
        field="idempotency_key",
        limit=MAX_IDEMPOTENCY_KEY_LENGTH,
    )
    _nonempty_with_limit(command.capture_id, field="capture_id", limit=MAX_ID_LENGTH)
    _nonempty_with_limit(
        command.principal.actor_id,
        field="principal.actor_id",
        limit=MAX_ACTOR_LENGTH,
    )
    if command.principal.client_id is None:
        raise PositionMaterializationScopeError(
            "A tenant-bound principal is required",
            code="PRINCIPAL_CLIENT_REQUIRED",
        )
    _nonempty_with_limit(
        command.principal.client_id,
        field="principal.client_id",
        limit=MAX_ID_LENGTH,
    )
    recognition = command.recognition
    if recognition.raw_code is not None:
        _nonempty_with_limit(
            recognition.raw_code,
            field="recognition.raw_code",
            limit=MAX_RAW_CODE_LENGTH,
        )
    elif command.safe_raw_evidence is None:
        raise ValueError("raw recognition or safe_raw_evidence is required")
    if command.safe_raw_evidence is not None:
        _nonempty_with_limit(
            command.safe_raw_evidence.payload_hash,
            field="safe_raw_evidence.payload_hash",
            limit=128,
        )
        _nonempty_with_limit(
            command.safe_raw_evidence.display_code,
            field="safe_raw_evidence.display_code",
            limit=MAX_NORMALIZED_CODE_LENGTH,
        )
        if (
            command.safe_raw_evidence.utf8_length is not None
            and command.safe_raw_evidence.utf8_length < 0
        ):
            raise ValueError("safe_raw_evidence.utf8_length must be non-negative")
    _nonempty_with_limit(
        recognition.normalized_code,
        field="recognition.normalized_code",
        limit=MAX_NORMALIZED_CODE_LENGTH,
    )
    _nonempty_with_limit(
        recognition.client_supplier_id,
        field="recognition.client_supplier_id",
        limit=MAX_ID_LENGTH,
    )
    _nonempty_with_limit(
        recognition.profile_id, field="recognition.profile_id", limit=MAX_ID_LENGTH
    )
    if recognition.profile_version is not None and recognition.profile_version < 1:
        raise ValueError("recognition.profile_version must be positive")
    if recognition.level is not None and recognition.level < 0:
        raise ValueError("recognition.level must be non-negative")
    if recognition.marker_index is not None and recognition.marker_index < 1:
        raise ValueError("recognition.marker_index must be positive")
    if recognition.marker_total is not None and recognition.marker_total < 1:
        raise ValueError("recognition.marker_total must be positive")
    if (
        recognition.marker_index is not None
        and recognition.marker_total is not None
        and recognition.marker_index > recognition.marker_total
    ):
        raise ValueError("recognition.marker_index exceeds marker_total")
    build_fingerprint_v1(command)


class MaterializePositionService:
    def __init__(
        self,
        unit_of_work: PositionMaterializationUnitOfWork,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def execute(self, command: MaterializePositionCommand) -> MaterializePositionResult:
        try:
            _validate(command)
        except PositionMaterializationScopeError as exc:
            result = self._rejected(PositionMaterializationStatus.REJECTED_SCOPE, exc)
            self._record_result_metric(command, result)
            return result
        except (TypeError, ValueError) as exc:
            result = MaterializePositionResult(
                status=PositionMaterializationStatus.REJECTED_VALIDATION,
                error_code="INVALID_MATERIALIZATION_REQUEST",
                detail=str(exc),
            )
            self._record_result_metric(command, result)
            return result

        try:
            request_hash = canonical_request_fingerprint(command)
            result = self._unit_of_work.materialize(
                command,
                request_hash=request_hash,
                now=self._clock(),
            )
        except PositionMaterializationScopeError as exc:
            result = self._rejected(PositionMaterializationStatus.REJECTED_SCOPE, exc)
        except PositionMaterializationConflictError as exc:
            result = self._rejected(self._conflict_status(exc.code), exc)
        except PositionMaterializationInventoryStateError as exc:
            result = self._rejected(PositionMaterializationStatus.REJECTED_INVENTORY_STATE, exc)
        except PositionMaterializationRetryableError as exc:
            result = self._rejected(PositionMaterializationStatus.RETRYABLE_FAILURE, exc)
        except PositionMaterializationInvariantError as exc:
            result = self._rejected(PositionMaterializationStatus.INVARIANT_VIOLATION, exc)
        else:
            logger.info(
                "position_materialization status=%s location_id=%s inventory_id=%s aisle_id=%s",
                result.status.value,
                result.location_id,
                command.inventory_id,
                command.aisle_id,
            )

        self._record_result_metric(command, result)
        return result

    def materialize(self, command: MaterializePositionCommand) -> MaterializePositionResult:
        return self.execute(command)

    def lookup_replay(
        self,
        command: MaterializePositionCommand,
    ) -> MaterializePositionResult | None:
        _validate(command)
        client_id = command.principal.client_id
        assert client_id is not None
        return self._unit_of_work.lookup_replay(
            client_id=client_id,
            idempotency_key=command.idempotency_key,
            request_hash=canonical_request_fingerprint(command),
        )

    def complete_association(
        self,
        request_id: str,
        *,
        success: bool,
        error_code: str | None = None,
        now: datetime | None = None,
    ) -> bool:
        normalized_request_id = _nonempty_with_limit(
            request_id,
            field="request_id",
            limit=MAX_ID_LENGTH,
        )
        assert normalized_request_id is not None
        normalized_error = (error_code or "").strip() or None
        if success:
            if normalized_error is not None:
                raise ValueError("error_code must be absent for a successful association")
            target = PositionMaterializationAssociationStatus.ASSOCIATED
        else:
            if normalized_error is None:
                raise ValueError("error_code is required when association fails")
            if len(normalized_error) > 64:
                raise ValueError("error_code exceeds 64 characters")
            target = PositionMaterializationAssociationStatus.REQUIRES_REVIEW
        try:
            completed = self._unit_of_work.complete_association(
                normalized_request_id,
                target=target,
                error_code=normalized_error,
                now=now or self._clock(),
            )
        except PositionMaterializationRetryableError:
            self._record_association_metric(
                outcome=PositionMaterializationMetricOutcome.ASSOCIATION_PENDING,
                reason=PositionMaterializationMetricReason.ASSOCIATION_WRITE_PENDING,
            )
            logger.warning(
                "position_materialization_association_retryable request_id=%s target=%s",
                normalized_request_id,
                target.value,
            )
            return False
        if not success:
            self._record_association_metric(
                outcome=PositionMaterializationMetricOutcome.REQUIRES_REVIEW,
                reason=PositionMaterializationMetricReason.DOWNSTREAM_REQUIRES_REVIEW,
            )
        logger.info(
            "position_materialization_association request_id=%s target=%s completed=%s",
            normalized_request_id,
            target.value,
            completed,
        )
        return completed

    def get_association_status(
        self,
        request_id: str,
    ) -> PositionMaterializationAssociationStatus | None:
        normalized_request_id = _nonempty_with_limit(
            request_id,
            field="request_id",
            limit=MAX_ID_LENGTH,
        )
        assert normalized_request_id is not None
        return self._unit_of_work.get_association_status(normalized_request_id)

    @staticmethod
    def _conflict_status(code: str) -> PositionMaterializationStatus:
        if code in _IDEMPOTENCY_CONFLICT_CODES:
            return PositionMaterializationStatus.REJECTED_IDEMPOTENCY_CONFLICT
        if code in _IDENTITY_CONFLICT_CODES or (
            code.startswith("POSITION_") and code.endswith("_CONFLICT")
        ):
            return PositionMaterializationStatus.REJECTED_IDENTITY_CONFLICT
        return PositionMaterializationStatus.INVARIANT_VIOLATION

    @staticmethod
    def _rejected(
        status: PositionMaterializationStatus,
        exc: PositionMaterializationScopeError
        | PositionMaterializationConflictError
        | PositionMaterializationInventoryStateError
        | PositionMaterializationRetryableError
        | PositionMaterializationInvariantError,
    ) -> MaterializePositionResult:
        logger.warning(
            "position_materialization_rejected status=%s code=%s", status.value, exc.code
        )
        return MaterializePositionResult(status=status, error_code=exc.code, detail=str(exc))

    @classmethod
    def _record_result_metric(
        cls,
        command: MaterializePositionCommand,
        result: MaterializePositionResult,
    ) -> None:
        if result.idempotent_replay:
            outcome = PositionMaterializationMetricOutcome.IDEMPOTENT_REPLAY
            reason = PositionMaterializationMetricReason.NONE
        else:
            outcome, reason = {
                PositionMaterializationStatus.MATERIALIZED: (
                    PositionMaterializationMetricOutcome.CREATED,
                    PositionMaterializationMetricReason.NONE,
                ),
                PositionMaterializationStatus.REUSED: (
                    PositionMaterializationMetricOutcome.REUSED,
                    PositionMaterializationMetricReason.NONE,
                ),
                PositionMaterializationStatus.REJECTED_CONFLICT: (
                    PositionMaterializationMetricOutcome.VALIDATION_REJECTED,
                    PositionMaterializationMetricReason.INVARIANT_VIOLATION,
                ),
                PositionMaterializationStatus.REJECTED_IDEMPOTENCY_CONFLICT: (
                    PositionMaterializationMetricOutcome.IDEMPOTENCY_CONFLICT,
                    PositionMaterializationMetricReason.IDEMPOTENCY_CONFLICT,
                ),
                PositionMaterializationStatus.REJECTED_IDENTITY_CONFLICT: (
                    PositionMaterializationMetricOutcome.IDENTITY_CONFLICT,
                    PositionMaterializationMetricReason.IDENTITY_CONFLICT,
                ),
                PositionMaterializationStatus.RETRYABLE_FAILURE: (
                    PositionMaterializationMetricOutcome.TECHNICAL_RETRY,
                    PositionMaterializationMetricReason.TECHNICAL_FAILURE,
                ),
                PositionMaterializationStatus.REJECTED_SCOPE: (
                    PositionMaterializationMetricOutcome.VALIDATION_REJECTED,
                    PositionMaterializationMetricReason.SCOPE_REJECTED,
                ),
                PositionMaterializationStatus.REJECTED_INVENTORY_STATE: (
                    PositionMaterializationMetricOutcome.VALIDATION_REJECTED,
                    PositionMaterializationMetricReason.INVENTORY_STATE,
                ),
                PositionMaterializationStatus.INVARIANT_VIOLATION: (
                    PositionMaterializationMetricOutcome.VALIDATION_REJECTED,
                    PositionMaterializationMetricReason.INVARIANT_VIOLATION,
                ),
                PositionMaterializationStatus.REJECTED_VALIDATION: (
                    PositionMaterializationMetricOutcome.VALIDATION_REJECTED,
                    PositionMaterializationMetricReason.INVALID_REQUEST,
                ),
            }[result.status]
        cls._record_metric(command, outcome=outcome, reason=reason)
        if result.accepted:
            cls._record_metric(
                command,
                outcome=PositionMaterializationMetricOutcome.ASSOCIATION_PENDING,
                reason=PositionMaterializationMetricReason.NONE,
            )

    @staticmethod
    def _record_association_metric(
        *,
        outcome: PositionMaterializationMetricOutcome,
        reason: PositionMaterializationMetricReason,
    ) -> None:
        record_position_materialization(
            component=PositionMaterializationMetricComponent.SERVICE,
            source=PositionMaterializationMetricSource.API,
            mode=PositionMaterializationMetricMode.DINAMIC,
            outcome=outcome,
            reason_code=reason,
        )

    @staticmethod
    def _record_metric(
        command: MaterializePositionCommand,
        *,
        outcome: PositionMaterializationMetricOutcome,
        reason: PositionMaterializationMetricReason,
    ) -> None:
        recognition = command.recognition
        source = (
            PositionMaterializationMetricSource(recognition.source.value)
            if isinstance(recognition.source, PositionRecognitionSource)
            else PositionMaterializationMetricSource.API
        )
        record_position_materialization(
            component=PositionMaterializationMetricComponent.SERVICE,
            source=source,
            mode=(
                PositionMaterializationMetricMode.SUPPLIER
                if recognition.client_supplier_id
                else PositionMaterializationMetricMode.DINAMIC
            ),
            outcome=outcome,
            reason_code=reason,
        )
