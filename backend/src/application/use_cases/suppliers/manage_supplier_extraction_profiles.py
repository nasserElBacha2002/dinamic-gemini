"""Supplier extraction profile use cases — Phase 6 application layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from src.application.errors import (
    ClientNotFoundError,
    ClientSupplierClientMismatchError,
    ClientSupplierNotFoundError,
    SupplierExtractionProfileActivationFailedError,
    SupplierExtractionProfileInvalidConfigurationError,
    SupplierExtractionProfileNotFoundError,
    SupplierExtractionProfileRowVersionConflictError,
    SupplierExtractionProfileVersionConflictError,
    SupplierReferenceImageNotFoundError,
)
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
from src.application.services.image_processing.extraction_profile_configuration import (
    ExtractionProfileConfigurationError,
    parse_extraction_configuration,
)
from src.domain.client_supplier.extraction_profile import (
    ExtractionProfileStatus,
    ReferenceAnnotation,
    SpatialRelation,
    SupplierExtractionProfile,
    default_extraction_configuration,
)

DEFAULT_PROFILE_KEY = "default"


@dataclass
class ListSupplierExtractionProfilesCommand:
    client_id: str
    supplier_id: str


@dataclass
class GetActiveSupplierExtractionProfileCommand:
    client_id: str
    supplier_id: str


@dataclass
class GetSupplierExtractionProfileByVersionCommand:
    client_id: str
    supplier_id: str
    version: int


@dataclass
class CreateSupplierExtractionProfileVersionCommand:
    client_id: str
    supplier_id: str
    configuration: dict[str, Any] | None
    visual_notes: str | None = None
    profile_key: str | None = None
    activate: bool = False
    created_by: str | None = None


@dataclass
class ActivateSupplierExtractionProfileVersionCommand:
    client_id: str
    supplier_id: str
    profile_id: str
    activated_by: str | None = None
    expected_row_version: int | None = None


@dataclass
class CloneSupplierExtractionProfileCommand:
    client_id: str
    supplier_id: str
    source_profile_id: str
    created_by: str | None = None


@dataclass
class ListSupplierReferenceAnnotationsCommand:
    client_id: str
    supplier_id: str
    image_id: str


@dataclass
class ReplaceSupplierReferenceAnnotationsCommand:
    client_id: str
    supplier_id: str
    image_id: str
    annotations: list[dict[str, Any]]
    profile_id: str | None = None


def _validate_supplier_in_client_scope(
    *,
    client_repo: ClientRepository,
    client_supplier_repo: ClientSupplierRepository,
    client_id: str,
    supplier_id: str,
) -> None:
    client = client_repo.get_by_id(client_id)
    if client is None:
        raise ClientNotFoundError(f"Client not found: {client_id}")
    supplier = client_supplier_repo.get_by_id(supplier_id)
    if supplier is None:
        raise ClientSupplierNotFoundError(f"Client supplier not found: {supplier_id}")
    if supplier.client_id != client_id:
        raise ClientSupplierClientMismatchError(
            "Client supplier does not belong to the requested client"
        )


def _parse_configuration(raw: dict[str, Any] | None):
    try:
        return parse_extraction_configuration(raw)
    except ExtractionProfileConfigurationError as exc:
        raise SupplierExtractionProfileInvalidConfigurationError(str(exc)) from exc


def _normalize_profile_key(profile_key: str | None) -> str:
    normalized = (profile_key or DEFAULT_PROFILE_KEY).strip()
    return normalized or DEFAULT_PROFILE_KEY


def _normalize_visual_notes(visual_notes: str | None) -> str | None:
    return (visual_notes or "").strip() or None


def _ensure_profile_in_scope(
    profile: SupplierExtractionProfile | None,
    *,
    client_id: str,
    supplier_id: str,
    profile_id: str,
) -> SupplierExtractionProfile:
    if (
        profile is None
        or profile.client_id != client_id
        or profile.supplier_id != supplier_id
    ):
        raise SupplierExtractionProfileNotFoundError(
            f"Supplier extraction profile not found in supplier scope: {profile_id}"
        )
    return profile


def _parse_annotation_payload(
    raw: dict[str, Any],
    *,
    template_image_id: str,
    profile_id: str | None,
) -> ReferenceAnnotation:
    field_key = str(raw.get("field_key") or "").strip().lower()
    if not field_key:
        raise SupplierExtractionProfileInvalidConfigurationError("field_key is required")
    anchor_texts_raw = raw.get("anchor_texts") or []
    if not isinstance(anchor_texts_raw, list):
        raise SupplierExtractionProfileInvalidConfigurationError(
            "anchor_texts must be a list of strings"
        )
    anchor_texts = tuple(str(x).strip() for x in anchor_texts_raw if str(x).strip())
    spatial_key = str(raw.get("spatial_relation") or "").strip().upper()
    try:
        spatial_relation = SpatialRelation(spatial_key)
    except ValueError as exc:
        raise SupplierExtractionProfileInvalidConfigurationError(
            f"unsupported spatial_relation {spatial_key!r}"
        ) from exc
    polygon_raw = raw.get("normalized_polygon")
    polygon: tuple[tuple[float, float], ...] | None = None
    if polygon_raw:
        if not isinstance(polygon_raw, list):
            raise SupplierExtractionProfileInvalidConfigurationError(
                "normalized_polygon must be a list of [x, y] pairs"
            )
        polygon = tuple((float(p[0]), float(p[1])) for p in polygon_raw)
    annotation_id = str(raw.get("id") or uuid4())
    return ReferenceAnnotation(
        id=annotation_id,
        template_image_id=template_image_id,
        profile_id=profile_id,
        field_key=field_key,
        anchor_texts=anchor_texts,
        spatial_relation=spatial_relation,
        normalized_polygon=polygon,
        priority=int(raw.get("priority") or 1),
        required=bool(raw.get("required", False)),
        max_distance_ratio=(
            float(raw["max_distance_ratio"])
            if raw.get("max_distance_ratio") is not None
            else None
        ),
    )


class ListSupplierExtractionProfilesUseCase:
    def __init__(
        self,
        client_repo: ClientRepository,
        client_supplier_repo: ClientSupplierRepository,
        profile_repo: SupplierExtractionProfileRepository,
    ) -> None:
        self._client_repo = client_repo
        self._client_supplier_repo = client_supplier_repo
        self._profile_repo = profile_repo

    def execute(
        self, command: ListSupplierExtractionProfilesCommand
    ) -> list[SupplierExtractionProfile]:
        _validate_supplier_in_client_scope(
            client_repo=self._client_repo,
            client_supplier_repo=self._client_supplier_repo,
            client_id=command.client_id,
            supplier_id=command.supplier_id,
        )
        return list(
            self._profile_repo.list_by_supplier(command.client_id, command.supplier_id)
        )


class GetActiveSupplierExtractionProfileUseCase:
    def __init__(
        self,
        client_repo: ClientRepository,
        client_supplier_repo: ClientSupplierRepository,
        profile_repo: SupplierExtractionProfileRepository,
    ) -> None:
        self._client_repo = client_repo
        self._client_supplier_repo = client_supplier_repo
        self._profile_repo = profile_repo

    def execute(
        self, command: GetActiveSupplierExtractionProfileCommand
    ) -> SupplierExtractionProfile | None:
        _validate_supplier_in_client_scope(
            client_repo=self._client_repo,
            client_supplier_repo=self._client_supplier_repo,
            client_id=command.client_id,
            supplier_id=command.supplier_id,
        )
        return self._profile_repo.get_active(command.client_id, command.supplier_id)


class GetSupplierExtractionProfileByVersionUseCase:
    def __init__(
        self,
        client_repo: ClientRepository,
        client_supplier_repo: ClientSupplierRepository,
        profile_repo: SupplierExtractionProfileRepository,
    ) -> None:
        self._client_repo = client_repo
        self._client_supplier_repo = client_supplier_repo
        self._profile_repo = profile_repo

    def execute(
        self, command: GetSupplierExtractionProfileByVersionCommand
    ) -> SupplierExtractionProfile:
        _validate_supplier_in_client_scope(
            client_repo=self._client_repo,
            client_supplier_repo=self._client_supplier_repo,
            client_id=command.client_id,
            supplier_id=command.supplier_id,
        )
        profile = self._profile_repo.get_by_client_supplier_version(
            command.client_id,
            command.supplier_id,
            int(command.version),
        )
        if profile is None:
            raise SupplierExtractionProfileNotFoundError(
                f"Supplier extraction profile version not found: {command.version}"
            )
        return profile


class CreateSupplierExtractionProfileVersionUseCase:
    def __init__(
        self,
        client_repo: ClientRepository,
        client_supplier_repo: ClientSupplierRepository,
        profile_repo: SupplierExtractionProfileRepository,
        clock: Clock,
    ) -> None:
        self._client_repo = client_repo
        self._client_supplier_repo = client_supplier_repo
        self._profile_repo = profile_repo
        self._clock = clock

    def execute(
        self, command: CreateSupplierExtractionProfileVersionCommand
    ) -> SupplierExtractionProfile:
        _validate_supplier_in_client_scope(
            client_repo=self._client_repo,
            client_supplier_repo=self._client_supplier_repo,
            client_id=command.client_id,
            supplier_id=command.supplier_id,
        )
        configuration = (
            _parse_configuration(command.configuration)
            if command.configuration is not None
            else default_extraction_configuration()
        )
        profile_key = _normalize_profile_key(command.profile_key)
        now = self._clock.now()
        try:
            created = self._profile_repo.create_next_version(
                client_id=command.client_id,
                supplier_id=command.supplier_id,
                profile_key=profile_key,
                configuration=configuration,
                visual_notes=_normalize_visual_notes(command.visual_notes),
                created_by=(command.created_by or "").strip() or None,
                created_at=now,
            )
        except SupplierExtractionProfileVersionConflictError:
            raise
        except ValueError as exc:
            if "version_conflict" in str(exc):
                raise SupplierExtractionProfileVersionConflictError(str(exc)) from exc
            raise
        if not command.activate:
            return created
        try:
            return self._profile_repo.activate_version(
                client_id=command.client_id,
                supplier_id=command.supplier_id,
                profile_id=created.id,
                activated_by=command.created_by,
            )
        except ValueError as exc:
            if str(exc) == "row_version_conflict":
                raise SupplierExtractionProfileRowVersionConflictError(str(exc)) from exc
            raise SupplierExtractionProfileActivationFailedError(str(exc)) from exc
        except KeyError as exc:
            raise SupplierExtractionProfileActivationFailedError(
                f"Failed to activate created supplier extraction profile: {created.id}"
            ) from exc


class ActivateSupplierExtractionProfileVersionUseCase:
    def __init__(
        self,
        client_repo: ClientRepository,
        client_supplier_repo: ClientSupplierRepository,
        profile_repo: SupplierExtractionProfileRepository,
    ) -> None:
        self._client_repo = client_repo
        self._client_supplier_repo = client_supplier_repo
        self._profile_repo = profile_repo

    def execute(
        self, command: ActivateSupplierExtractionProfileVersionCommand
    ) -> SupplierExtractionProfile:
        _validate_supplier_in_client_scope(
            client_repo=self._client_repo,
            client_supplier_repo=self._client_supplier_repo,
            client_id=command.client_id,
            supplier_id=command.supplier_id,
        )
        _ensure_profile_in_scope(
            self._profile_repo.get_by_id(command.profile_id),
            client_id=command.client_id,
            supplier_id=command.supplier_id,
            profile_id=command.profile_id,
        )
        try:
            return self._profile_repo.activate_version(
                client_id=command.client_id,
                supplier_id=command.supplier_id,
                profile_id=command.profile_id,
                activated_by=command.activated_by,
                expected_row_version=command.expected_row_version,
            )
        except ValueError as exc:
            if str(exc) == "row_version_conflict":
                raise SupplierExtractionProfileRowVersionConflictError(str(exc)) from exc
            raise SupplierExtractionProfileActivationFailedError(str(exc)) from exc
        except KeyError as exc:
            raise SupplierExtractionProfileNotFoundError(
                f"Supplier extraction profile not found: {command.profile_id}"
            ) from exc


class CloneSupplierExtractionProfileUseCase:
    def __init__(
        self,
        client_repo: ClientRepository,
        client_supplier_repo: ClientSupplierRepository,
        profile_repo: SupplierExtractionProfileRepository,
        clock: Clock,
    ) -> None:
        self._client_repo = client_repo
        self._client_supplier_repo = client_supplier_repo
        self._profile_repo = profile_repo
        self._clock = clock

    def execute(
        self, command: CloneSupplierExtractionProfileCommand
    ) -> SupplierExtractionProfile:
        _validate_supplier_in_client_scope(
            client_repo=self._client_repo,
            client_supplier_repo=self._client_supplier_repo,
            client_id=command.client_id,
            supplier_id=command.supplier_id,
        )
        source = _ensure_profile_in_scope(
            self._profile_repo.get_by_id(command.source_profile_id),
            client_id=command.client_id,
            supplier_id=command.supplier_id,
            profile_id=command.source_profile_id,
        )
        configuration = parse_extraction_configuration(source.configuration.to_public_dict())
        now = self._clock.now()
        try:
            return self._profile_repo.create_next_version(
                client_id=command.client_id,
                supplier_id=command.supplier_id,
                profile_key=source.profile_key,
                configuration=configuration,
                visual_notes=source.visual_notes,
                created_by=(command.created_by or "").strip() or None,
                created_at=now,
            )
        except SupplierExtractionProfileVersionConflictError:
            raise
        except ValueError as exc:
            if "version_conflict" in str(exc):
                raise SupplierExtractionProfileVersionConflictError(str(exc)) from exc
            raise


class ListSupplierReferenceAnnotationsUseCase:
    def __init__(
        self,
        client_repo: ClientRepository,
        client_supplier_repo: ClientSupplierRepository,
        reference_repo: SupplierReferenceImageRepository,
        annotation_repo: SupplierReferenceAnnotationRepository,
    ) -> None:
        self._client_repo = client_repo
        self._client_supplier_repo = client_supplier_repo
        self._reference_repo = reference_repo
        self._annotation_repo = annotation_repo

    def execute(
        self, command: ListSupplierReferenceAnnotationsCommand
    ) -> list[ReferenceAnnotation]:
        _validate_supplier_in_client_scope(
            client_repo=self._client_repo,
            client_supplier_repo=self._client_supplier_repo,
            client_id=command.client_id,
            supplier_id=command.supplier_id,
        )
        image = self._reference_repo.get_by_id(command.image_id)
        if image is None or image.client_supplier_id != command.supplier_id:
            raise SupplierReferenceImageNotFoundError(
                f"Supplier reference image not found in supplier scope: {command.image_id}"
            )
        return list(self._annotation_repo.list_by_template(command.image_id))


class ReplaceSupplierReferenceAnnotationsUseCase:
    def __init__(
        self,
        client_repo: ClientRepository,
        client_supplier_repo: ClientSupplierRepository,
        reference_repo: SupplierReferenceImageRepository,
        annotation_repo: SupplierReferenceAnnotationRepository,
        profile_repo: SupplierExtractionProfileRepository | None = None,
    ) -> None:
        self._client_repo = client_repo
        self._client_supplier_repo = client_supplier_repo
        self._reference_repo = reference_repo
        self._annotation_repo = annotation_repo
        self._profile_repo = profile_repo

    def execute(
        self, command: ReplaceSupplierReferenceAnnotationsCommand
    ) -> list[ReferenceAnnotation]:
        _validate_supplier_in_client_scope(
            client_repo=self._client_repo,
            client_supplier_repo=self._client_supplier_repo,
            client_id=command.client_id,
            supplier_id=command.supplier_id,
        )
        image = self._reference_repo.get_by_id(command.image_id)
        if image is None or image.client_supplier_id != command.supplier_id:
            raise SupplierReferenceImageNotFoundError(
                f"Supplier reference image not found in supplier scope: {command.image_id}"
            )
        # Tenant isolation: image must belong to the same client via client_supplier.
        supplier = self._client_supplier_repo.get_by_id(command.supplier_id)
        if supplier is None or supplier.client_id != command.client_id:
            raise ClientSupplierClientMismatchError(
                "Client supplier does not belong to the requested client"
            )

        if command.profile_id:
            if self._profile_repo is None:
                raise SupplierExtractionProfileNotFoundError(
                    f"Supplier extraction profile not found: {command.profile_id}"
                )
            profile = _ensure_profile_in_scope(
                self._profile_repo.get_by_id(command.profile_id),
                client_id=command.client_id,
                supplier_id=command.supplier_id,
                profile_id=command.profile_id,
            )
            if profile.status not in (
                ExtractionProfileStatus.DRAFT,
                ExtractionProfileStatus.ACTIVE,
            ):
                raise SupplierExtractionProfileInvalidConfigurationError(
                    f"profile {command.profile_id} status {profile.status.value} "
                    "cannot receive annotations"
                )

        parsed = [
            _parse_annotation_payload(
                item,
                template_image_id=command.image_id,
                profile_id=command.profile_id,
            )
            for item in command.annotations
        ]
        self._annotation_repo.replace_for_template(command.image_id, parsed)
        return list(self._annotation_repo.list_by_template(command.image_id))
