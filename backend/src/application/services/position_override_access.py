"""Role-to-capability mapping for manual product-position overrides."""

from __future__ import annotations

from src.application.dto.access_principal import AccessPrincipal
from src.application.position_override_errors import PositionOverrideAccessDeniedError

CAP_VIEW = "position_overrides:view"
CAP_CREATE = "position_overrides:create"
CAP_REMOVE = "position_overrides:remove"
CAP_RESTORE = "position_overrides:restore"
CAP_AUDIT = "position_overrides:audit"

_ALL = frozenset({CAP_VIEW, CAP_CREATE, CAP_REMOVE, CAP_RESTORE, CAP_AUDIT})
_SUPERVISOR = frozenset({CAP_VIEW, CAP_CREATE, CAP_REMOVE, CAP_RESTORE})
_VIEW = frozenset({CAP_VIEW})
_ROLE_CAPABILITIES = {
    "platform_admin": _ALL,
    "administrator": _ALL,
    "admin": _ALL,
    "company_admin": _ALL,
    "supervisor": _SUPERVISOR,
    "responsable": _SUPERVISOR,
    "lector": _VIEW,
    "reader": _VIEW,
}


def capabilities_for_position_override(principal: AccessPrincipal) -> frozenset[str]:
    if principal.is_platform:
        return _ALL
    capabilities: set[str] = set()
    for role in principal.roles:
        capabilities.update(_ROLE_CAPABILITIES.get(role.strip().lower(), ()))
    return frozenset(capabilities)


def require_position_override_capability(
    principal: AccessPrincipal, capability: str
) -> None:
    if capability not in capabilities_for_position_override(principal):
        raise PositionOverrideAccessDeniedError(
            f"Missing capability: {capability}"
        )
