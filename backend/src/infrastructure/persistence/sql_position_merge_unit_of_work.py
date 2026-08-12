"""SQL Server Unit of Work for atomic operator position merge."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, cast

from src.application.ports.clock import Clock
from src.application.services.aisle_review_lifecycle_sync import AisleReviewLifecycleSync
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.use_cases.positions.merge_positions import PositionMergeRepositories
from src.database.sqlserver import SqlServerClient
from src.infrastructure.database.sql_transaction import SqlServerTransaction, TransactionState
from src.infrastructure.repositories.sql_aisle_repository import SqlAisleRepository
from src.infrastructure.repositories.sql_inventory_repository import SqlInventoryRepository
from src.infrastructure.repositories.sql_position_repository import SqlPositionRepository
from src.infrastructure.repositories.sql_product_record_repository import SqlProductRecordRepository
from src.infrastructure.repositories.sql_review_action_repository import SqlReviewActionRepository

logger = logging.getLogger(__name__)


@dataclass
class _TxRepos:
    position_repo: SqlPositionRepository
    product_record_repo: SqlProductRecordRepository
    review_repo: SqlReviewActionRepository


@dataclass
class SqlPositionMergeUnitOfWork:
    _client: SqlServerClient
    _clock: Clock
    _inventory_id: str | None = field(default=None, init=False)
    _aisle_id: str | None = field(default=None, init=False)
    _tx: SqlServerTransaction | None = field(default=None, init=False)
    _tx_repos: _TxRepos | None = field(default=None, init=False)
    _lifecycle_sync: AisleReviewLifecycleSync | None = field(default=None, init=False)
    _committed: bool = field(default=False, init=False)
    _rolled_back: bool = field(default=False, init=False)

    @property
    def repositories(self) -> PositionMergeRepositories:
        if self._tx_repos is None:
            raise RuntimeError("SqlPositionMergeUnitOfWork is not active")
        return cast(PositionMergeRepositories, self._tx_repos)

    def bind_lifecycle_scope(self, *, inventory_id: str, aisle_id: str) -> None:
        self._inventory_id = inventory_id
        self._aisle_id = aisle_id

    def commit(self) -> None:
        if self._rolled_back:
            raise RuntimeError("Cannot commit after rollback")
        if self._tx is None or self._lifecycle_sync is None:
            raise RuntimeError("SqlPositionMergeUnitOfWork is not active")
        if self._inventory_id and self._aisle_id:
            self._lifecycle_sync.after_review_mutation(self._inventory_id, self._aisle_id)
        self._tx.commit()
        self._committed = True

    def rollback(self) -> None:
        if self._rolled_back:
            return
        if self._tx is not None and self._tx.state == TransactionState.ACTIVE:
            self._tx.rollback()
        self._committed = False
        self._rolled_back = True
        logger.warning("SqlPositionMergeUnitOfWork rolled back")

    def __enter__(self) -> SqlPositionMergeUnitOfWork:
        self._tx = self._client.begin_transaction()
        self._tx.__enter__()
        conn = self._tx.connection
        position_repo = SqlPositionRepository(self._client, connection=conn)
        aisle_repo = SqlAisleRepository(self._client, connection=conn)
        inventory_repo = SqlInventoryRepository(self._client, connection=conn)
        self._tx_repos = _TxRepos(
            position_repo=position_repo,
            product_record_repo=SqlProductRecordRepository(self._client, connection=conn),
            review_repo=SqlReviewActionRepository(self._client, connection=conn),
        )
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


def build_sql_position_merge_uow_factory(
    client: SqlServerClient,
    clock: Clock,
) -> Callable[[], SqlPositionMergeUnitOfWork]:
    def _factory() -> SqlPositionMergeUnitOfWork:
        return SqlPositionMergeUnitOfWork(_client=client, _clock=clock)

    return _factory
