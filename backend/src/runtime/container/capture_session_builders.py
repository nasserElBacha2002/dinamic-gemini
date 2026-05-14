"""Capture session repository construction (Phase C3)."""

from __future__ import annotations

from collections.abc import Callable

from src.application.ports.capture_repositories import (
    CaptureSessionConfirmIdempotencyRepository,
    CaptureSessionGroupRepository,
    CaptureSessionItemRepository,
    CaptureSessionRepository,
)
from src.database.sqlserver import SqlServerClient

from src.runtime.container.repository_builders import BuildSqlOrMemory


def build_capture_session_repository(
    build_repo: BuildSqlOrMemory[CaptureSessionRepository],
) -> CaptureSessionRepository:
    def _sql(client: SqlServerClient) -> CaptureSessionRepository:
        from src.infrastructure.repositories.sql_capture_session_repository import SqlCaptureSessionRepository

        return SqlCaptureSessionRepository(client)

    def _memory() -> CaptureSessionRepository:
        from src.infrastructure.repositories.memory_capture_session_repository import (
            MemoryCaptureSessionRepository,
        )

        return MemoryCaptureSessionRepository()

    return build_repo(
        backend_info_name="CaptureSessionRepository",
        sql_error_subject="capture_session repo",
        build_sql=_sql,
        build_memory=_memory,
    )


def build_capture_session_item_repository(
    build_repo: BuildSqlOrMemory[CaptureSessionItemRepository],
) -> CaptureSessionItemRepository:
    def _sql(client: SqlServerClient) -> CaptureSessionItemRepository:
        from src.infrastructure.repositories.sql_capture_session_item_repository import (
            SqlCaptureSessionItemRepository,
        )

        return SqlCaptureSessionItemRepository(client)

    def _memory() -> CaptureSessionItemRepository:
        from src.infrastructure.repositories.memory_capture_session_item_repository import (
            MemoryCaptureSessionItemRepository,
        )

        return MemoryCaptureSessionItemRepository()

    return build_repo(
        backend_info_name="CaptureSessionItemRepository",
        sql_error_subject="capture_session_item repo",
        build_sql=_sql,
        build_memory=_memory,
    )


def build_capture_session_group_repository(
    build_repo: BuildSqlOrMemory[CaptureSessionGroupRepository],
    *,
    get_capture_session_item_repo: Callable[[], CaptureSessionItemRepository],
) -> CaptureSessionGroupRepository:
    def _sql(client: SqlServerClient) -> CaptureSessionGroupRepository:
        from src.infrastructure.repositories.sql_capture_session_group_repository import (
            SqlCaptureSessionGroupRepository,
        )

        return SqlCaptureSessionGroupRepository(client)

    def _memory() -> CaptureSessionGroupRepository:
        from src.infrastructure.repositories.memory_capture_session_group_repository import (
            MemoryCaptureSessionGroupRepository,
        )

        return MemoryCaptureSessionGroupRepository(get_capture_session_item_repo())

    return build_repo(
        backend_info_name="CaptureSessionGroupRepository",
        sql_error_subject="capture_session_group repo",
        build_sql=_sql,
        build_memory=_memory,
    )


def build_capture_session_confirm_repository(
    build_repo: BuildSqlOrMemory[CaptureSessionConfirmIdempotencyRepository],
) -> CaptureSessionConfirmIdempotencyRepository:
    def _sql(client: SqlServerClient) -> CaptureSessionConfirmIdempotencyRepository:
        from src.infrastructure.repositories.sql_capture_session_confirm_idempotency_repository import (
            SqlCaptureSessionConfirmIdempotencyRepository,
        )

        return SqlCaptureSessionConfirmIdempotencyRepository(client)

    def _memory() -> CaptureSessionConfirmIdempotencyRepository:
        from src.infrastructure.repositories.memory_capture_session_confirm_idempotency_repository import (
            MemoryCaptureSessionConfirmIdempotencyRepository,
        )

        return MemoryCaptureSessionConfirmIdempotencyRepository()

    return build_repo(
        backend_info_name="CaptureSessionConfirmIdempotencyRepository",
        sql_error_subject="capture_session_confirm repo",
        build_sql=_sql,
        build_memory=_memory,
    )
