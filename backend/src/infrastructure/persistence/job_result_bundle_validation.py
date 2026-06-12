"""Validate JobResultRepositories bundles match UoW factory persistence backend."""

from __future__ import annotations

from src.application.ports.job_result_unit_of_work import JobResultRepositories


def _is_memory_compatible(repo: object) -> bool:
    if getattr(repo, "_store", None) is not None:
        return True
    inner = getattr(repo, "_inner", None)
    if inner is not None:
        return _is_memory_compatible(inner)
    module = type(repo).__module__
    return module.startswith("src.infrastructure.repositories.memory_")


def _is_sql_compatible(repo: object) -> bool:
    module = type(repo).__module__
    return module.startswith("src.infrastructure.repositories.sql_")


def assert_memory_job_result_bundle(repositories: JobResultRepositories) -> None:
    fields = (
        repositories.position_repo,
        repositories.product_record_repo,
        repositories.evidence_repo,
        repositories.raw_label_repo,
        repositories.normalized_label_repo,
        repositories.final_count_repo,
    )
    for repo in fields:
        if not _is_memory_compatible(repo):
            raise ValueError(
                "MemoryJobResultUnitOfWorkFactory requires memory-compatible repositories; "
                f"got {type(repo).__name__}"
            )


def assert_sql_job_result_bundle(repositories: JobResultRepositories) -> None:
    fields = (
        repositories.position_repo,
        repositories.product_record_repo,
        repositories.evidence_repo,
        repositories.raw_label_repo,
        repositories.normalized_label_repo,
        repositories.final_count_repo,
    )
    for repo in fields:
        if not _is_sql_compatible(repo):
            raise ValueError(
                "SqlJobResultUnitOfWorkFactory requires SQL repository bundle; "
                f"got {type(repo).__name__}"
            )
