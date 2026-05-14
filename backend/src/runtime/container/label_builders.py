"""Label-related SQL vs memory repository construction (Phase C3)."""

from __future__ import annotations

from src.application.ports.repositories import (
    FinalCountRepository,
    NormalizedLabelRepository,
    RawLabelRepository,
)
from src.database.sqlserver import SqlServerClient

from src.runtime.container.repository_builders import BuildSqlOrMemory


def build_raw_label_repository(
    build_repo: BuildSqlOrMemory[RawLabelRepository],
) -> RawLabelRepository:
    def _sql(client: SqlServerClient) -> RawLabelRepository:
        from src.infrastructure.repositories.sql_raw_label_repository import SqlRawLabelRepository

        return SqlRawLabelRepository(client)

    def _memory() -> RawLabelRepository:
        from src.infrastructure.repositories.memory_raw_label_repository import (
            MemoryRawLabelRepository,
        )

        return MemoryRawLabelRepository()

    return build_repo(
        backend_info_name="RawLabelRepository",
        sql_error_subject="raw_label repo",
        build_sql=_sql,
        build_memory=_memory,
    )


def build_normalized_label_repository(
    build_repo: BuildSqlOrMemory[NormalizedLabelRepository],
) -> NormalizedLabelRepository:
    def _sql(client: SqlServerClient) -> NormalizedLabelRepository:
        from src.infrastructure.repositories.sql_normalized_label_repository import (
            SqlNormalizedLabelRepository,
        )

        return SqlNormalizedLabelRepository(client)

    def _memory() -> NormalizedLabelRepository:
        from src.infrastructure.repositories.memory_normalized_label_repository import (
            MemoryNormalizedLabelRepository,
        )

        return MemoryNormalizedLabelRepository()

    return build_repo(
        backend_info_name="NormalizedLabelRepository",
        sql_error_subject="normalized_label repo",
        build_sql=_sql,
        build_memory=_memory,
    )


def build_final_count_repository(
    build_repo: BuildSqlOrMemory[FinalCountRepository],
) -> FinalCountRepository:
    def _sql(client: SqlServerClient) -> FinalCountRepository:
        from src.infrastructure.repositories.sql_final_count_repository import (
            SqlFinalCountRepository,
        )

        return SqlFinalCountRepository(client)

    def _memory() -> FinalCountRepository:
        from src.infrastructure.repositories.memory_final_count_repository import (
            MemoryFinalCountRepository,
        )

        return MemoryFinalCountRepository()

    return build_repo(
        backend_info_name="FinalCountRepository",
        sql_error_subject="final_count repo",
        build_sql=_sql,
        build_memory=_memory,
    )
