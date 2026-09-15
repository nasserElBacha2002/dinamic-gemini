"""Client tenant access policy (Stage 2 corrections).

Complements :class:`~src.application.services.inventory_access_policy.InventoryAccessPolicy`.
Platform principals may access any client. Company-scoped principals must match
``principal.client_id``. Cross-tenant / missing client → ``ClientNotFoundError`` (HTTP 404).
Create-client is platform-only → ``PlatformOnlyOperationError`` (HTTP 403).

Denial logs never include raw client/resource IDs or JWT material.
"""

from __future__ import annotations

import logging

from src.application.dto.access_principal import AccessPrincipal
from src.application.errors import ClientNotFoundError, PlatformOnlyOperationError
from src.application.ports.repositories import ClientRepository
from src.domain.client.entities import Client

logger = logging.getLogger(__name__)


class ClientAccessPolicy:
    """Reusable client-id ownership checks for clients CRUD and nested client resources."""

    def __init__(self, client_repo: ClientRepository) -> None:
        self._client_repo = client_repo

    def require_client(self, client_id: str, principal: AccessPrincipal) -> Client:
        cid = (client_id or "").strip()
        client = self._client_repo.get_by_id(cid) if cid else None
        if client is None:
            self._log_denied(principal, reason_code="not_found", operation="require_client")
            raise ClientNotFoundError(f"Client not found: {cid}")
        if principal.is_platform:
            return client
        principal_client = (principal.client_id or "").strip() or None
        if principal_client is None:
            self._log_denied(
                principal, reason_code="missing_principal_client", operation="require_client"
            )
            raise ClientNotFoundError(f"Client not found: {cid}")
        if principal_client != cid:
            self._log_denied(principal, reason_code="cross_tenant", operation="require_client")
            raise ClientNotFoundError(f"Client not found: {cid}")
        return client

    def require_platform(self, principal: AccessPrincipal, *, operation: str) -> None:
        if principal.is_platform:
            return
        self._log_denied(principal, reason_code="platform_only", operation=operation)
        raise PlatformOnlyOperationError(
            f"Operation requires platform_admin: {operation}"
        )

    def list_visible(self, principal: AccessPrincipal) -> list[Client]:
        if principal.is_platform:
            return list(self._client_repo.list_all())
        principal_client = (principal.client_id or "").strip() or None
        if principal_client is None:
            return []
        return list(self._client_repo.list_for_client(principal_client))

    @staticmethod
    def _log_denied(
        principal: AccessPrincipal,
        *,
        reason_code: str,
        operation: str,
    ) -> None:
        logger.info(
            "event=authorization_denied reason_code=%s principal_role=%s "
            "resource_type=client operation=%s",
            reason_code,
            ",".join(sorted(principal.roles)) if principal.roles else "",
            operation,
        )
