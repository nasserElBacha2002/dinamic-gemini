"""SQL Server Unit of Work for job-result persistence."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.application.ports.job_result_unit_of_work import (
    JobResultRepositories,
    JobResultUnitOfWork,
)
from src.database.sqlserver import SqlServerClient
from src.infrastructure.database.sql_transaction import SqlServerTransaction
from src.infrastructure.repositories.sql_evidence_repository import SqlEvidenceRepository
from src.infrastructure.repositories.sql_final_count_repository import SqlFinalCountRepository
from src.infrastructure.repositories.sql_normalized_label_repository import (
    SqlNormalizedLabelRepository,
)
from src.infrastructure.repositories.sql_position_repository import SqlPositionRepository
from src.infrastructure.repositories.sql_product_record_repository import (
    SqlProductRecordRepository,
)
from src.infrastructure.repositories.sql_raw_label_repository import SqlRawLabelRepository

logger = logging.getLogger(__name__)


@dataclass
class SqlJobResultUnitOfWork:
    _client: SqlServerClient
    _base_repos: JobResultRepositories
    _tx: SqlServerTransaction | None = field(default=None, init=False)
    _tx_repos: JobResultRepositories | None = field(default=None, init=False)
    _committed: bool = field(default=False, init=False)

    @property
    def repositories(self) -> JobResultRepositories:
        if self._tx_repos is None:
            return self._base_repos
        return self._tx_repos

    @property
    def sql_cursor(self):
        if self._tx is None:
            raise RuntimeError("SqlJobResultUnitOfWork is not active")
        return self._tx.active_cursor

    def commit(self) -> None:
        if self._tx is not None:
            self._tx.commit()
        self._committed = True
        logger.debug("SqlJobResultUnitOfWork committed")

    def rollback(self) -> None:
        if self._tx is not None:
            self._tx.rollback()
        self._committed = False
        logger.warning("SqlJobResultUnitOfWork rolled back")

    def __enter__(self) -> SqlJobResultUnitOfWork:
        self._tx = SqlServerTransaction(self._client._connection_string).__enter__()
        conn = self._tx.connection
        self._tx_repos = JobResultRepositories(
            position_repo=SqlPositionRepository(self._client, connection=conn),
            product_record_repo=SqlProductRecordRepository(self._client, connection=conn),
            evidence_repo=SqlEvidenceRepository(self._client, connection=conn),
            raw_label_repo=SqlRawLabelRepository(self._client, connection=conn),
            normalized_label_repo=SqlNormalizedLabelRepository(self._client, connection=conn),
            final_count_repo=SqlFinalCountRepository(self._client, connection=conn),
        )
        self._committed = False
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._tx is not None:
            if exc_type is not None and not self._committed:
                self.rollback()
            self._tx.__exit__(exc_type, exc, tb)
        self._tx = None
        self._tx_repos = None


class SqlJobResultUnitOfWorkFactory:
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def __call__(self, repositories: JobResultRepositories) -> JobResultUnitOfWork:
        return SqlJobResultUnitOfWork(_client=self._client, _base_repos=repositories)
