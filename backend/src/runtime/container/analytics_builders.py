"""Analytics repository construction (Phase C3).

Memory analytics composes other repositories; callers supply getters to preserve lazy wiring.
"""

from __future__ import annotations

from collections.abc import Callable

from src.application.ports.analytics_repository import AnalyticsRepository
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    JobRepository,
    PositionRepository,
    ProductRecordRepository,
    ReviewActionRepository,
)
from src.database.sqlserver import SqlServerClient

from src.runtime.container.repository_builders import BuildSqlOrMemory


def build_analytics_repository(
    build_repo: BuildSqlOrMemory[AnalyticsRepository],
    *,
    get_inventory_repo: Callable[[], InventoryRepository],
    get_aisle_repo: Callable[[], AisleRepository],
    get_position_repo: Callable[[], PositionRepository],
    get_product_record_repo: Callable[[], ProductRecordRepository],
    get_review_action_repo: Callable[[], ReviewActionRepository],
    get_job_repo: Callable[[], JobRepository],
) -> AnalyticsRepository:
    def _sql(client: SqlServerClient) -> AnalyticsRepository:
        from src.infrastructure.repositories.sql_analytics_repository import SqlAnalyticsRepository

        return SqlAnalyticsRepository(client)

    def _memory() -> AnalyticsRepository:
        from src.infrastructure.repositories.memory_analytics_repository import (
            MemoryAnalyticsRepository,
        )

        return MemoryAnalyticsRepository(
            get_inventory_repo(),
            get_aisle_repo(),
            get_position_repo(),
            get_product_record_repo(),
            get_review_action_repo(),
            get_job_repo(),
        )

    return build_repo(
        backend_info_name="AnalyticsRepository",
        sql_error_subject="analytics repo",
        build_sql=_sql,
        build_memory=_memory,
    )
