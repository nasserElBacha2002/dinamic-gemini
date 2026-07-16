"""SQL Server Unit of Work for atomic manual image-result creation."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable

from src.application.ports.clock import Clock
from src.application.ports.manual_image_result_unit_of_work import (
    ManualImageResultRepositories,
)
from src.application.services.aisle_review_lifecycle_sync import AisleReviewLifecycleSync
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.database.sqlserver import SqlServerClient
from src.infrastructure.database.sql_transaction import SqlServerTransaction, TransactionState
from src.infrastructure.persistence.image_result_applock import acquire_image_result_applock
from src.infrastructure.persistence.sql_job_image_coverage_repository import (
    SqlJobImageCoverageRepository,
)
from src.infrastructure.persistence.sql_manual_image_coverage_repository import (
    SqlManualImageCoverageRepository,
)
from src.infrastructure.repositories.sql_aisle_repository import SqlAisleRepository
from src.infrastructure.repositories.sql_evidence_repository import SqlEvidenceRepository
from src.infrastructure.repositories.sql_inventory_repository import SqlInventoryRepository
from src.infrastructure.repositories.sql_position_repository import SqlPositionRepository
from src.infrastructure.repositories.sql_product_record_repository import SqlProductRecordRepository
from src.infrastructure.repositories.sql_result_evidence_repository import (
    SqlResultEvidenceRepository,
)
from src.infrastructure.repositories.sql_review_action_repository import SqlReviewActionRepository

logger = logging.getLogger(__name__)


@dataclass
class SqlManualImageResultUnitOfWork:
    _client: SqlServerClient
    _clock: Clock
    _inventory_id: str | None = field(default=None, init=False)
    _aisle_id: str | None = field(default=None, init=False)
    _tx: SqlServerTransaction | None = field(default=None, init=False)
    _tx_repos: ManualImageResultRepositories | None = field(default=None, init=False)
    _lifecycle_sync: AisleReviewLifecycleSync | None = field(default=None, init=False)
    _committed: bool = field(default=False, init=False)
    _rolled_back: bool = field(default=False, init=False)
    timing_ms: dict[str, float] = field(default_factory=dict, init=False)

    @property
    def repositories(self) -> ManualImageResultRepositories:
        if self._tx_repos is None:
            raise RuntimeError("SqlManualImageResultUnitOfWork is not active")
        return self._tx_repos

    def bind_lifecycle_scope(self, *, inventory_id: str, aisle_id: str) -> None:
        self._inventory_id = inventory_id
        self._aisle_id = aisle_id

    def acquire_image_result_lock(self, *, job_id: str, source_asset_id: str) -> None:
        if self._tx is None:
            raise RuntimeError("SqlManualImageResultUnitOfWork is not active")
        started = time.perf_counter()
        acquire_image_result_applock(
            self._tx.connection,
            job_id=job_id,
            source_asset_id=source_asset_id,
        )
        self.timing_ms["lock_acquisition_ms"] = (time.perf_counter() - started) * 1000.0

    def commit(self) -> None:
        if self._rolled_back:
            raise RuntimeError("Cannot commit after rollback")
        if self._tx is None:
            raise RuntimeError("SqlManualImageResultUnitOfWork is not active")
        if self._lifecycle_sync is None:
            raise RuntimeError("Transactional lifecycle sync is not initialized")
        if self._inventory_id and self._aisle_id:
            started = time.perf_counter()
            self._lifecycle_sync.after_review_mutation(self._inventory_id, self._aisle_id)
            self.timing_ms["lifecycle_sync_ms"] = (time.perf_counter() - started) * 1000.0
        started = time.perf_counter()
        self._tx.commit()
        self.timing_ms["transaction_commit_ms"] = (time.perf_counter() - started) * 1000.0
        self._committed = True
        logger.debug("SqlManualImageResultUnitOfWork committed timing=%s", self.timing_ms)

    def rollback(self) -> None:
        if self._rolled_back:
            return
        if self._tx is not None and self._tx.state == TransactionState.ACTIVE:
            self._tx.rollback()
        self._committed = False
        self._rolled_back = True
        logger.warning("SqlManualImageResultUnitOfWork rolled back")

    def __enter__(self) -> SqlManualImageResultUnitOfWork:
        self._tx = self._client.begin_transaction()
        self._tx.__enter__()
        conn = self._tx.connection
        position_repo = SqlPositionRepository(self._client, connection=conn)
        aisle_repo = SqlAisleRepository(self._client, connection=conn)
        inventory_repo = SqlInventoryRepository(self._client, connection=conn)
        self._tx_repos = ManualImageResultRepositories(
            position_repo=position_repo,
            product_record_repo=SqlProductRecordRepository(self._client, connection=conn),
            evidence_repo=SqlEvidenceRepository(self._client, connection=conn),
            manual_coverage_repo=SqlManualImageCoverageRepository(self._client, connection=conn),
            result_evidence_repo=SqlResultEvidenceRepository(self._client, connection=conn),
            review_repo=SqlReviewActionRepository(self._client, connection=conn),
            image_coverage_repo=SqlJobImageCoverageRepository(self._client, connection=conn),
        )
        # Lifecycle uses the SAME transactional connection — never AppContainer globals.
        self._lifecycle_sync = AisleReviewLifecycleSync(
            aisle_repo=aisle_repo,
            position_repo=position_repo,
            clock=self._clock,
            status_reconciler=InventoryStatusReconciler(
                inventory_repo=inventory_repo,
                aisle_repo=aisle_repo,
                clock=self._clock,
            ),
        )
        self._committed = False
        self._rolled_back = False
        self.timing_ms = {}
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is not None and not self._committed:
                self.rollback()
            elif not self._committed and exc_type is None:
                self.rollback()
        finally:
            if self._tx is not None:
                self._tx.close()
            self._tx = None
            self._tx_repos = None
            self._lifecycle_sync = None


def build_sql_manual_image_result_uow_factory(
    client: SqlServerClient,
    clock: Clock,
) -> Callable[[], SqlManualImageResultUnitOfWork]:
    def factory() -> SqlManualImageResultUnitOfWork:
        return SqlManualImageResultUnitOfWork(_client=client, _clock=clock)

    return factory
