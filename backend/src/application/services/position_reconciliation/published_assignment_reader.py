"""Batch reader for published Phase 4 assignments (Phase 5 enrichment SoT)."""

from __future__ import annotations

from collections.abc import Sequence

from src.application.ports.position_reconciliation_repository import (
    PositionReconciliationRepository,
)
from src.application.services.position_reconciliation.published_assignment_read_model import (
    PositionReadAvailability,
    PublishedPositionAssignmentView,
    feature_disabled_view,
    map_assignment_to_view,
    no_reconciliation_view,
)
from src.domain.position_reconciliation.entities import ReconciliationStatus


class PublishedPositionAssignmentReader:
    """Load active published assignments for a job in one batch (no N+1)."""

    def __init__(
        self,
        *,
        reconciliation_repo: PositionReconciliationRepository,
        enrichment_enabled: bool = True,
    ) -> None:
        self._repo = reconciliation_repo
        self._enabled = enrichment_enabled

    def load_for_job(
        self,
        job_id: str,
        *,
        result_ids: Sequence[str] | None = None,
    ) -> dict[str, PublishedPositionAssignmentView]:
        """Return views keyed by result_id.

        When ``result_ids`` is provided, every id is present in the map.
        Missing assignment rows become explicit UNASSIGNED (or NO_RECONCILIATION /
        FEATURE_DISABLED when applicable). Never invents a position name.
        """
        wanted = [rid for rid in (result_ids or ()) if rid]
        wanted_set = set(wanted)

        if not self._enabled:
            return {rid: feature_disabled_view(rid) for rid in wanted}

        published = self._repo.get_published_by_job(job_id)
        if published is None:
            if wanted:
                return {rid: no_reconciliation_view(rid) for rid in wanted}
            return {}

        assignments = self._repo.list_active_assignments(job_id)
        by_result: dict[str, PublishedPositionAssignmentView] = {}
        for row in assignments:
            if wanted_set and row.result_id not in wanted_set:
                continue
            by_result[row.result_id] = map_assignment_to_view(
                row,
                reconciliation_status=published.status,
            )

        status_value = (
            published.status.value
            if isinstance(published.status, ReconciliationStatus)
            else str(published.status)
        )
        for rid in wanted:
            if rid in by_result:
                continue
            by_result[rid] = PublishedPositionAssignmentView(
                result_id=rid,
                availability=(
                    PositionReadAvailability.RECONCILIATION_STALE
                    if status_value == ReconciliationStatus.STALE.value
                    else PositionReadAvailability.INCONSISTENT
                ),
                position=None,
                assignment_status="ASSIGNMENT_MISSING_FROM_PUBLISHED_REVISION",
                assignment_reason="NO_ASSIGNMENT_ROW",
                assignment_source=None,
                reconciliation_id=published.id,
                reconciliation_version=published.reconciliation_version,
                reconciliation_status=status_value,
                sequence_number=None,
                source_asset_id=None,
                assigned_at=None,
            )
        return by_result
