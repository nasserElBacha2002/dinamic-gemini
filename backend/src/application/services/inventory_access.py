"""Inventory client-scope authorization helpers (Phase 2).

Prefer :class:`~src.application.services.inventory_access_policy.InventoryAccessPolicy`
for new call sites. These thin wrappers remain for Observability-era callers.
"""

from __future__ import annotations

from src.application.dto.access_principal import AccessPrincipal
from src.application.ports.repositories import InventoryRepository
from src.application.services.access_principal_factory import access_principal_from_auth_user
from src.application.services.inventory_access_policy import InventoryAccessPolicy
from src.auth.schemas import AuthUser
from src.domain.inventory.entities import Inventory


def authorize_inventory_access(
    inventory_repo: InventoryRepository,
    *,
    inventory_id: str,
    user: AuthUser,
) -> Inventory:
    """Load inventory and enforce actor → client → inventory scope (404 on mismatch)."""
    principal = access_principal_from_auth_user(user)
    return InventoryAccessPolicy(inventory_repo).require_inventory(inventory_id, principal)


def authorize_inventory_access_for_principal(
    inventory_repo: InventoryRepository,
    *,
    inventory_id: str,
    principal: AccessPrincipal,
) -> Inventory:
    return InventoryAccessPolicy(inventory_repo).require_inventory(inventory_id, principal)


def authorize_inventory_access_or_log_denied(
    inventory_repo: InventoryRepository,
    *,
    inventory_id: str,
    user: AuthUser,
) -> Inventory:
    """Same as :func:`authorize_inventory_access` (deny logging lives in the policy)."""
    return authorize_inventory_access(
        inventory_repo, inventory_id=inventory_id, user=user
    )
