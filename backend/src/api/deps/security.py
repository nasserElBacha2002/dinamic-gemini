"""Authentication-adjacent FastAPI request guards and access providers."""

from __future__ import annotations

import secrets

from fastapi import Depends, Header, HTTPException, Query, status

from src.application.dto.access_principal import AccessPrincipal
from src.application.ports.repositories import (
    AisleRepository,
    ClientRepository,
    InventoryRepository,
)
from src.application.services.access_principal_factory import access_principal_from_auth_user
from src.application.services.inventory_access_policy import InventoryAccessPolicy
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from src.runtime.v3_deps import (
    get_aisle_repo,
    get_capture_session_repo,
    get_client_repo,
    get_inventory_repo,
)


def require_inventory_client_scope(
    inventory_id: str,
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    user: AuthUser = Depends(get_current_admin),
) -> AccessPrincipal:
    """FastAPI dependency: enforce actor→client→inventory; return AccessPrincipal.

    Raised as a **dependency** (before the route body runs), so failures here are not
    caught by a route's own ``try/except reraise_if_mapped``. Map them explicitly —
    otherwise an unmapped ``InventoryNotFoundError`` raised during dependency resolution
    escapes FastAPI's registered exception handlers and surfaces as a 500, not the
    intended 404 (verified: ``ServerErrorMiddleware`` sits outside ``ExceptionMiddleware``,
    so only ``StructuredApiHttpError``/``HTTPException`` raised here become the documented
    client-facing status).
    """
    from src.api.errors import reraise_if_mapped

    principal = access_principal_from_auth_user(user)
    try:
        InventoryAccessPolicy(inventory_repo).require_inventory(inventory_id, principal)
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return principal


def require_client_scope(
    client_id: str,
    client_repo: ClientRepository = Depends(get_client_repo),
    user: AuthUser = Depends(get_current_admin),
) -> AccessPrincipal:
    """FastAPI dependency: enforce actor→client; return AccessPrincipal (404 cross-tenant)."""
    from src.api.errors import reraise_if_mapped
    from src.application.services.client_access_policy import ClientAccessPolicy

    principal = access_principal_from_auth_user(user)
    try:
        ClientAccessPolicy(client_repo).require_client(client_id, principal)
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return principal


def require_raspberry_offline_export_scope(
    client_id: str | None = Query(
        default=None,
        min_length=1,
        description="Optional client scope; omit to include all active clients.",
    ),
    user: AuthUser = Depends(get_current_admin),
    client_repo: ClientRepository = Depends(get_client_repo),
) -> str | None:
    """Enforce platform or client scope for Raspberry offline package export."""
    from src.api.errors import reraise_if_mapped
    from src.application.services.client_access_policy import ClientAccessPolicy

    principal = access_principal_from_auth_user(user)
    policy = ClientAccessPolicy(client_repo)
    scoped_client = client_id.strip() if client_id else None
    try:
        if scoped_client:
            policy.require_client(scoped_client, principal)
        else:
            policy.require_platform(
                principal,
                operation="export_raspberry_offline_package",
            )
    except Exception as exc:
        reraise_if_mapped(exc)
        raise
    return scoped_client


def require_raspberry_device_token(
    x_device_token: str | None = Header(default=None, alias="X-Device-Token"),
) -> None:
    from src.config import load_settings

    expected_token = (load_settings().raspberry_device_token or "").strip()
    if not expected_token or not x_device_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Raspberry device authentication is not configured or missing",
            headers={"WWW-Authenticate": "Device-Token"},
        )
    if not secrets.compare_digest(
        x_device_token.encode("utf-8"), expected_token.encode("utf-8")
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Raspberry device token",
            headers={"WWW-Authenticate": "Device-Token"},
        )


def get_access_principal(
    user: AuthUser = Depends(get_current_admin),
) -> AccessPrincipal:
    """FastAPI dependency: AuthUser → AccessPrincipal (no inventory scope check)."""
    return access_principal_from_auth_user(user)


def get_inventory_access_policy(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
) -> InventoryAccessPolicy:
    return InventoryAccessPolicy(inventory_repo, aisle_repo=aisle_repo)


def get_capture_session_access_policy(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    capture_session_repo=Depends(get_capture_session_repo),
) -> InventoryAccessPolicy:
    return InventoryAccessPolicy(
        inventory_repo,
        aisle_repo=aisle_repo,
        capture_session_repo=capture_session_repo,
    )


def require_capture_session_upload_scope(
    inventory_id: str,
    session_id: str,
    aisle_id: str | None = None,
    access_policy: InventoryAccessPolicy = Depends(get_capture_session_access_policy),
    user: AuthUser = Depends(get_current_admin),
) -> AccessPrincipal:
    """Validate inventory→session→aisle hierarchy before multipart staging spool.

    Runs as a **dependency**, ahead of ``files: File(...)`` in the route signature, so a
    denial here means Starlette/FastAPI never invokes the route body's own upload-spool
    call. Domain errors (``InventoryNotFoundError`` / ``CaptureSessionNotFoundError`` /
    ``AisleNotFoundError`` / ``CaptureSessionNotAcceptingUploadsError``) must be mapped to
    HTTP here explicitly: raised unmapped from a dependency, they bypass every route's
    ``try/except reraise_if_mapped`` and reach only the global ``Exception`` handler,
    which is wired to Starlette's outer ``ServerErrorMiddleware`` — producing a 500
    instead of the documented 404/409, even though the security check itself ran correctly.
    """
    from src.api.errors import reraise_if_mapped

    principal = access_principal_from_auth_user(user)
    try:
        access_policy.require_capture_session_for_staging_upload(
            inventory_id=inventory_id,
            session_id=session_id,
            principal=principal,
            aisle_id=aisle_id,
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return principal
