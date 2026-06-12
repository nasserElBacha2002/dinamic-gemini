"""Delete existing rows for one job scope before replacement (Phase 2 Part 2)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from src.application.ports.job_result_unit_of_work import JobResultRepositories
from src.application.ports.repositories import (
    EvidenceRepository,
    ProductRecordRepository,
)
from src.infrastructure.repositories.memory_final_count_repository import MemoryFinalCountRepository
from src.infrastructure.repositories.memory_normalized_label_repository import (
    MemoryNormalizedLabelRepository,
)
from src.infrastructure.repositories.memory_raw_label_repository import MemoryRawLabelRepository

logger = logging.getLogger(__name__)

AfterDeleteHook = Callable[[], None]


@dataclass(frozen=True)
class JobScopeRowCounts:
    positions: int
    products: int
    evidence: int
    raw_labels: int
    normalized_labels: int
    final_counts: int


class JobResultScopeCleaner:
    """FK-safe delete of one ``(inventory_id, aisle_id, job_id)`` result snapshot."""

    def __init__(self, *, after_delete_hook: AfterDeleteHook | None = None) -> None:
        self._after_delete_hook = after_delete_hook

    def count_scope(
        self,
        repos: JobResultRepositories,
        *,
        inventory_id: str,
        aisle_id: str,
        job_id: str,
    ) -> JobScopeRowCounts:
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
        repos: JobResultRepositories,
        *,
        inventory_id: str,
        aisle_id: str,
        job_id: str,
        sql_cursor: Any | None = None,
    ) -> JobScopeRowCounts:
        """Remove prior snapshot for ``job_id`` only. Returns pre-delete counts."""
        before = self.count_scope(
            repos, inventory_id=inventory_id, aisle_id=aisle_id, job_id=job_id
        )
        if sql_cursor is not None:
            _delete_sql_job_scope(
                sql_cursor,
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                job_id=job_id,
            )
        else:
            _delete_memory_job_scope(
                repos,
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                job_id=job_id,
            )
        logger.info(
            "job_result_replacement deleted prior scope inventory_id=%s aisle_id=%s job_id=%s "
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
        if self._after_delete_hook is not None:
            self._after_delete_hook()
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
        rows.extend(evidence_repo.list_by_entity("position", pos.id))
    return rows


def _delete_memory_job_scope(
    repos: JobResultRepositories,
    *,
    inventory_id: str,
    aisle_id: str,
    job_id: str,
) -> None:
    positions = list(repos.position_repo.list_by_aisle(aisle_id, job_id=job_id))
    for pos in positions:
        for prod in repos.product_record_repo.list_by_position(pos.id):
            _delete_from_store(repos.product_record_repo, prod.id)
        for ev in repos.evidence_repo.list_by_entity("position", pos.id):
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


def _delete_from_store(repo: Any, entity_id: str) -> None:
    store = getattr(repo, "_store", None)
    if store is not None and entity_id in store:
        del store[entity_id]


def _delete_sql_job_scope(
    cur: Any,
    *,
    inventory_id: str,
    aisle_id: str,
    job_id: str,
) -> None:
    cur.execute(
        "DELETE FROM final_count_records WHERE inventory_id = ? AND aisle_id = ? AND job_id = ?",
        (inventory_id, aisle_id, job_id),
    )
    cur.execute(
        "DELETE FROM normalized_labels WHERE inventory_id = ? AND aisle_id = ? AND job_id = ?",
        (inventory_id, aisle_id, job_id),
    )
    cur.execute(
        "DELETE FROM raw_labels WHERE inventory_id = ? AND aisle_id = ? AND job_id = ?",
        (inventory_id, aisle_id, job_id),
    )
    cur.execute(
        "DELETE FROM evidences WHERE entity_id IN "
        "(SELECT id FROM positions WHERE aisle_id = ? AND job_id = ?)",
        (aisle_id, job_id),
    )
    cur.execute(
        "DELETE FROM product_records WHERE position_id IN "
        "(SELECT id FROM positions WHERE aisle_id = ? AND job_id = ?)",
        (aisle_id, job_id),
    )
    cur.execute(
        "DELETE FROM positions WHERE aisle_id = ? AND job_id = ?",
        (aisle_id, job_id),
    )
