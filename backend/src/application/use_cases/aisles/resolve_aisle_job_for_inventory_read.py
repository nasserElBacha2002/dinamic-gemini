"""
Resolve a ``Job`` row in the context of an inventory-scoped aisle (read-only API paths).

Used by GET ``.../jobs/{job_id}``, execution-log, execution-log.txt, hybrid-report,
auditability, artifacts, retry-chain, and related Observability routes so validation
stays in the application layer (Phase 6 + Observability company scope).
"""

from __future__ import annotations

from src.application.errors import JobDoesNotBelongToAisleError, JobNotFoundError
from src.application.ports.repositories import AisleRepository, InventoryRepository, JobRepository
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.application.services.observability_access import (
    ObservabilityAccessContext,
    assert_inventory_client_scope,
)
from src.auth.schemas import AuthUser
from src.domain.jobs.entities import Job


class ResolveAisleJobForInventoryReadUseCase:
    def __init__(
        self,
        job_repo: JobRepository,
        aisle_repo: AisleRepository,
        inventory_repo: InventoryRepository | None = None,
    ) -> None:
        self._job_repo = job_repo
        self._aisle_repo = aisle_repo
        self._inventory_repo = inventory_repo

    def execute(
        self,
        inventory_id: str,
        aisle_id: str,
        job_id: str,
        *,
        access_user: AuthUser | None = None,
    ) -> Job:
        """Resolve job under inventory/aisle scope.

        When ``access_user`` is provided and carries ``client_id``, also enforce
        ``inventory.client_id`` match (404 on mismatch). Platform-unbound admins
        (``client_id is None``) keep legacy inventory-wide access.
        """
        if self._inventory_repo is not None and access_user is not None:
            access = ObservabilityAccessContext.from_user(access_user)
            assert_inventory_client_scope(
                self._inventory_repo,
                inventory_id=inventory_id,
                access=access,
            )
        job = self._job_repo.get_by_id(job_id)
        if job is None:
            raise JobNotFoundError(f"Job not found: {job_id}")
        if job.target_type != "aisle" or job.target_id != aisle_id:
            raise JobDoesNotBelongToAisleError(f"Job {job_id} is not scoped to aisle {aisle_id}")
        require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            detail_style="strict",
        )
        return job
