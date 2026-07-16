"""Observability access control: roles, client scope, and capability gates.

Roles:
- ``platform_admin`` — may have global scope (``client_id is None``).
- ``company_admin`` / ``operator`` — require non-empty ``client_id`` (fail closed).
- ``administrator`` — temporary alias of ``platform_admin`` for legacy JWTs.

Only ``platform_admin`` (incl. administrator alias) may access inventories across
clients. Absence of ``client_id`` is never treated as global for company roles.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.errors import InventoryNotFoundError, JobNotFoundError
from src.application.ports.repositories import InventoryRepository
from src.auth.schemas import AuthUser
from src.domain.inventory.entities import Inventory

# Capability names used by Observability endpoints and UI gating.
CAP_VIEW_SUMMARY = "observability.view_summary"
CAP_VIEW_TECHNICAL_LOGS = "observability.view_technical_logs"
CAP_VIEW_FULL_PROMPT = "observability.view_full_prompt"
CAP_VIEW_STACK_TRACES = "observability.view_stack_traces"
CAP_DOWNLOAD_ARTIFACTS = "observability.download_artifacts"
CAP_VIEW_ARTIFACT_PREVIEW = "observability.view_artifact_preview"
CAP_CANCEL_RETRY = "observability.cancel_retry"
CAP_FINALIZATION_RECOVERY = "observability.finalization_recovery"

ROLE_PLATFORM_ADMIN = "platform_admin"
ROLE_COMPANY_ADMIN = "company_admin"
ROLE_OPERATOR = "operator"
# Legacy JWT role — treated as platform_admin for a documented transition window.
ROLE_ADMINISTRATOR_LEGACY = "administrator"

_PLATFORM_ROLES = frozenset({ROLE_PLATFORM_ADMIN, ROLE_ADMINISTRATOR_LEGACY})
_COMPANY_SCOPED_ROLES = frozenset({ROLE_COMPANY_ADMIN, ROLE_OPERATOR})


_ROLE_CAPABILITIES: dict[str, frozenset[str]] = {
    ROLE_OPERATOR: frozenset(
        {
            CAP_VIEW_SUMMARY,
            CAP_DOWNLOAD_ARTIFACTS,
            CAP_VIEW_ARTIFACT_PREVIEW,
            CAP_CANCEL_RETRY,
        }
    ),
    ROLE_COMPANY_ADMIN: frozenset(
        {
            CAP_VIEW_SUMMARY,
            CAP_VIEW_TECHNICAL_LOGS,
            CAP_VIEW_FULL_PROMPT,
            CAP_DOWNLOAD_ARTIFACTS,
            CAP_VIEW_ARTIFACT_PREVIEW,
            CAP_CANCEL_RETRY,
        }
    ),
    ROLE_PLATFORM_ADMIN: frozenset(
        {
            CAP_VIEW_SUMMARY,
            CAP_VIEW_TECHNICAL_LOGS,
            CAP_VIEW_FULL_PROMPT,
            CAP_VIEW_STACK_TRACES,
            CAP_DOWNLOAD_ARTIFACTS,
            CAP_VIEW_ARTIFACT_PREVIEW,
            CAP_CANCEL_RETRY,
            CAP_FINALIZATION_RECOVERY,
        }
    ),
}
# Legacy alias shares platform_admin capabilities.
_ROLE_CAPABILITIES[ROLE_ADMINISTRATOR_LEGACY] = _ROLE_CAPABILITIES[ROLE_PLATFORM_ADMIN]


class ObservabilityAuthError(Exception):
    """Raised when a principal is misconfigured or lacks a capability."""

    def __init__(self, code: str, message: str, *, http_status: int = 403) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def normalize_role(role: str | None) -> str:
    key = (role or "").strip().lower()
    if not key:
        return ROLE_OPERATOR
    if key == ROLE_ADMINISTRATOR_LEGACY:
        return ROLE_PLATFORM_ADMIN
    return key


def is_platform_role(role: str | None) -> bool:
    raw = (role or "").strip().lower()
    return raw in _PLATFORM_ROLES or normalize_role(raw) == ROLE_PLATFORM_ADMIN


def capabilities_for_role(role: str) -> frozenset[str]:
    raw = (role or "").strip().lower()
    if raw in _ROLE_CAPABILITIES:
        return _ROLE_CAPABILITIES[raw]
    return _ROLE_CAPABILITIES.get(normalize_role(raw), _ROLE_CAPABILITIES[ROLE_OPERATOR])


def principal_has_capability(user: AuthUser, capability: str) -> bool:
    return capability in capabilities_for_role(user.role)


def validate_principal_tenant_binding(user: AuthUser) -> None:
    """Fail closed: only platform roles may omit client_id (global scope)."""
    if is_platform_role(user.role):
        return
    client = (user.client_id or "").strip() or None
    if client is None:
        raise ObservabilityAuthError(
            "PRINCIPAL_MISSING_CLIENT_SCOPE",
            "Non-platform principals require client_id.",
            http_status=403,
        )


@dataclass(frozen=True)
class ObservabilityAccessContext:
    """Resolved auth context for one Observability request."""

    user: AuthUser
    client_id: str | None
    capabilities: frozenset[str]
    is_platform: bool

    @classmethod
    def from_user(cls, user: AuthUser) -> ObservabilityAccessContext:
        validate_principal_tenant_binding(user)
        caps = capabilities_for_role(user.role)
        return cls(
            user=user,
            client_id=(user.client_id or "").strip() or None,
            capabilities=caps,
            is_platform=is_platform_role(user.role),
        )

    def require(self, capability: str) -> None:
        if capability not in self.capabilities:
            raise ObservabilityAuthError(
                "FORBIDDEN_CAPABILITY",
                f"Missing capability: {capability}",
                http_status=403,
            )


def assert_inventory_client_scope(
    inventory_repo: InventoryRepository,
    *,
    inventory_id: str,
    access: ObservabilityAccessContext,
) -> Inventory:
    """Load inventory and enforce client scope.

    Platform principals may access any inventory. Company-scoped principals must
    match ``inventory.client_id``. Mismatch → ``InventoryNotFoundError`` (404 path).
    """
    inventory = inventory_repo.get_by_id(inventory_id)
    if inventory is None:
        raise InventoryNotFoundError(f"Inventory not found: {inventory_id}")
    if access.is_platform:
        return inventory
    principal_client = (access.client_id or "").strip() or None
    if principal_client is None:
        # Should have been rejected by validate_principal_tenant_binding.
        raise InventoryNotFoundError(f"Inventory not found: {inventory_id}")
    inv_client = (inventory.client_id or "").strip() or None
    if inv_client != principal_client:
        raise InventoryNotFoundError(f"Inventory not found: {inventory_id}")
    return inventory


def require_capability_or_not_found(access: ObservabilityAccessContext, capability: str) -> None:
    """Hide technical surfaces from unauthorized callers (404-equivalent)."""
    if capability not in access.capabilities:
        raise JobNotFoundError("Job not found")
