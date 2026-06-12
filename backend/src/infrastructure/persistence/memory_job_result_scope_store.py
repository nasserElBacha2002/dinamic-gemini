"""In-memory job-scope delete/count for transactional replacement."""

from __future__ import annotations

import logging
from typing import Any

from src.application.ports.job_result_scope_store import JobResultScopeStore, JobScopeRowCounts
from src.application.ports.job_result_unit_of_work import JobResultRepositories
from src.application.ports.repositories import EvidenceRepository, ProductRecordRepository
from src.infrastructure.repositories.memory_final_count_repository import MemoryFinalCountRepository
from src.infrastructure.repositories.memory_normalized_label_repository import (
    MemoryNormalizedLabelRepository,
)
from src.infrastructure.repositories.memory_raw_label_repository import MemoryRawLabelRepository

logger = logging.getLogger(__name__)
_POSITION_ENTITY_TYPE = "position"


class MemoryJobResultScopeStore(JobResultScopeStore):
    def __init__(self, repositories: JobResultRepositories) -> None:
        self._repos = repositories

    def count_scope(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        job_id: str,
    ) -> JobScopeRowCounts:
        repos = self._repos
        positions = list(repos.position_repo.list_by_aisle(aisle_id, job_id=job_id))
        products = _products_for_positions(repos.product_record_repo, positions)
        evidence = _evidence_for_positions(repos.evidence_repo, positions)
        raw_labels = list(
            repos.raw_label_repo.list_for_scope(inventory_id, aisle_id, job_id=job_id)
        )
        norm_labels = list(
            repos.normalized_label_repo.list_for_scope(inventory_id, aisle_id, job_id=job_id)
        )
        final_counts = list(
            repos.final_count_repo.list_for_scope(inventory_id, aisle_id, job_id=job_id)
        )
        return JobScopeRowCounts(
            positions=len(positions),
            products=len(products),
            evidence=len(evidence),
            raw_labels=len(raw_labels),
            normalized_labels=len(norm_labels),
            final_counts=len(final_counts),
        )

    def delete_scope(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        job_id: str,
    ) -> JobScopeRowCounts:
        before = self.count_scope(
            inventory_id=inventory_id, aisle_id=aisle_id, job_id=job_id
        )
        repos = self._repos
        positions = list(repos.position_repo.list_by_aisle(aisle_id, job_id=job_id))
        for pos in positions:
            for prod in repos.product_record_repo.list_by_position(pos.id):
                _delete_from_store(repos.product_record_repo, prod.id)
            for ev in repos.evidence_repo.list_by_entity(_POSITION_ENTITY_TYPE, pos.id):
                _delete_from_store(repos.evidence_repo, ev.id)
            _delete_from_store(repos.position_repo, pos.id)

        if isinstance(repos.raw_label_repo, MemoryRawLabelRepository):
            to_remove = [
                lid
                for lid, lb in repos.raw_label_repo._store.items()
                if lb.inventory_id == inventory_id
                and lb.aisle_id == aisle_id
                and lb.job_id == job_id
            ]
            for lid in to_remove:
                del repos.raw_label_repo._store[lid]

        if isinstance(repos.normalized_label_repo, MemoryNormalizedLabelRepository):
            repos.normalized_label_repo.replace_for_scope(
                inventory_id, aisle_id, job_id=job_id
            )
        if isinstance(repos.final_count_repo, MemoryFinalCountRepository):
            repos.final_count_repo.replace_for_scope(inventory_id, aisle_id, job_id=job_id)

        logger.info(
            "memory_job_result_scope deleted inventory_id=%s aisle_id=%s job_id=%s "
            "positions=%d products=%d evidence=%d raw=%d normalized=%d final=%d",
            inventory_id,
            aisle_id,
            job_id,
            before.positions,
            before.products,
            before.evidence,
            before.raw_labels,
            before.normalized_labels,
            before.final_counts,
        )
        return before


def _products_for_positions(
    product_repo: ProductRecordRepository, positions: list
) -> list:
    rows: list = []
    for pos in positions:
        rows.extend(product_repo.list_by_position(pos.id))
    return rows


def _evidence_for_positions(evidence_repo: EvidenceRepository, positions: list) -> list:
    rows: list = []
    for pos in positions:
        rows.extend(evidence_repo.list_by_entity(_POSITION_ENTITY_TYPE, pos.id))
    return rows


def _delete_from_store(repo: Any, entity_id: str) -> None:
    store = getattr(repo, "_store", None)
    if store is not None and entity_id in store:
        del store[entity_id]
