"""Attest that a historical supplier extraction profile version exists in scope."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.ports.repositories import (
    AisleRepository,
    ClientSupplierRepository,
    InventoryRepository,
)
from src.application.ports.supplier_extraction_profile_repository import (
    SupplierExtractionProfileRepository,
)
from src.domain.client_supplier.extraction_profile import SupplierExtractionProfile
from src.domain.label_profiles.kinds import LabelKind, effective_label_kind


class ProfileVersionNotFoundError(Exception):
    """Raised when mobile-attested profile id/version cannot be loaded."""

    code = "PROFILE_VERSION_NOT_FOUND"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ProfileVersionScopeMismatchError(Exception):
    """Raised when profile exists but does not belong to inventory/aisle/supplier scope."""

    code = "PROFILE_VERSION_SCOPE_MISMATCH"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class HistoricalProfileAttestation:
    profile_id: str
    profile_version: int
    client_supplier_id: str
    label_kind: LabelKind | None = None


class ExactExtractionProfileVersionService:
    """Load immutable profile versions for offline capture reconciliation.

    Never uses get_active() for historical captures.
    """

    def __init__(
        self,
        *,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        client_supplier_repo: ClientSupplierRepository,
        extraction_profile_repo: SupplierExtractionProfileRepository,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._client_supplier_repo = client_supplier_repo
        self._extraction_profile_repo = extraction_profile_repo

    def load_for_aisle_capture(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        attestation: HistoricalProfileAttestation,
    ) -> SupplierExtractionProfile:
        inventory = self._inventory_repo.get_by_id(inventory_id)
        if inventory is None:
            raise ProfileVersionScopeMismatchError("inventory not found")
        aisle = self._aisle_repo.get_by_id(aisle_id)
        if aisle is None or aisle.inventory_id != inventory_id:
            raise ProfileVersionScopeMismatchError("aisle not in inventory")

        supplier_id = (attestation.client_supplier_id or "").strip()
        aisle_supplier = (aisle.client_supplier_id or "").strip()
        if aisle_supplier and supplier_id and aisle_supplier != supplier_id:
            raise ProfileVersionScopeMismatchError(
                "client_supplier_id does not match aisle supplier"
            )

        supplier = self._client_supplier_repo.get_by_id(supplier_id)
        if supplier is None or supplier.client_id != inventory.client_id:
            raise ProfileVersionScopeMismatchError(
                "supplier not in inventory client scope"
            )

        profile = self._extraction_profile_repo.get_by_id(attestation.profile_id)
        if profile is None:
            # Fall back to version lookup (id may differ across environments).
            profile = self._extraction_profile_repo.get_by_client_supplier_version(
                inventory.client_id, supplier_id, int(attestation.profile_version)
            )
        if profile is None:
            raise ProfileVersionNotFoundError(
                f"profile version not found: {attestation.profile_id}@"
                f"{attestation.profile_version}"
            )

        if profile.client_id != inventory.client_id or profile.supplier_id != supplier_id:
            raise ProfileVersionScopeMismatchError("profile tenant/supplier mismatch")
        if int(profile.version) != int(attestation.profile_version):
            raise ProfileVersionNotFoundError(
                "profile id/version pair mismatch"
            )
        if attestation.label_kind is not None:
            if effective_label_kind(profile.label_kind) is not attestation.label_kind:
                raise ProfileVersionScopeMismatchError("profile label_kind mismatch")
        return profile
