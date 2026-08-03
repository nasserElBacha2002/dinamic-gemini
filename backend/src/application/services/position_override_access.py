"""Role-to-capability mapping for manual product-position overrides."""

from __future__ import annotations

from src.application.dto.access_principal import AccessPrincipal
from src.application.position_override_errors import PositionOverrideAccessDeniedError
from src.application.services.observability_access import (
    CAP_POSITION_OVERRIDE_AUDIT,
    CAP_POSITION_OVERRIDE_CREATE,
    CAP_POSITION_OVERRIDE_REMOVE,
    CAP_POSITION_OVERRIDE_RESTORE,
    CAP_POSITION_OVERRIDE_VIEW,
    capabilities_for_role,
)

CAP_VIEW = CAP_POSITION_OVERRIDE_VIEW
CAP_CREATE = CAP_POSITION_OVERRIDE_CREATE
CAP_REMOVE = CAP_POSITION_OVERRIDE_REMOVE
CAP_RESTORE = CAP_POSITION_OVERRIDE_RESTORE
CAP_AUDIT = CAP_POSITION_OVERRIDE_AUDIT

_ALL = frozenset({CAP_VIEW, CAP_CREATE, CAP_REMOVE, CAP_RESTORE, CAP_AUDIT})


def capabilities_for_position_override(principal: AccessPrincipal) -> frozenset[str]:
    if principal.is_platform:
        return _ALL
    capabilities: set[str] = set()
    for role in principal.roles:
        capabilities.update(capabilities_for_role(role))
    return frozenset(capabilities)


def require_position_override_capability(
    principal: AccessPrincipal, capability: str
) -> None:
    if capability not in capabilities_for_position_override(principal):
        raise PositionOverrideAccessDeniedError(
            f"Missing capability: {capability}"
        )
