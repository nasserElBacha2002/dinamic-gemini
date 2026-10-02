"""Aisle location and positioning label API dependency providers.

Implementation is mechanically extracted from src.api.dependencies. The
historical module remains the public compatibility facade.
"""

from __future__ import annotations

from fastapi import Depends

from src.api.deps.infrastructure import get_aisle_location_label_artifact_repo
from src.api.deps.security import get_inventory_access_policy
from src.application.ports.clock import Clock
from src.application.ports.repositories import AisleRepository, InventoryRepository
from src.application.services.inventory_access_policy import InventoryAccessPolicy
from src.runtime.app_container import get_app_container
from src.runtime.v3_deps import (
    get_aisle_location_label_repo,
    get_aisle_location_repo,
    get_aisle_repo,
    get_clock,
    get_inventory_repo,
)


def get_create_aisle_location_use_case(
    location_repo=Depends(get_aisle_location_repo),
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.aisle_locations.manage_aisle_locations import (
        CreateAisleLocationUseCase,
    )

    return CreateAisleLocationUseCase(
        location_repo=location_repo,
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        access_policy=access_policy,
        clock=clock,
    )


def get_list_aisle_locations_use_case(
    location_repo=Depends(get_aisle_location_repo),
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
):
    from src.application.use_cases.aisle_locations.manage_aisle_locations import (
        ListAisleLocationsUseCase,
    )

    return ListAisleLocationsUseCase(
        location_repo=location_repo,
        access_policy=access_policy,
    )


def get_get_aisle_location_use_case(
    location_repo=Depends(get_aisle_location_repo),
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
):
    from src.application.use_cases.aisle_locations.manage_aisle_locations import (
        GetAisleLocationUseCase,
    )

    return GetAisleLocationUseCase(
        location_repo=location_repo,
        access_policy=access_policy,
    )


def get_update_aisle_location_use_case(
    location_repo=Depends(get_aisle_location_repo),
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.aisle_locations.manage_aisle_locations import (
        UpdateAisleLocationUseCase,
    )

    return UpdateAisleLocationUseCase(
        location_repo=location_repo,
        access_policy=access_policy,
        clock=clock,
    )


def get_issue_aisle_location_label_use_case(
    location_repo=Depends(get_aisle_location_repo),
    label_repo=Depends(get_aisle_location_label_repo),
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
    clock: Clock = Depends(get_clock),
):
    from src.application.services.positioning_label_signing import (
        PositioningLabelSigningConfig,
        PositioningLabelSigningService,
        parse_previous_secrets,
    )
    from src.application.use_cases.aisle_locations.manage_aisle_locations import (
        IssueAisleLocationLabelUseCase,
    )
    from src.config import load_settings

    settings = load_settings()
    signing = PositioningLabelSigningService(
        PositioningLabelSigningConfig(
            secret=settings.positioning_label_hmac_secret or None,
            key_version=int(settings.positioning_label_hmac_key_version),
            previous_secrets=parse_previous_secrets(
                settings.positioning_label_hmac_previous_secrets
            ),
            required=bool(settings.positioning_label_signing_required),
        )
    )
    return IssueAisleLocationLabelUseCase(
        location_repo=location_repo,
        label_repo=label_repo,
        access_policy=access_policy,
        clock=clock,
        signing=signing,
    )


def get_render_aisle_location_label_use_case(
    location_repo=Depends(get_aisle_location_repo),
    label_repo=Depends(get_aisle_location_label_repo),
    artifact_repo=Depends(get_aisle_location_label_artifact_repo),
    inventory_repo=Depends(get_inventory_repo),
    aisle_repo=Depends(get_aisle_repo),
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
    clock: Clock = Depends(get_clock),
):
    from src.application.services.positioning_label_renderer import PositioningLabelRenderer
    from src.application.use_cases.aisle_locations.render_aisle_location_labels import (
        RenderAisleLocationLabelUseCase,
    )

    container = get_app_container()
    return RenderAisleLocationLabelUseCase(
        location_repo=location_repo,
        label_repo=label_repo,
        artifact_repo=artifact_repo,
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        artifact_store=container.get_artifact_store(),
        renderer=PositioningLabelRenderer(),
        access_policy=access_policy,
        clock=clock,
    )


def get_download_aisle_location_label_use_case(
    render_uc=Depends(get_render_aisle_location_label_use_case),
    label_repo=Depends(get_aisle_location_label_repo),
):
    from src.application.use_cases.aisle_locations.render_aisle_location_labels import (
        DownloadAisleLocationLabelUseCase,
    )

    return DownloadAisleLocationLabelUseCase(
        render_use_case=render_uc,
        label_repo=label_repo,
        artifact_store=get_app_container().get_artifact_store(),
    )


def get_get_aisle_location_label_use_case(
    location_repo=Depends(get_aisle_location_repo),
    label_repo=Depends(get_aisle_location_label_repo),
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
):
    from src.application.use_cases.aisle_locations.render_aisle_location_labels import (
        GetAisleLocationLabelUseCase,
    )

    return GetAisleLocationLabelUseCase(
        location_repo=location_repo,
        label_repo=label_repo,
        access_policy=access_policy,
    )


def get_replace_aisle_location_label_use_case(
    location_repo=Depends(get_aisle_location_repo),
    label_repo=Depends(get_aisle_location_label_repo),
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
    clock: Clock = Depends(get_clock),
):
    from src.application.ports.aisle_location_repository import (
        AisleLocationLabelReplaceUnitOfWork,
    )
    from src.application.services.positioning_label_signing import (
        PositioningLabelSigningConfig,
        PositioningLabelSigningService,
        parse_previous_secrets,
    )
    from src.application.use_cases.aisle_locations.render_aisle_location_labels import (
        ReplaceAisleLocationLabelUseCase,
    )
    from src.config import load_settings
    from src.infrastructure.persistence.sql_aisle_location_label_replace_uow import (
        MemoryAisleLocationLabelReplaceUnitOfWork,
        SqlAisleLocationLabelReplaceUnitOfWork,
    )
    from src.infrastructure.repositories.memory_aisle_location_repository import (
        MemoryAisleLocationLabelRepository,
    )

    settings = load_settings()
    signing = PositioningLabelSigningService(
        PositioningLabelSigningConfig(
            secret=settings.positioning_label_hmac_secret or None,
            key_version=int(settings.positioning_label_hmac_key_version),
            previous_secrets=parse_previous_secrets(
                settings.positioning_label_hmac_previous_secrets
            ),
            required=bool(settings.positioning_label_signing_required),
        )
    )
    container = get_app_container()
    replace_uow: AisleLocationLabelReplaceUnitOfWork
    if container.is_sql_repository_backend():
        replace_uow = SqlAisleLocationLabelReplaceUnitOfWork(container._get_v3_sql_client())
    else:
        if not isinstance(label_repo, MemoryAisleLocationLabelRepository):
            raise RuntimeError("Memory replace UoW requires MemoryAisleLocationLabelRepository")
        replace_uow = MemoryAisleLocationLabelReplaceUnitOfWork(label_repo)
    return ReplaceAisleLocationLabelUseCase(
        location_repo=location_repo,
        label_repo=label_repo,
        replace_uow=replace_uow,
        access_policy=access_policy,
        clock=clock,
        signing=signing,
    )


def get_batch_render_aisle_location_labels_use_case(
    location_repo=Depends(get_aisle_location_repo),
    label_repo=Depends(get_aisle_location_label_repo),
    issue_uc=Depends(get_issue_aisle_location_label_use_case),
    inventory_repo=Depends(get_inventory_repo),
    aisle_repo=Depends(get_aisle_repo),
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
    clock: Clock = Depends(get_clock),
):
    from src.application.services.positioning_label_renderer import PositioningLabelRenderer
    from src.application.use_cases.aisle_locations.render_aisle_location_labels import (
        BatchRenderAisleLocationLabelsUseCase,
    )
    from src.config import load_settings

    settings = load_settings()
    max_batch = min(
        int(settings.position_label_max_batch_size),
        int(settings.position_label_batch_sync_limit),
    )
    return BatchRenderAisleLocationLabelsUseCase(
        location_repo=location_repo,
        label_repo=label_repo,
        issue_use_case=issue_uc,
        access_policy=access_policy,
        renderer=PositioningLabelRenderer(),
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        artifact_store=get_app_container().get_artifact_store(),
        clock=clock,
        max_batch_size=max_batch,
        max_pdf_bytes=int(settings.position_label_max_pdf_bytes),
    )


def get_list_aisle_location_labels_use_case(
    location_repo=Depends(get_aisle_location_repo),
    label_repo=Depends(get_aisle_location_label_repo),
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
):
    from src.application.use_cases.aisle_locations.manage_aisle_locations import (
        ListAisleLocationLabelsUseCase,
    )

    return ListAisleLocationLabelsUseCase(
        location_repo=location_repo,
        label_repo=label_repo,
        access_policy=access_policy,
    )


def get_invalidate_aisle_location_label_use_case(
    location_repo=Depends(get_aisle_location_repo),
    label_repo=Depends(get_aisle_location_label_repo),
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.aisle_locations.manage_aisle_locations import (
        InvalidateAisleLocationLabelUseCase,
    )

    return InvalidateAisleLocationLabelUseCase(
        location_repo=location_repo,
        label_repo=label_repo,
        access_policy=access_policy,
        clock=clock,
    )
