"""Durable recovery for stuck local CSV / package import materialization."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.application.ports.clock import Clock
from src.application.ports.local_csv_import_repository import LocalCsvImportRepository
from src.application.use_cases.inventories.manage_local_csv_import import ConfirmLocalCsvImport
from src.domain.local_csv_import.error_codes import (
    LOCAL_CSV_MATERIALIZATION_EXHAUSTED,
    LOCAL_CSV_MATERIALIZATION_IN_PROGRESS,
    is_retryable_error_code,
)
from src.domain.local_csv_import.errors import LocalCsvImportError
from src.domain.local_csv_import.statuses import LOCAL_CSV_IMPORT_STATUS_CONFIRMED
from src.observability.metrics.instruments import record_local_csv_import_event

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LocalCsvImportRecoveryConfig:
    max_attempts: int = 5
    lease_sec: int = 120
    backoff_base_sec: int = 60
    backoff_max_sec: int = 3600
    batch_size: int = 20


class LocalCsvImportRecoveryService:
    """Reclaim expired leases / failed imports and reuse ConfirmLocalCsvImport."""

    def __init__(
        self,
        *,
        import_repo: LocalCsvImportRepository,
        confirm: ConfirmLocalCsvImport,
        clock: Clock,
        config: LocalCsvImportRecoveryConfig | None = None,
    ) -> None:
        self._import_repo = import_repo
        self._confirm = confirm
        self._clock = clock
        self._config = config or LocalCsvImportRecoveryConfig()
        self._owner = f"import-recovery:{uuid.uuid4()}"

    def run_once(self, *, now: datetime | None = None) -> int:
        current = now or self._clock.now()
        candidates = self._import_repo.list_recovery_candidates(
            now=current,
            limit=self._config.batch_size,
        )
        recovered = 0
        for record in candidates:
            if int(record.materialization_attempts) >= self._config.max_attempts:
                self._import_repo.mark_materialization_failed(
                    import_id=record.id,
                    error_code=LOCAL_CSV_MATERIALIZATION_EXHAUSTED,
                    clock_now=self._clock.now,
                    requires_review=True,
                )
                record_local_csv_import_event(event="recovery_exhausted")
                continue
            try:
                confirmed, _duplicate = self._confirm.execute(
                    inventory_id=record.inventory_id,
                    export_id=record.export_id,
                    conflict_policy=record.conflict_policy or "SKIP",
                    confirmed_by_user_id=record.confirmed_by_user_id,
                    owner=self._owner,
                )
            except LocalCsvImportError as exc:
                if exc.code == LOCAL_CSV_MATERIALIZATION_IN_PROGRESS:
                    record_local_csv_import_event(event="active_lease_conflict")
                    continue
                retry_at = None
                if is_retryable_error_code(exc.code):
                    attempt = max(1, int(record.materialization_attempts))
                    delay = min(
                        self._config.backoff_max_sec,
                        self._config.backoff_base_sec * (2 ** (attempt - 1)),
                    )
                    retry_at = current + timedelta(seconds=delay)
                    self._import_repo.mark_materialization_failed(
                        import_id=record.id,
                        error_code=exc.code,
                        clock_now=self._clock.now,
                        next_retry_at=retry_at,
                    )
                    record_local_csv_import_event(event="retry")
                logger.info(
                    "local_csv_import_recovery_failed import_id=%s code=%s",
                    record.id,
                    exc.code,
                )
                continue
            if confirmed.status == LOCAL_CSV_IMPORT_STATUS_CONFIRMED:
                recovered += 1
                record_local_csv_import_event(event="recovery_succeeded")
        return recovered
