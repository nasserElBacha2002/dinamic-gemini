"""SQL Server Unit of Work for job-result persistence."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.application.ports.finalization_evidence_writer import FinalizationEvidenceWriter
from src.application.ports.job_result_scope_store import JobResultScopeStore
from src.application.ports.job_result_unit_of_work import (
    JobResultRepositories,
    JobResultUnitOfWork,
)
from src.database.sqlserver import SqlServerClient
from src.infrastructure.database.sql_transaction import SqlServerTransaction, TransactionState
from src.infrastructure.persistence.job_result_bundle_validation import (
    assert_sql_job_result_bundle,
)
from src.infrastructure.persistence.sql_finalization_evidence_writer import (
    SqlFinalizationEvidenceWriter,
)
from src.infrastructure.persistence.sql_finalization_stage_store import SqlFinalizationStageStore
from src.infrastructure.persistence.sql_job_result_scope_store import SqlJobResultScopeStore
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
from src.infrastructure.repositories.sql_result_evidence_repository import (
    SqlResultEvidenceRepository,
)

logger = logging.getLogger(__name__)


@dataclass
class SqlJobResultUnitOfWork:
    _client: SqlServerClient
    _base_repos: JobResultRepositories
    _tx: SqlServerTransaction | None = field(default=None, init=False)
    _tx_repos: JobResultRepositories | None = field(default=None, init=False)
    _scope_store: JobResultScopeStore | None = field(default=None, init=False)
    _evidence_writer: SqlFinalizationEvidenceWriter | None = field(default=None, init=False)
    _committed: bool = field(default=False, init=False)
    _rolled_back: bool = field(default=False, init=False)

    @property
    def repositories(self) -> JobResultRepositories:
        if self._tx_repos is None:
            return self._base_repos
        return self._tx_repos

    @property
    def scope_store(self) -> JobResultScopeStore:
        if self._scope_store is None:
            raise RuntimeError("SqlJobResultUnitOfWork is not active")
        return self._scope_store

    @property
    def finalization_evidence(self) -> FinalizationEvidenceWriter | None:
        return self._evidence_writer

    def commit(self) -> None:
        if self._rolled_back:
            raise RuntimeError("Cannot commit after rollback")
        if self._tx is None:
            raise RuntimeError("SqlJobResultUnitOfWork is not active")
        if self._evidence_writer is not None:
            self._evidence_writer.flush()
        self._tx.commit()
        self._committed = True
        logger.debug("SqlJobResultUnitOfWork committed")

    def rollback(self) -> None:
        if self._rolled_back:
            return
        if self._evidence_writer is not None:
            self._evidence_writer.discard()
        if self._tx is not None and self._tx.state == TransactionState.ACTIVE:
            self._tx.rollback()
        self._committed = False
        self._rolled_back = True
        logger.warning("SqlJobResultUnitOfWork rolled back")

    def __enter__(self) -> SqlJobResultUnitOfWork:
        self._tx = self._client.begin_transaction()
        self._tx.__enter__()
        conn = self._tx.connection
        self._tx_repos = JobResultRepositories(
            position_repo=SqlPositionRepository(self._client, connection=conn),
            product_record_repo=SqlProductRecordRepository(self._client, connection=conn),
            evidence_repo=SqlEvidenceRepository(self._client, connection=conn),
            raw_label_repo=SqlRawLabelRepository(self._client, connection=conn),
            normalized_label_repo=SqlNormalizedLabelRepository(self._client, connection=conn),
            final_count_repo=SqlFinalCountRepository(self._client, connection=conn),
            result_evidence_repo=SqlResultEvidenceRepository(self._client, connection=conn),
        )
        self._scope_store = SqlJobResultScopeStore(self._tx_repos, connection=conn)
        stage_store = SqlFinalizationStageStore(self._client, connection=conn)
        self._evidence_writer = SqlFinalizationEvidenceWriter(stage_store)
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
            self._scope_store = None
            self._evidence_writer = None


class SqlJobResultUnitOfWorkFactory:
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def __call__(self, repositories: JobResultRepositories) -> JobResultUnitOfWork:
        assert_sql_job_result_bundle(repositories)
        return SqlJobResultUnitOfWork(_client=self._client, _base_repos=repositories)
