"""Application-layer access principal (Phase 2 corrections).

Auth adapters map JWT ``AuthUser`` into this DTO. Use cases must not import AuthUser.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AccessPrincipal:
    """Authenticated actor for inventory-rooted application operations."""

    actor_id: str
    client_id: str | None
    roles: frozenset[str]
    is_platform: bool


class AccessPrincipalRequiredError(Exception):
    """Raised when a user-facing use case is invoked without an AccessPrincipal."""


class InventoryAccessPolicyRequiredError(Exception):
    """Raised when a use case is constructed without an InventoryAccessPolicy."""
