"""SQL Server job-scope delete/count for transactional replacement."""

from __future__ import annotations

import logging
from typing import Any

from src.application.ports.job_result_scope_store import JobResultScopeStore, JobScopeRowCounts
from src.application.ports.job_result_unit_of_work import JobResultRepositories
from src.application.ports.repositories import (
    EvidenceRepository,
    ProductRecordRepository,
)

logger = logging.getLogger(__name__)
_POSITION_ENTITY_TYPE = "position"


class SqlJobResultScopeStore(JobResultScopeStore):
    def __init__(
        self,
        repositories: JobResultRepositories,
        *,
        connection: Any,
    ) -> None:
        self._repos = repositories
        self._connection = connection

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
        result_evidence = list(repos.result_evidence_repo.list_by_job_id(job_id))
        return JobScopeRowCounts(
            positions=len(positions),
            products=len(products),
            evidence=len(evidence),
            raw_labels=len(raw_labels),
            normalized_labels=len(norm_labels),
            final_counts=len(final_counts),
            result_evidence=len(result_evidence),
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
        cur = self._connection.cursor()
        try:
            _delete_sql_job_scope(
                cur,
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                job_id=job_id,
            )
        finally:
            cur.close()
        logger.info(
            "sql_job_result_scope deleted inventory_id=%s aisle_id=%s job_id=%s "
            "positions=%d products=%d evidence=%d raw=%d normalized=%d final=%d result_evidence=%d",
            inventory_id,
            aisle_id,
            job_id,
            before.positions,
            before.products,
            before.evidence,
            before.raw_labels,
            before.normalized_labels,
            before.final_counts,
            before.result_evidence,
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


def _delete_sql_job_scope(
    cur: Any,
    *,
    inventory_id: str,
    aisle_id: str,
    job_id: str,
) -> None:
    cur.execute(
        """
        DELETE FROM result_evidence
        WHERE inventory_id = ? AND aisle_id = ? AND job_id = ?
        """,
        (inventory_id, aisle_id, job_id),
    )
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
        "DELETE FROM evidences WHERE entity_type = ? AND entity_id IN "
        "(SELECT id FROM positions WHERE aisle_id = ? AND job_id = ?)",
        (_POSITION_ENTITY_TYPE, aisle_id, job_id),
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
