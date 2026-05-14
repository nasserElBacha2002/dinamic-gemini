"""SQL vs memory repository construction for core and client/supplier domains (Phase C3).

Callers pass :meth:`~src.runtime.app_container.AppContainer._build_sql_repository_or_memory`
bound as ``build_repo``; this module does not resolve backend mode or cache instances.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, TypeVar

from src.application.ports.repositories import (
    AisleRepository,
    ClientRepository,
    ClientSupplierRepository,
    EvidenceRepository,
    InventoryRepository,
    JobRepository,
    PositionRepository,
    ProductRecordRepository,
    ReviewActionRepository,
    SourceAssetRepository,
    SupplierPromptConfigRepository,
    SupplierReferenceImageRepository,
)
from src.database.sqlserver import SqlServerClient

_RepoT = TypeVar("_RepoT")


class BuildSqlOrMemory(Protocol[_RepoT]):
    """Shape of :meth:`AppContainer._build_sql_repository_or_memory` (bound method, no ``self``)."""

    def __call__(
        self,
        *,
        backend_info_name: str,
        sql_error_subject: str,
        build_sql: Callable[[SqlServerClient], _RepoT],
        build_memory: Callable[[], _RepoT],
    ) -> _RepoT: ...


def build_inventory_repository(
    build_repo: BuildSqlOrMemory[InventoryRepository],
) -> InventoryRepository:
    def _sql(client: SqlServerClient) -> InventoryRepository:
        from src.infrastructure.repositories.sql_inventory_repository import SqlInventoryRepository

        return SqlInventoryRepository(client)

    def _memory() -> InventoryRepository:
        from src.infrastructure.repositories.memory_inventory_repository import (
            MemoryInventoryRepository,
        )

        return MemoryInventoryRepository()

    return build_repo(
        backend_info_name="InventoryRepository",
        sql_error_subject="repo",
        build_sql=_sql,
        build_memory=_memory,
    )


def build_client_repository(build_repo: BuildSqlOrMemory[ClientRepository]) -> ClientRepository:
    def _sql(client: SqlServerClient) -> ClientRepository:
        from src.infrastructure.repositories.sql_client_repository import SqlClientRepository

        return SqlClientRepository(client)

    def _memory() -> ClientRepository:
        from src.infrastructure.repositories.memory_client_repository import MemoryClientRepository

        return MemoryClientRepository()

    return build_repo(
        backend_info_name="ClientRepository",
        sql_error_subject="client repo",
        build_sql=_sql,
        build_memory=_memory,
    )


def build_client_supplier_repository(
    build_repo: BuildSqlOrMemory[ClientSupplierRepository],
) -> ClientSupplierRepository:
    def _sql(client: SqlServerClient) -> ClientSupplierRepository:
        from src.infrastructure.repositories.sql_client_supplier_repository import (
            SqlClientSupplierRepository,
        )

        return SqlClientSupplierRepository(client)

    def _memory() -> ClientSupplierRepository:
        from src.infrastructure.repositories.memory_client_supplier_repository import (
            MemoryClientSupplierRepository,
        )

        return MemoryClientSupplierRepository()

    return build_repo(
        backend_info_name="ClientSupplierRepository",
        sql_error_subject="client_supplier repo",
        build_sql=_sql,
        build_memory=_memory,
    )


def build_aisle_repository(build_repo: BuildSqlOrMemory[AisleRepository]) -> AisleRepository:
    def _sql(client: SqlServerClient) -> AisleRepository:
        from src.infrastructure.repositories.sql_aisle_repository import SqlAisleRepository

        return SqlAisleRepository(client)

    def _memory() -> AisleRepository:
        from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository

        return MemoryAisleRepository()

    return build_repo(
        backend_info_name="AisleRepository",
        sql_error_subject="aisle repo",
        build_sql=_sql,
        build_memory=_memory,
    )


def build_job_repository(build_repo: BuildSqlOrMemory[JobRepository]) -> JobRepository:
    def _sql(client: SqlServerClient) -> JobRepository:
        from src.infrastructure.repositories.sql_job_repository import SqlJobRepository

        return SqlJobRepository(client)

    def _memory() -> JobRepository:
        from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository

        return MemoryJobRepository()

    return build_repo(
        backend_info_name="JobRepository",
        sql_error_subject="job repo",
        build_sql=_sql,
        build_memory=_memory,
    )


def build_source_asset_repository(
    build_repo: BuildSqlOrMemory[SourceAssetRepository],
) -> SourceAssetRepository:
    def _sql(client: SqlServerClient) -> SourceAssetRepository:
        from src.infrastructure.repositories.sql_source_asset_repository import (
            SqlSourceAssetRepository,
        )

        return SqlSourceAssetRepository(client)

    def _memory() -> SourceAssetRepository:
        from src.infrastructure.repositories.memory_source_asset_repository import (
            MemorySourceAssetRepository,
        )

        return MemorySourceAssetRepository()

    return build_repo(
        backend_info_name="SourceAssetRepository",
        sql_error_subject="source_asset repo",
        build_sql=_sql,
        build_memory=_memory,
    )


def build_supplier_reference_image_repository(
    build_repo: BuildSqlOrMemory[SupplierReferenceImageRepository],
) -> SupplierReferenceImageRepository:
    def _sql(client: SqlServerClient) -> SupplierReferenceImageRepository:
        from src.infrastructure.repositories.sql_supplier_reference_image_repository import (
            SqlSupplierReferenceImageRepository,
        )

        return SqlSupplierReferenceImageRepository(client)

    def _memory() -> SupplierReferenceImageRepository:
        from src.infrastructure.repositories.memory_supplier_reference_image_repository import (
            MemorySupplierReferenceImageRepository,
        )

        return MemorySupplierReferenceImageRepository()

    return build_repo(
        backend_info_name="SupplierReferenceImageRepository",
        sql_error_subject="supplier_reference_image repo",
        build_sql=_sql,
        build_memory=_memory,
    )


def build_supplier_prompt_config_repository(
    build_repo: BuildSqlOrMemory[SupplierPromptConfigRepository],
) -> SupplierPromptConfigRepository:
    def _sql(client: SqlServerClient) -> SupplierPromptConfigRepository:
        from src.infrastructure.repositories.sql_supplier_prompt_config_repository import (
            SqlSupplierPromptConfigRepository,
        )

        return SqlSupplierPromptConfigRepository(client)

    def _memory() -> SupplierPromptConfigRepository:
        from src.infrastructure.repositories.memory_supplier_prompt_config_repository import (
            MemorySupplierPromptConfigRepository,
        )

        return MemorySupplierPromptConfigRepository()

    return build_repo(
        backend_info_name="SupplierPromptConfigRepository",
        sql_error_subject="supplier_prompt_config repo",
        build_sql=_sql,
        build_memory=_memory,
    )


def build_position_repository(
    build_repo: BuildSqlOrMemory[PositionRepository],
) -> PositionRepository:
    def _sql(client: SqlServerClient) -> PositionRepository:
        from src.infrastructure.repositories.sql_position_repository import SqlPositionRepository

        return SqlPositionRepository(client)

    def _memory() -> PositionRepository:
        from src.infrastructure.repositories.memory_position_repository import (
            MemoryPositionRepository,
        )

        return MemoryPositionRepository()

    return build_repo(
        backend_info_name="PositionRepository",
        sql_error_subject="position repo",
        build_sql=_sql,
        build_memory=_memory,
    )


def build_product_record_repository(
    build_repo: BuildSqlOrMemory[ProductRecordRepository],
) -> ProductRecordRepository:
    def _sql(client: SqlServerClient) -> ProductRecordRepository:
        from src.infrastructure.repositories.sql_product_record_repository import (
            SqlProductRecordRepository,
        )

        return SqlProductRecordRepository(client)

    def _memory() -> ProductRecordRepository:
        from src.infrastructure.repositories.memory_product_record_repository import (
            MemoryProductRecordRepository,
        )

        return MemoryProductRecordRepository()

    return build_repo(
        backend_info_name="ProductRecordRepository",
        sql_error_subject="product_record repo",
        build_sql=_sql,
        build_memory=_memory,
    )


def build_evidence_repository(
    build_repo: BuildSqlOrMemory[EvidenceRepository],
) -> EvidenceRepository:
    def _sql(client: SqlServerClient) -> EvidenceRepository:
        from src.infrastructure.repositories.sql_evidence_repository import SqlEvidenceRepository

        return SqlEvidenceRepository(client)

    def _memory() -> EvidenceRepository:
        from src.infrastructure.repositories.memory_evidence_repository import (
            MemoryEvidenceRepository,
        )

        return MemoryEvidenceRepository()

    return build_repo(
        backend_info_name="EvidenceRepository",
        sql_error_subject="evidence repo",
        build_sql=_sql,
        build_memory=_memory,
    )


def build_review_action_repository(
    build_repo: BuildSqlOrMemory[ReviewActionRepository],
) -> ReviewActionRepository:
    def _sql(client: SqlServerClient) -> ReviewActionRepository:
        from src.infrastructure.repositories.sql_review_action_repository import (
            SqlReviewActionRepository,
        )

        return SqlReviewActionRepository(client)

    def _memory() -> ReviewActionRepository:
        from src.infrastructure.repositories.memory_review_action_repository import (
            MemoryReviewActionRepository,
        )

        return MemoryReviewActionRepository()

    return build_repo(
        backend_info_name="ReviewActionRepository",
        sql_error_subject="review_action repo",
        build_sql=_sql,
        build_memory=_memory,
    )
