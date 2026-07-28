"""Inventory access policy for inventory-rooted application operations (Phase 2).

Platform principals may access any inventory. Company-scoped principals must match
``inventory.client_id``. Mismatch / missing → ``InventoryNotFoundError`` (HTTP 404 path).
Does not leak the owning client id of a denied resource.
"""

from __future__ import annotations

import logging

from src.application.dto.access_principal import AccessPrincipal
from src.application.errors import (
    AisleNotFoundError,
    CaptureSessionNotFoundError,
    InventoryNotFoundError,
)
from src.application.ports.capture_repositories import CaptureSessionRepository
from src.application.ports.repositories import AisleRepository, InventoryRepository
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.domain.aisle.entities import Aisle
from src.domain.capture.entities import CaptureSession, CaptureSessionStatus
from src.domain.inventory.entities import Inventory

logger = logging.getLogger(__name__)


class InventoryAccessPolicy:
    """Small reusable inventory/aisle/session ownership checks."""

    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository | None = None,
        capture_session_repo: CaptureSessionRepository | None = None,
        *,
        log_authorized: bool = False,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._capture_session_repo = capture_session_repo
        self._log_authorized = log_authorized

    def require_inventory(self, inventory_id: str, principal: AccessPrincipal) -> Inventory:
        inventory = self._inventory_repo.get_by_id(inventory_id)
        if inventory is None:
            self._log_denied(principal, resource_type="inventory", resource_id=inventory_id)
            raise InventoryNotFoundError(f"Inventory not found: {inventory_id}")
        if principal.is_platform:
            return inventory
        principal_client = (principal.client_id or "").strip() or None
        if principal_client is None:
            self._log_denied(principal, resource_type="inventory", resource_id=inventory_id)
            raise InventoryNotFoundError(f"Inventory not found: {inventory_id}")
        inv_client = (inventory.client_id or "").strip() or None
        if inv_client != principal_client:
            self._log_denied(principal, resource_type="inventory", resource_id=inventory_id)
            raise InventoryNotFoundError(f"Inventory not found: {inventory_id}")
        if self._log_authorized:
            logger.info(
                "event=inventory_access_authorized inventory_id=%s actor_client_id=%s",
                inventory_id,
                principal.client_id,
            )
        return inventory

    def require_aisle(
        self,
        inventory_id: str,
        aisle_id: str,
        principal: AccessPrincipal,
    ) -> Aisle:
        self.require_inventory(inventory_id, principal)
        if self._aisle_repo is None:
            raise AisleNotFoundError(f"Aisle not found: {aisle_id}")
        return require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            detail_style="strict",
        )

    def require_capture_session_for_staging_upload(
        self,
        *,
        inventory_id: str,
        session_id: str,
        principal: AccessPrincipal,
        aisle_id: str | None = None,
    ) -> CaptureSession:
        """Validate inventory → session → optional aisle before staging media spool."""
        self.require_inventory(inventory_id, principal)
        if self._capture_session_repo is None:
            raise CaptureSessionNotFoundError(f"Capture session not found: {session_id}")
        session = self._capture_session_repo.get_by_id_for_inventory(session_id, inventory_id)
        if session is None:
            self._log_denied(principal, resource_type="capture_session", resource_id=session_id)
            raise CaptureSessionNotFoundError(f"Capture session not found: {session_id}")
        if session.inventory_id != inventory_id:
            self._log_denied(principal, resource_type="capture_session", resource_id=session_id)
            raise CaptureSessionNotFoundError(f"Capture session not found: {session_id}")
        if aisle_id is not None:
            aisle = self.require_aisle(inventory_id, aisle_id, principal)
            if session.aisle_id is not None and session.aisle_id != aisle.id:
                self._log_denied(principal, resource_type="capture_session", resource_id=session_id)
                raise CaptureSessionNotFoundError(f"Capture session not found: {session_id}")
        if session.closed_at is not None or session.status in (
            CaptureSessionStatus.CANCELLED,
            CaptureSessionStatus.FAILED,
            CaptureSessionStatus.CONFIRMED,
        ):
            from src.application.errors import CaptureSessionNotAcceptingUploadsError

            raise CaptureSessionNotAcceptingUploadsError(
                f"Capture session {session_id} is not accepting uploads (status={session.status.value})"
            )
        return session

    @staticmethod
    def _log_denied(
        principal: AccessPrincipal, *, resource_type: str, resource_id: str
    ) -> None:
        if principal.is_platform:
            return
        logger.info(
            "event=cross_client_access_denied actor_client_id=%s resource_type=%s resource_id=%s",
            principal.client_id,
            resource_type,
            resource_id,
        )
