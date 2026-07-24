"""SQL Server Unit of Work for atomic aisle revision apply (Phase 8 corrections)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable

from src.application.ports.aisle_revision_unit_of_work import AisleRevisionRepositories
from src.database.sqlserver import SqlServerClient
from src.infrastructure.database.sql_transaction import SqlServerTransaction, TransactionState
from src.infrastructure.repositories.sql_aisle_repository import SqlAisleRepository
from src.infrastructure.repositories.sql_aisle_revision_repository import (
    SqlAisleRevisionRepository,
)
from src.infrastructure.repositories.sql_authoritative_aisle_finalization_repository import (
    SqlAuthoritativeAisleFinalizationRepository,
)
from src.infrastructure.repositories.sql_authoritative_local_code_scan_repository import (
    SqlAuthoritativeLocalCodeScanRepository,
)
from src.infrastructure.repositories.sql_inventory_repository import SqlInventoryRepository
from src.infrastructure.repositories.sql_position_repository import SqlPositionRepository

logger = logging.getLogger(__name__)


@dataclass
class SqlAisleRevisionUnitOfWork:
    _client: SqlServerClient
    _tx: SqlServerTransaction | None = field(default=None, init=False)
    _tx_repos: AisleRevisionRepositories | None = field(default=None, init=False)
    _committed: bool = field(default=False, init=False)
    _rolled_back: bool = field(default=False, init=False)
    timing_ms: dict[str, float] = field(default_factory=dict, init=False)

    @property
    def repositories(self) -> AisleRevisionRepositories:
        if self._tx_repos is None:
            raise RuntimeError("SqlAisleRevisionUnitOfWork is not active")
        return self._tx_repos

    def commit(self) -> None:
        if self._rolled_back:
            raise RuntimeError("Cannot commit after rollback")
        if self._tx is None:
            raise RuntimeError("SqlAisleRevisionUnitOfWork is not active")
        started = time.perf_counter()
        self._tx.commit()
        self.timing_ms["transaction_commit_ms"] = (time.perf_counter() - started) * 1000.0
        self._committed = True
        logger.debug("SqlAisleRevisionUnitOfWork committed timing=%s", self.timing_ms)

    def rollback(self) -> None:
        if self._rolled_back:
            return
        if self._tx is not None and self._tx.state == TransactionState.ACTIVE:
            self._tx.rollback()
        self._committed = False
        self._rolled_back = True
        logger.warning("SqlAisleRevisionUnitOfWork rolled back")

    def __enter__(self) -> SqlAisleRevisionUnitOfWork:
        self._tx = self._client.begin_transaction()
        self._tx.__enter__()
        conn = self._tx.connection
        # All repositories share the single transactional connection — never AppContainer globals.
        self._tx_repos = AisleRevisionRepositories(
            revision_repo=SqlAisleRevisionRepository(self._client, connection=conn),
            authoritative_repo=SqlAuthoritativeLocalCodeScanRepository(
                self._client, connection=conn
            ),
            position_repo=SqlPositionRepository(self._client, connection=conn),
            finalization_repo=SqlAuthoritativeAisleFinalizationRepository(
                self._client, connection=conn
            ),
            aisle_repo=SqlAisleRepository(self._client, connection=conn),
            inventory_repo=SqlInventoryRepository(self._client, connection=conn),
        )
        self._committed = False
        self._rolled_back = False
        self.timing_ms = {}
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if not self._committed:
                self.rollback()
        finally:
            if self._tx is not None:
                self._tx.close()
            self._tx = None
            self._tx_repos = None


def build_sql_aisle_revision_uow_factory(
    client: SqlServerClient,
) -> Callable[[], SqlAisleRevisionUnitOfWork]:
    def factory() -> SqlAisleRevisionUnitOfWork:
        return SqlAisleRevisionUnitOfWork(_client=client)

    return factory
