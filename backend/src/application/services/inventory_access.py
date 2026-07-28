"""Inventory client-scope authorization for inventory-rooted APIs (Phase 2).

Reuses the same 404-on-mismatch policy as Observability so existence of
cross-client resources is not leaked. Platform roles retain global access.
"""

from __future__ import annotations

import logging

from src.application.errors import InventoryNotFoundError
from src.application.ports.repositories import InventoryRepository
from src.application.services.observability_access import (
    ObservabilityAccessContext,
    assert_inventory_client_scope,
)
from src.auth.schemas import AuthUser
from src.domain.inventory.entities import Inventory

logger = logging.getLogger(__name__)


def authorize_inventory_access(
    inventory_repo: InventoryRepository,
    *,
    inventory_id: str,
    user: AuthUser,
) -> Inventory:
    """Load inventory and enforce actor → client → inventory scope.

    Mismatch / missing → ``InventoryNotFoundError`` (HTTP 404 path).
    """
    access = ObservabilityAccessContext.from_user(user)
    inventory = assert_inventory_client_scope(
        inventory_repo,
        inventory_id=inventory_id,
        access=access,
    )
    if not access.is_platform:
        logger.info(
            "event=inventory_access_authorized inventory_id=%s actor_client_id=%s",
            inventory_id,
            access.client_id,
        )
    return inventory


def authorize_inventory_access_or_log_denied(
    inventory_repo: InventoryRepository,
    *,
    inventory_id: str,
    user: AuthUser,
) -> Inventory:
    """Same as :func:`authorize_inventory_access` with structured deny logging."""
    try:
        return authorize_inventory_access(
            inventory_repo, inventory_id=inventory_id, user=user
        )
    except InventoryNotFoundError:
        access = ObservabilityAccessContext.from_user(user)
        if not access.is_platform:
            logger.info(
                "event=cross_client_access_denied actor_client_id=%s resource_type=inventory "
                "resource_id=%s",
                access.client_id,
                inventory_id,
            )
        raise
