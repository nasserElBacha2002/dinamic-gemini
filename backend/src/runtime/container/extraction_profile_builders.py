"""Supplier extraction profile use-case construction (Phase 6)."""

from __future__ import annotations

from src.application.ports.clock import Clock
from src.application.ports.repositories import (
    ClientRepository,
    ClientSupplierRepository,
    SupplierReferenceImageRepository,
)
from src.application.ports.supplier_extraction_profile_repository import (
    SupplierExtractionProfileRepository,
    SupplierReferenceAnnotationRepository,
)
from src.application.use_cases.suppliers.manage_supplier_extraction_profiles import (
    ActivateSupplierExtractionProfileVersionUseCase,
    CloneSupplierExtractionProfileUseCase,
    CreateSupplierExtractionProfileVersionUseCase,
    GetActiveSupplierExtractionProfileUseCase,
    GetSupplierExtractionProfileByVersionUseCase,
    ListSupplierExtractionProfilesUseCase,
    ListSupplierReferenceAnnotationsUseCase,
    ReplaceSupplierReferenceAnnotationsUseCase,
)


def build_list_supplier_extraction_profiles_use_case(
    *,
    client_repo: ClientRepository,
    client_supplier_repo: ClientSupplierRepository,
    profile_repo: SupplierExtractionProfileRepository,
) -> ListSupplierExtractionProfilesUseCase:
    return ListSupplierExtractionProfilesUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        profile_repo=profile_repo,
    )


def build_get_active_supplier_extraction_profile_use_case(
    *,
    client_repo: ClientRepository,
    client_supplier_repo: ClientSupplierRepository,
    profile_repo: SupplierExtractionProfileRepository,
) -> GetActiveSupplierExtractionProfileUseCase:
    return GetActiveSupplierExtractionProfileUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        profile_repo=profile_repo,
    )


def build_get_supplier_extraction_profile_by_version_use_case(
    *,
    client_repo: ClientRepository,
    client_supplier_repo: ClientSupplierRepository,
    profile_repo: SupplierExtractionProfileRepository,
) -> GetSupplierExtractionProfileByVersionUseCase:
    return GetSupplierExtractionProfileByVersionUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        profile_repo=profile_repo,
    )


def build_create_supplier_extraction_profile_version_use_case(
    *,
    client_repo: ClientRepository,
    client_supplier_repo: ClientSupplierRepository,
    profile_repo: SupplierExtractionProfileRepository,
    clock: Clock,
) -> CreateSupplierExtractionProfileVersionUseCase:
    return CreateSupplierExtractionProfileVersionUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        profile_repo=profile_repo,
        clock=clock,
    )


def build_activate_supplier_extraction_profile_version_use_case(
    *,
    client_repo: ClientRepository,
    client_supplier_repo: ClientSupplierRepository,
    profile_repo: SupplierExtractionProfileRepository,
) -> ActivateSupplierExtractionProfileVersionUseCase:
    return ActivateSupplierExtractionProfileVersionUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        profile_repo=profile_repo,
    )


def build_clone_supplier_extraction_profile_use_case(
    *,
    client_repo: ClientRepository,
    client_supplier_repo: ClientSupplierRepository,
    profile_repo: SupplierExtractionProfileRepository,
    clock: Clock,
) -> CloneSupplierExtractionProfileUseCase:
    return CloneSupplierExtractionProfileUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        profile_repo=profile_repo,
        clock=clock,
    )


def build_list_supplier_reference_annotations_use_case(
    *,
    client_repo: ClientRepository,
    client_supplier_repo: ClientSupplierRepository,
    reference_repo: SupplierReferenceImageRepository,
    annotation_repo: SupplierReferenceAnnotationRepository,
) -> ListSupplierReferenceAnnotationsUseCase:
    return ListSupplierReferenceAnnotationsUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        reference_repo=reference_repo,
        annotation_repo=annotation_repo,
    )


def build_replace_supplier_reference_annotations_use_case(
    *,
    client_repo: ClientRepository,
    client_supplier_repo: ClientSupplierRepository,
    reference_repo: SupplierReferenceImageRepository,
    annotation_repo: SupplierReferenceAnnotationRepository,
) -> ReplaceSupplierReferenceAnnotationsUseCase:
    return ReplaceSupplierReferenceAnnotationsUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        reference_repo=reference_repo,
        annotation_repo=annotation_repo,
    )
