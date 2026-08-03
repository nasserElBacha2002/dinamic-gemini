"""Aisle positioning reprocess orchestration (Phase 7 corrections)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from src.application.dto.access_principal import AccessPrincipal
from src.application.errors import IdempotencyKeyReusedError
from src.application.ports.clock import Clock
from src.application.ports.manual_position_override_repository import (
    ManualPositionOverrideRepository,
)
from src.application.ports.position_reconciliation_repository import (
    PositionReconciliationRepository,
)
from src.application.position_override_errors import PositionOverrideAccessDeniedError
from src.application.services.aisle_processing_state import resolve_aisle_processing_state
from src.application.services.image_processing.processing_action_idempotency_service import (
    ProcessingActionIdempotencyService,
)
from src.application.services.inventory_access_policy import InventoryAccessPolicy
from src.application.services.observability_access import (
    CAP_POSITION_PROCESSING_REPROCESS,
    capabilities_for_role,
)
from src.application.use_cases.aisles.get_aisle_processing_status import (
    GetAisleProcessingStatusUseCase,
)
from src.application.use_cases.aisles.start_aisle_processing import (
    StartAisleProcessingCommand,
    StartAisleProcessingUseCase,
)
from src.application.use_cases.position_reconciliation.reconcile_job_positions import (
    ReconcileJobPositionsCommand,
    ReconcileJobPositionsUseCase,
)
from src.domain.positioning_operational.entities import (
    ManualOverridePolicy,
    PositioningReprocessMode,
)
from src.observability.metrics.instruments import record_positioning_reprocess

logger = logging.getLogger(__name__)

_ACTION_TYPE = "POSITIONING_REPROCESS"


class PositioningReprocessError(Exception):
    def __init__(self, code: str, detail: str, *, http_status: int = 409) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.http_status = http_status


class PositioningReprocessValidationError(PositioningReprocessError):
    def __init__(self, detail: str) -> None:
        super().__init__("POSITION_REPROCESS_INVALID", detail, http_status=422)


@dataclass(frozen=True)
class ReprocessAislePositioningCommand:
    inventory_id: str
    aisle_id: str
    principal: AccessPrincipal
    idempotency_key: str
    reprocess_mode: str
    expected_active_job_id: str | None = None
    expected_result_job_id: str | None = None
    identification_mode: str | None = None


@dataclass(frozen=True)
class ReprocessAislePositioningResult:
    mode: str
    job_id: str | None
    reconciliation_id: str | None
    detail: str
    manuals_preserved: bool
    manual_override_policy: str
    previous_manual_overrides_count: int = 0


class ReprocessAislePositioningUseCase:
    """Idempotent aisle positioning reprocess using existing process/reconcile paths."""

    def __init__(
        self,
        *,
        status_use_case: GetAisleProcessingStatusUseCase,
        start_processing: StartAisleProcessingUseCase,
        reconcile: ReconcileJobPositionsUseCase,
        clock: Clock,
        access_policy: InventoryAccessPolicy,
        idempotency: ProcessingActionIdempotencyService,
        override_repo: ManualPositionOverrideRepository | None = None,
        reconciliation_repo: PositionReconciliationRepository | None = None,
        reprocessing_enabled: bool = True,
    ) -> None:
        self._status = status_use_case
        self._start = start_processing
        self._reconcile = reconcile
        self._clock = clock
        self._access = access_policy
        self._idempotency = idempotency
        self._override_repo = override_repo
        self._reconciliation_repo = reconciliation_repo
        self._enabled = bool(reprocessing_enabled)

    def execute(
        self, command: ReprocessAislePositioningCommand
    ) -> ReprocessAislePositioningResult:
        mode_for_metric = (command.reprocess_mode or "").strip().upper() or "unknown"
        try:
            result = self._execute(command)
            record_positioning_reprocess(
                mode=result.mode or mode_for_metric,
                outcome=(
                    "reused"
                    if "[idempotency_replay]" in (result.detail or "")
                    else "ok"
                ),
            )
            return result
        except PositioningReprocessError as exc:
            record_positioning_reprocess(mode=mode_for_metric, outcome=exc.code.lower())
            raise
        except Exception:
            record_positioning_reprocess(mode=mode_for_metric, outcome="error")
            raise

    def _execute(
        self, command: ReprocessAislePositioningCommand
    ) -> ReprocessAislePositioningResult:
        if not self._enabled:
            raise PositioningReprocessError(
                "POSITION_REPROCESSING_DISABLED",
                "Position reprocessing is disabled.",
                http_status=403,
            )
        self._access.require_inventory(command.inventory_id, command.principal)
        self._require_cap(command.principal)

        mode_raw = (command.reprocess_mode or "").strip().upper()
        try:
            mode = PositioningReprocessMode(mode_raw)
        except ValueError as exc:
            raise PositioningReprocessValidationError(
                f"Unsupported reprocess_mode {command.reprocess_mode!r}. "
                f"Supported: {[m.value for m in PositioningReprocessMode]}"
            ) from exc

        key = (command.idempotency_key or "").strip()
        if not key:
            raise PositioningReprocessValidationError("idempotency_key is required")

        status = self._status.execute(command.inventory_id, command.aisle_id)
        processing = resolve_aisle_processing_state(
            latest_job=status.latest_job,
            recent_jobs=status.recent_jobs,
            operational_job_id=status.aisle.operational_job_id,
            clock=self._clock,
        )

        # Resolve authoritative current jobs first; never use expected_* as selection.
        # Active job is only present while processing cannot start a new run
        # (same contract as operational view).
        current_active = (
            processing.job_id if not processing.can_start_new else None
        )
        current_result = (
            status.aisle.operational_job_id
            or (status.latest_job.id if status.latest_job else None)
        )

        # Compare including None: omit/null means "I expect no active/result job".
        expected_active = (command.expected_active_job_id or "").strip() or None
        if expected_active != current_active:
            raise PositioningReprocessError(
                "ACTIVE_JOB_MISMATCH",
                "expected_active_job_id does not match current active job.",
            )

        expected_result = (command.expected_result_job_id or "").strip() or None
        if expected_result != current_result:
            raise PositioningReprocessError(
                "RESULT_JOB_MISMATCH",
                "expected_result_job_id does not match current operational/result job.",
            )

        previous_manuals = self._count_manuals(current_result)

        payload = {
            "mode": mode.value,
            "expected_active_job_id": (
                (command.expected_active_job_id or "").strip() or None
                if command.expected_active_job_id is not None
                else None
            ),
            "expected_result_job_id": (
                (command.expected_result_job_id or "").strip() or None
                if command.expected_result_job_id is not None
                else None
            ),
            "identification_mode": command.identification_mode,
            "inventory_id": command.inventory_id,
            "aisle_id": command.aisle_id,
        }
        now = self._now()
        try:
            begun = self._idempotency.begin(
                action_type=_ACTION_TYPE,
                job_id=command.aisle_id,
                asset_id=mode.value,
                idempotency_key=key,
                payload=payload,
                actor=command.principal.actor_id,
                now=now,
            )
        except IdempotencyKeyReusedError as exc:
            raise PositioningReprocessError(
                "POSITION_REPROCESS_IDEMPOTENCY_CONFLICT",
                str(exc),
                http_status=409,
            ) from exc

        if begun.replay and begun.response:
            replayed = self._from_snapshot(begun.response)
            return ReprocessAislePositioningResult(
                mode=replayed.mode,
                job_id=replayed.job_id,
                reconciliation_id=replayed.reconciliation_id,
                detail=f"{replayed.detail} [idempotency_replay]",
                manuals_preserved=replayed.manuals_preserved,
                manual_override_policy=replayed.manual_override_policy,
                previous_manual_overrides_count=replayed.previous_manual_overrides_count,
            )

        if mode is PositioningReprocessMode.RECONCILE_ONLY:
            result = self._reconcile_only(
                command=command,
                current_result=current_result,
                previous_manuals=previous_manuals,
            )
        else:
            if not processing.can_start_new:
                if processing.recoverable:
                    raise PositioningReprocessError(
                        "PROCESSING_RECOVERY_REQUIRED",
                        "Recover the stuck job before reprocessing.",
                    )
                raise PositioningReprocessError(
                    "ACTIVE_JOB_EXISTS",
                    "An active processing job already exists for this aisle.",
                )
            result = self._full_reprocess(
                command=command,
                key=key,
                previous_manuals=previous_manuals,
            )

        self._idempotency.complete(
            begun.record,
            response=self._to_snapshot(result),
            now=self._now(),
        )
        return result

    def _reconcile_only(
        self,
        *,
        command: ReprocessAislePositioningCommand,
        current_result: str | None,
        previous_manuals: int,
    ) -> ReprocessAislePositioningResult:
        if not current_result:
            raise PositioningReprocessError(
                "POSITION_RECONCILIATION_NOT_READY",
                "No result job available to reconcile.",
                http_status=422,
            )
        recon_result = self._reconcile.execute(
            ReconcileJobPositionsCommand(
                inventory_id=command.inventory_id,
                job_id=current_result,
                principal=command.principal,
            )
        )
        recon_id = recon_result.reconciliation.id
        logger.info(
            "positioning_reprocess mode=RECONCILE_ONLY inventory_id=%s aisle_id=%s "
            "job_id=%s reconciliation_id=%s",
            command.inventory_id,
            command.aisle_id,
            current_result,
            recon_id,
        )
        return ReprocessAislePositioningResult(
            mode=PositioningReprocessMode.RECONCILE_ONLY.value,
            job_id=current_result,
            reconciliation_id=str(recon_id) if recon_id else None,
            detail=(
                "Reconciliation completed on the same job. "
                "Manual overrides remain effective for existing result IDs."
            ),
            manuals_preserved=True,
            manual_override_policy=ManualOverridePolicy.PRESERVED.value,
            previous_manual_overrides_count=previous_manuals,
        )

    def _full_reprocess(
        self,
        *,
        command: ReprocessAislePositioningCommand,
        key: str,
        previous_manuals: int,
    ) -> ReprocessAislePositioningResult:
        # Do not force CODE_SCAN — inherit unless caller overrides.
        started = self._start.execute(
            StartAisleProcessingCommand(
                inventory_id=command.inventory_id,
                aisle_id=command.aisle_id,
                principal=command.principal,
                requested_identification_mode=command.identification_mode,
                idempotency_key=key,
                resolve_execution_keys=True,
            )
        )
        logger.info(
            "positioning_reprocess mode=REPROCESS_FULL_AISLE inventory_id=%s aisle_id=%s "
            "job_id=%s previous_manuals=%s",
            command.inventory_id,
            command.aisle_id,
            started.job_id,
            previous_manuals,
        )
        return ReprocessAislePositioningResult(
            mode=PositioningReprocessMode.REPROCESS_FULL_AISLE.value,
            job_id=started.job_id,
            reconciliation_id=None,
            detail=(
                "Full aisle reprocess started as a new job. "
                "Manual overrides from the previous job are not auto-migrated; "
                "review after completion."
            ),
            manuals_preserved=False,
            manual_override_policy=ManualOverridePolicy.REQUIRES_REVIEW_AFTER_NEW_JOB.value,
            previous_manual_overrides_count=previous_manuals,
        )

    def _count_manuals(self, job_id: str | None) -> int:
        if not job_id or self._override_repo is None or self._reconciliation_repo is None:
            return 0
        assignments = list(self._reconciliation_repo.list_active_assignments(job_id))
        result_ids = [a.result_id for a in assignments if a.result_id]
        if not result_ids:
            return 0
        return len(self._override_repo.list_active_for_results(job_id, result_ids))

    def _now(self) -> datetime:
        now = self._clock.now()
        if now.tzinfo is None:
            return now.replace(tzinfo=timezone.utc)
        return now

    @staticmethod
    def _to_snapshot(result: ReprocessAislePositioningResult) -> dict:
        return {
            "mode": result.mode,
            "job_id": result.job_id,
            "reconciliation_id": result.reconciliation_id,
            "detail": result.detail,
            "manuals_preserved": result.manuals_preserved,
            "manual_override_policy": result.manual_override_policy,
            "previous_manual_overrides_count": result.previous_manual_overrides_count,
        }

    @staticmethod
    def _from_snapshot(payload: dict) -> ReprocessAislePositioningResult:
        return ReprocessAislePositioningResult(
            mode=str(payload.get("mode") or ""),
            job_id=payload.get("job_id"),
            reconciliation_id=payload.get("reconciliation_id"),
            detail=str(payload.get("detail") or ""),
            manuals_preserved=bool(payload.get("manuals_preserved")),
            manual_override_policy=str(
                payload.get("manual_override_policy")
                or ManualOverridePolicy.NOT_APPLICABLE.value
            ),
            previous_manual_overrides_count=int(
                payload.get("previous_manual_overrides_count") or 0
            ),
        )

    @staticmethod
    def _require_cap(principal: AccessPrincipal) -> None:
        if principal.is_platform:
            return
        caps: set[str] = set()
        for role in principal.roles:
            caps.update(capabilities_for_role(role))
        if CAP_POSITION_PROCESSING_REPROCESS not in caps:
            raise PositionOverrideAccessDeniedError(
                f"Missing capability: {CAP_POSITION_PROCESSING_REPROCESS}"
            )
