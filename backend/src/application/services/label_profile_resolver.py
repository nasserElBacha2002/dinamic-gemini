"""Resolve effective ITEM/POSITION label profile sources (Phase 1 — no runtime consumption)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.application.errors import ClientSupplierClientMismatchError, ClientSupplierNotFoundError
from src.application.ports.client_supplier_label_profile_repository import (
    ClientSupplierLabelProfileRepository,
)
from src.application.ports.repositories import (
    ClientSupplierRepository,
    SupplierPromptConfigRepository,
)
from src.application.ports.supplier_extraction_profile_repository import (
    SupplierExtractionProfileRepository,
)
from src.domain.aisle.entities import Aisle
from src.domain.client_supplier.extraction_profile import (
    ExtractionProfileStatus,
    SupplierExtractionProfile,
)
from src.domain.client_supplier.prompt_config import SupplierPromptConfig
from src.domain.label_profiles.entities import (
    ClientSupplierLabelProfile,
    ResolvedLabelProfile,
    ResolvedLabelProfiles,
)
from src.domain.label_profiles.errors import SupplierLabelProfileNotConfiguredError
from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource, effective_label_kind

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LabelProfileResolutionContext:
    client_id: str | None
    client_supplier_id: str | None
    aisle: Aisle | None = None


@dataclass(frozen=True)
class _SupplierBackingRefs:
    extraction_profile_id: str | None = None
    extraction_profile_version: int | None = None
    supplier_prompt_config_id: str | None = None
    supplier_prompt_config_version: int | None = None

    def has_any(self) -> bool:
        return self.extraction_profile_id is not None or self.supplier_prompt_config_id is not None


class LabelProfileResolver:
    """Central resolver for ITEM/POSITION profile source selection.

    Precedence (per label kind):
    1. Aisle override (``item_profile_source_override`` / ``position_profile_source_override``)
    2. ClientSupplier stored config (``client_supplier_label_profiles``)
    3. DINAMIC default (absence of row — not persisted)
    """

    def __init__(
        self,
        *,
        label_profile_repo: ClientSupplierLabelProfileRepository,
        client_supplier_repo: ClientSupplierRepository,
        extraction_profile_repo: SupplierExtractionProfileRepository | None = None,
        supplier_prompt_config_repo: SupplierPromptConfigRepository | None = None,
    ) -> None:
        self._label_profile_repo = label_profile_repo
        self._client_supplier_repo = client_supplier_repo
        self._extraction_profile_repo = extraction_profile_repo
        self._supplier_prompt_config_repo = supplier_prompt_config_repo

    def resolve(self, ctx: LabelProfileResolutionContext) -> ResolvedLabelProfiles:
        if ctx.client_supplier_id and ctx.client_id:
            supplier = self._client_supplier_repo.get_by_id(ctx.client_supplier_id)
            if supplier is None:
                raise ClientSupplierNotFoundError(
                    f"Client supplier not found: {ctx.client_supplier_id}"
                )
            if supplier.client_id != ctx.client_id:
                raise ClientSupplierClientMismatchError(
                    "Client supplier does not belong to inventory client"
                )

        backings = self._load_supplier_backings(ctx)
        item = self._resolve_one(
            ctx=ctx,
            label_kind=LabelKind.ITEM,
            override=ctx.aisle.item_profile_source_override if ctx.aisle else None,
            backing=backings.get(LabelKind.ITEM),
        )
        position = self._resolve_one(
            ctx=ctx,
            label_kind=LabelKind.POSITION,
            override=ctx.aisle.position_profile_source_override if ctx.aisle else None,
            backing=backings.get(LabelKind.POSITION),
        )
        resolved = ResolvedLabelProfiles(item=item, position=position)
        logger.info(
            "resolved_label_profiles client_id=%s client_supplier_id=%s "
            "item_source=%s position_source=%s item_resolution=%s position_resolution=%s",
            ctx.client_id,
            ctx.client_supplier_id,
            item.source.value,
            position.source.value,
            item.resolution_source,
            position.resolution_source,
        )
        return resolved

    def _resolve_one(
        self,
        *,
        ctx: LabelProfileResolutionContext,
        label_kind: LabelKind,
        override: LabelProfileSource | None,
        backing: _SupplierBackingRefs | None,
    ) -> ResolvedLabelProfile:
        supplier_id = (ctx.client_supplier_id or "").strip() or None
        stored: ClientSupplierLabelProfile | None = None
        if supplier_id:
            stored = self._label_profile_repo.get_by_supplier_and_kind(supplier_id, label_kind)

        if override is not None:
            source = override
            resolution_source = "AISLE_OVERRIDE"
        elif stored is not None:
            source = stored.source
            resolution_source = "CLIENT_SUPPLIER"
        else:
            source = LabelProfileSource.DINAMIC
            resolution_source = "DEFAULT"

        profile = ResolvedLabelProfile(
            label_kind=label_kind,
            source=source,
            client_supplier_id=supplier_id,
            profile_config_id=stored.id if stored else None,
            resolution_source=resolution_source,
        )

        if source != LabelProfileSource.SUPPLIER:
            return profile

        if not supplier_id or not ctx.client_id:
            raise SupplierLabelProfileNotConfiguredError(
                f"SUPPLIER source for {label_kind.value} requires a client supplier",
                label_kind=label_kind.value,
                client_supplier_id=supplier_id,
            )

        if backing is None or not backing.has_any():
            raise SupplierLabelProfileNotConfiguredError(
                f"No active supplier configuration for {label_kind.value} label profile",
                label_kind=label_kind.value,
                client_supplier_id=supplier_id,
            )
        return ResolvedLabelProfile(
            label_kind=label_kind,
            source=source,
            client_supplier_id=supplier_id,
            profile_config_id=stored.id if stored else None,
            resolution_source=resolution_source,
            extraction_profile_id=backing.extraction_profile_id,
            extraction_profile_version=backing.extraction_profile_version,
            supplier_prompt_config_id=backing.supplier_prompt_config_id,
            supplier_prompt_config_version=backing.supplier_prompt_config_version,
        )

    def _load_supplier_backings(
        self, ctx: LabelProfileResolutionContext
    ) -> dict[LabelKind, _SupplierBackingRefs]:
        if not ctx.client_id or not ctx.client_supplier_id:
            return {}
        extractions: list[SupplierExtractionProfile] = []
        prompts: list[SupplierPromptConfig] = []
        if self._extraction_profile_repo is not None:
            extractions = list(
                self._extraction_profile_repo.list_by_supplier(
                    ctx.client_id, ctx.client_supplier_id
                )
            )
        if self._supplier_prompt_config_repo is not None:
            prompts = list(
                self._supplier_prompt_config_repo.list_by_supplier(ctx.client_supplier_id)
            )

        out: dict[LabelKind, _SupplierBackingRefs] = {}
        for kind in LabelKind:
            extraction = _pick_active_extraction(extractions, kind)
            prompt = _pick_active_prompt(prompts, kind)
            if extraction is None and prompt is None:
                continue
            out[kind] = _SupplierBackingRefs(
                extraction_profile_id=extraction.id if extraction else None,
                extraction_profile_version=int(extraction.version) if extraction else None,
                supplier_prompt_config_id=prompt.id if prompt else None,
                supplier_prompt_config_version=int(prompt.version) if prompt else None,
            )
        return out


def _pick_active_extraction(
    profiles: list[SupplierExtractionProfile], kind: LabelKind
) -> SupplierExtractionProfile | None:
    best: SupplierExtractionProfile | None = None
    best_version = -1
    for profile in profiles:
        if profile.status is not ExtractionProfileStatus.ACTIVE:
            continue
        if effective_label_kind(profile.label_kind) != kind:
            continue
        if profile.version >= best_version:
            best = profile
            best_version = profile.version
    return best


def _pick_active_prompt(
    prompts: list[SupplierPromptConfig], kind: LabelKind
) -> SupplierPromptConfig | None:
    best: SupplierPromptConfig | None = None
    best_version = -1
    for prompt in prompts:
        if not prompt.is_active:
            continue
        if effective_label_kind(prompt.label_kind) != kind:
            continue
        if prompt.version >= best_version:
            best = prompt
            best_version = prompt.version
    return best
