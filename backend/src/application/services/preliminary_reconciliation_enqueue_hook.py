"""Best-effort enqueue of preliminary reconciliations after job terminalization."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def try_enqueue_preliminary_reconciliations(*, job_id: str, aisle_id: str, inventory_id: str) -> None:
    """Server-side trigger — independent of mobile UI flags."""
    try:
        from src.config import load_settings

        settings = load_settings()
        if not getattr(settings, "server_preliminary_reconciliation_enabled", False):
            return
        from src.application.use_cases.aisles.reconcile_preliminary_detections import (
            EnqueuePreliminaryReconciliationsUseCase,
            EnqueueReconciliationCommand,
        )
        from src.runtime.v3_deps import get_app_container

        c = get_app_container()
        uc = EnqueuePreliminaryReconciliationsUseCase(
            aisle_repo=c.get_aisle_repo(),
            job_repo=c.get_job_repo(),
            preliminary_repo=c.get_mobile_preliminary_detection_repo(),
            reconciliation_repo=c.get_preliminary_detection_reconciliation_repo(),
            job_source_asset_repo=c.get_job_source_asset_repo(),
            enabled=True,
            clock=c.get_clock(),
        )
        result = uc.execute(
            EnqueueReconciliationCommand(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                job_id=job_id,
            )
        )
        logger.info(
            "reconciliation_enqueued_on_terminal job_id=%s enqueued=%s batch_id=%s",
            job_id,
            result.enqueued,
            result.batch_id,
        )
    except Exception:
        # Never fail job terminalization because of diagnostic reconciliation.
        logger.exception(
            "reconciliation_enqueue_failed job_id=%s aisle_id=%s", job_id, aisle_id
        )
