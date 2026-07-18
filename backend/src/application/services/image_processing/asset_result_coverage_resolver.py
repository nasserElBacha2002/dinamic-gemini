"""Resolve per-asset coverage of an AISLE_BATCH legacy run from persisted evidence (Phase 2).

The legacy hybrid pipeline runs once per aisle and produces ``result_evidence`` /
``evidence`` rows keyed by ``source_asset_id`` (when the provider/consolidation could link a
detected entity back to the originating photo). This resolver answers, for one
``(job_id, asset_id)``, whether that linkage exists — without ever inferring "no result" from
a single missing signal when other signals are ambiguous.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from enum import Enum

from src.application.ports.repositories import (
    EvidenceRepository,
    PositionRepository,
    ResultEvidenceRepository,
)
from src.domain.result_evidence.entities import ResultEvidenceRecord

logger = logging.getLogger(__name__)


class AssetResultCoverageStatus(str, Enum):
    RESOLVED = "RESOLVED"
    UNRECOGNIZED = "UNRECOGNIZED"
    PENDING_RECONCILIATION = "PENDING_RECONCILIATION"


class AssetResultCoverageResolver:
    """Coverage decision for one asset within one job, built from three signals in order:

    1. ``result_evidence.source_asset_id`` (Phase 4.6 structural traceability rows for the job).
    2. ``evidence.source_asset_id`` linked to a ``position`` that belongs to the job (aisle
       positions scoped by ``job_id``).
    3. Absence of *any* traceability signal for the whole job (batch may not have synced
       evidence yet, or the legacy pipeline predates evidence rows) — ambiguous, not "no result".

    Never returns ``UNRECOGNIZED`` solely because ``result_evidence`` is missing for this asset
    when other links exist for the job; an inconclusive combination returns
    ``PENDING_RECONCILIATION`` instead (maps to ``PENDING_MANUAL_REVIEW`` on the asset state).
    """

    def __init__(
        self,
        *,
        result_evidence_repo: ResultEvidenceRepository,
        evidence_repo: EvidenceRepository,
        position_repo: PositionRepository,
        positions_page_size: int = 2000,
    ) -> None:
        self._result_evidence_repo = result_evidence_repo
        self._evidence_repo = evidence_repo
        self._position_repo = position_repo
        # Configurable cap (default aligned with ``V3_POSITIONS_AISLE_RAW_CAP``) — the job-scoped
        # position list must not silently truncate coverage evidence below the aisle's true size.
        self._positions_page_size = positions_page_size

    def resolve(
        self,
        *,
        job_id: str,
        aisle_id: str,
        asset_id: str,
    ) -> AssetResultCoverageStatus:
        result_evidence_rows = self._result_evidence_repo.list_by_job_id(job_id)
        matching = [
            r for r in result_evidence_rows if (r.source_asset_id or "").strip() == asset_id
        ]
        if matching:
            return self._resolve_from_result_evidence(matching, asset_id=asset_id)

        positions = self._position_repo.list_by_aisle(
            aisle_id, job_id=job_id, page_size=self._positions_page_size
        )
        if self._linked_via_position_evidence(positions, asset_id=asset_id):
            return AssetResultCoverageStatus.RESOLVED

        if not result_evidence_rows and not positions:
            logger.info(
                "asset_coverage.no_signal_yet job_id=%s aisle_id=%s asset_id=%s",
                job_id,
                aisle_id,
                asset_id,
            )
            return AssetResultCoverageStatus.PENDING_RECONCILIATION

        return AssetResultCoverageStatus.UNRECOGNIZED

    def _resolve_from_result_evidence(
        self, matching: Sequence[ResultEvidenceRecord], *, asset_id: str
    ) -> AssetResultCoverageStatus:
        if any(r.has_valid_evidence for r in matching):
            return AssetResultCoverageStatus.RESOLVED
        logger.info(
            "asset_coverage.result_evidence_without_valid_flag asset_id=%s count=%s",
            asset_id,
            len(matching),
        )
        return AssetResultCoverageStatus.PENDING_RECONCILIATION

    def _linked_via_position_evidence(self, positions: Sequence[object], *, asset_id: str) -> bool:
        for position in positions:
            position_id = getattr(position, "id", None)
            if not position_id:
                continue
            for evidence in self._evidence_repo.list_by_entity("position", position_id):
                if (evidence.source_asset_id or "").strip() == asset_id:
                    return True
        return False
