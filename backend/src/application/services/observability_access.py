"""Observability access control: client scope and technical capability gates.

Platform principals (``client_id is None``) retain full access for backward
compatibility with the current single-tenant admin JWT model. When a principal
carries ``client_id``, all inventory-scoped observability reads must match
``inventory.client_id``.
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
CAP_CANCEL_RETRY = "observability.cancel_retry"
CAP_FINALIZATION_RECOVERY = "observability.finalization_recovery"


_ROLE_CAPABILITIES: dict[str, frozenset[str]] = {
    "operator": frozenset(
        {
            CAP_VIEW_SUMMARY,
            CAP_DOWNLOAD_ARTIFACTS,
            CAP_CANCEL_RETRY,
        }
    ),
    "company_admin": frozenset(
        {
            CAP_VIEW_SUMMARY,
            CAP_VIEW_TECHNICAL_LOGS,
            CAP_VIEW_FULL_PROMPT,
            CAP_DOWNLOAD_ARTIFACTS,
            CAP_CANCEL_RETRY,
        }
    ),
    # Current product role — full technical surface (platform or company-scoped admin).
    "administrator": frozenset(
        {
            CAP_VIEW_SUMMARY,
            CAP_VIEW_TECHNICAL_LOGS,
            CAP_VIEW_FULL_PROMPT,
            CAP_VIEW_STACK_TRACES,
            CAP_DOWNLOAD_ARTIFACTS,
            CAP_CANCEL_RETRY,
            CAP_FINALIZATION_RECOVERY,
        }
    ),
}


def capabilities_for_role(role: str) -> frozenset[str]:
    key = (role or "").strip().lower() or "administrator"
    return _ROLE_CAPABILITIES.get(key, _ROLE_CAPABILITIES["operator"])


def principal_has_capability(user: AuthUser, capability: str) -> bool:
    return capability in capabilities_for_role(user.role)


@dataclass(frozen=True)
class ObservabilityAccessContext:
    """Resolved auth context for one Observability request."""

    user: AuthUser
    client_id: str | None
    capabilities: frozenset[str]

    @classmethod
    def from_user(cls, user: AuthUser) -> ObservabilityAccessContext:
        caps = capabilities_for_role(user.role)
        return cls(user=user, client_id=user.client_id, capabilities=caps)

    def require(self, capability: str) -> None:
        if capability not in self.capabilities:
            # Prefer 404-style hiding for sensitive technical surfaces when scoped.
            raise JobNotFoundError("Job not found")


def assert_inventory_client_scope(
    inventory_repo: InventoryRepository,
    *,
    inventory_id: str,
    access: ObservabilityAccessContext,
) -> Inventory:
    """Load inventory and enforce client scope when the principal is company-bound.

    Returns 404-equivalent (``InventoryNotFoundError`` / ``JobNotFoundError`` path)
    when the inventory is missing or belongs to another client — never reveal cross-tenant existence.
    """
    inventory = inventory_repo.get_by_id(inventory_id)
    if inventory is None:
        raise InventoryNotFoundError(f"Inventory not found: {inventory_id}")
    principal_client = (access.client_id or "").strip() or None
    if principal_client is None:
        # Platform / unbound admin — preserve current single-tenant behavior.
        return inventory
    inv_client = (inventory.client_id or "").strip() or None
    if inv_client != principal_client:
        raise InventoryNotFoundError(f"Inventory not found: {inventory_id}")
    return inventory
