"""Map auth-layer AuthUser → application AccessPrincipal (Phase 2 corrections)."""

from __future__ import annotations

from src.application.dto.access_principal import AccessPrincipal
from src.application.services.observability_access import (
    is_platform_role,
    normalize_role,
    validate_principal_tenant_binding,
)
from src.auth.schemas import AuthUser


def access_principal_from_auth_user(user: AuthUser) -> AccessPrincipal:
    """Convert JWT principal to application AccessPrincipal (fail-closed tenant binding)."""
    validate_principal_tenant_binding(user)
    role = normalize_role(user.role)
    return AccessPrincipal(
        actor_id=user.id,
        client_id=(user.client_id or "").strip() or None,
        roles=frozenset({role}),
        is_platform=is_platform_role(user.role),
    )
