"""Use cases for ClientSupplier ITEM/POSITION label profile source config (Phase 1)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from src.application.errors import ClientSupplierClientMismatchError, ClientSupplierNotFoundError
from src.application.ports.client_supplier_label_profile_repository import (
    ClientSupplierLabelProfileRepository,
)
from src.application.ports.clock import Clock
from src.application.ports.repositories import (
    ClientSupplierRepository,
    SupplierPromptConfigRepository,
)
from src.application.ports.supplier_extraction_profile_repository import (
    SupplierExtractionProfileRepository,
)
from src.application.services.label_profile_resolver import (
    LabelProfileResolutionContext,
    LabelProfileResolver,
)
from src.domain.aisle.entities import Aisle
from src.domain.label_profiles.entities import (
    ClientSupplierLabelProfile,
    ResolvedLabelProfiles,
    virtual_dinamic_label_profile,
)
from src.domain.label_profiles.kinds import (
    LabelKind,
    LabelProfileSource,
    parse_label_profile_source,
)


def _validate_supplier_in_client_scope(
    client_supplier_repo: ClientSupplierRepository,
    *,
    client_id: str,
    supplier_id: str,
) -> None:
    supplier = client_supplier_repo.get_by_id(supplier_id)
    if supplier is None:
        raise ClientSupplierNotFoundError(f"Client supplier not found: {supplier_id}")
    if supplier.client_id != client_id:
        raise ClientSupplierClientMismatchError(
            "Client supplier does not belong to the requested client"
        )


@dataclass
class ListClientSupplierLabelProfilesCommand:
    client_id: str
    supplier_id: str


@dataclass
class UpsertClientSupplierLabelProfileCommand:
    client_id: str
    supplier_id: str
    label_kind: LabelKind
    source: LabelProfileSource


@dataclass
class ResolveEffectiveLabelProfilesCommand:
    client_id: str | None
    client_supplier_id: str | None
    aisle: Aisle | None = None


class ListClientSupplierLabelProfilesUseCase:
    def __init__(
        self,
        *,
        client_supplier_repo: ClientSupplierRepository,
        label_profile_repo: ClientSupplierLabelProfileRepository,
    ) -> None:
        self._client_supplier_repo = client_supplier_repo
        self._label_profile_repo = label_profile_repo

    def execute(
        self, command: ListClientSupplierLabelProfilesCommand
    ) -> list[ClientSupplierLabelProfile]:
        _validate_supplier_in_client_scope(
            self._client_supplier_repo,
            client_id=command.client_id,
            supplier_id=command.supplier_id,
        )
        stored = {
            p.label_kind: p
            for p in self._label_profile_repo.list_by_supplier(command.supplier_id)
        }
        out: list[ClientSupplierLabelProfile] = []
        for kind in LabelKind:
            if kind in stored:
                out.append(stored[kind])
            else:
                out.append(virtual_dinamic_label_profile(command.supplier_id, kind))
        return out


class UpsertClientSupplierLabelProfileUseCase:
    def __init__(
        self,
        *,
        client_supplier_repo: ClientSupplierRepository,
        label_profile_repo: ClientSupplierLabelProfileRepository,
        clock: Clock,
    ) -> None:
        self._client_supplier_repo = client_supplier_repo
        self._label_profile_repo = label_profile_repo
        self._clock = clock

    def execute(
        self, command: UpsertClientSupplierLabelProfileCommand
    ) -> ClientSupplierLabelProfile:
        _validate_supplier_in_client_scope(
            self._client_supplier_repo,
            client_id=command.client_id,
            supplier_id=command.supplier_id,
        )
        existing = self._label_profile_repo.get_by_supplier_and_kind(
            command.supplier_id, command.label_kind
        )
        now = self._clock.now()
        profile = ClientSupplierLabelProfile(
            id=existing.id if existing else str(uuid4()),
            client_supplier_id=command.supplier_id,
            label_kind=command.label_kind,
            source=command.source,
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        if command.source == LabelProfileSource.DINAMIC:
            self._label_profile_repo.delete_by_supplier_and_kind(
                command.supplier_id, command.label_kind
            )
            return virtual_dinamic_label_profile(command.supplier_id, command.label_kind)
        return self._label_profile_repo.upsert(profile)


class ResolveEffectiveLabelProfilesUseCase:
    def __init__(
        self,
        *,
        label_profile_repo: ClientSupplierLabelProfileRepository,
        client_supplier_repo: ClientSupplierRepository,
        extraction_profile_repo: SupplierExtractionProfileRepository | None = None,
        supplier_prompt_config_repo: SupplierPromptConfigRepository | None = None,
    ) -> None:
        self._resolver = LabelProfileResolver(
            label_profile_repo=label_profile_repo,
            client_supplier_repo=client_supplier_repo,
            extraction_profile_repo=extraction_profile_repo,
            supplier_prompt_config_repo=supplier_prompt_config_repo,
        )

    def execute(self, command: ResolveEffectiveLabelProfilesCommand) -> ResolvedLabelProfiles:
        return self._resolver.resolve(
            LabelProfileResolutionContext(
                client_id=command.client_id,
                client_supplier_id=command.client_supplier_id,
                aisle=command.aisle,
            )
        )


def parse_upsert_source(raw: str) -> LabelProfileSource:
    return parse_label_profile_source(raw)
