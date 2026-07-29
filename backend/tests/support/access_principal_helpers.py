"""Test helpers for constructing ``AccessPrincipal`` / ``InventoryAccessPolicy`` (Phase 2 corrections).

Use these instead of hand-rolling ``AccessPrincipal(...)`` or ``AuthUser(...)`` in unit tests so
call sites stay aligned with the mandatory ``access_policy`` / ``principal`` use-case contracts.
"""

from __future__ import annotations

from src.application.dto.access_principal import AccessPrincipal
from src.application.services.access_principal_factory import access_principal_from_auth_user
from src.application.services.inventory_access_policy import InventoryAccessPolicy
from src.auth.schemas import AuthUser


def platform_principal(actor_id: str = "u-platform") -> AccessPrincipal:
    """Platform-scoped principal: may access any inventory regardless of client_id."""
    return AccessPrincipal(
        actor_id=actor_id,
        client_id=None,
        roles=frozenset({"platform_admin"}),
        is_platform=True,
    )


def company_principal(client_id: str, actor_id: str = "u-company") -> AccessPrincipal:
    """Company-scoped principal: restricted to inventories matching ``client_id``."""
    return AccessPrincipal(
        actor_id=actor_id,
        client_id=client_id,
        roles=frozenset({"company_admin"}),
        is_platform=False,
    )


def policy_for(
    inv_repo,
    aisle_repo=None,
    capture_session_repo=None,
) -> InventoryAccessPolicy:
    """Build an ``InventoryAccessPolicy`` for the given repos (aisle/session optional)."""
    return InventoryAccessPolicy(
        inv_repo,
        aisle_repo=aisle_repo,
        capture_session_repo=capture_session_repo,
    )


def principal_from_auth_user(user: AuthUser) -> AccessPrincipal:
    """Wrap the production factory for tests migrating away from raw ``AuthUser`` call sites."""
    return access_principal_from_auth_user(user)
