"""Capture session and ordered capture API dependency providers.

Implementation is mechanically extracted from src.api.dependencies. The
historical module remains the public compatibility facade.
"""

from __future__ import annotations

from fastapi import Depends

from src.api.deps.aisles import get_create_aisle_use_case
from src.api.deps.infrastructure import get_artifact_storage, get_inventory_status_reconciler
from src.api.deps.security import get_capture_session_access_policy, get_inventory_access_policy
from src.application.ports.capture_repositories import (
    CaptureSessionConfirmIdempotencyRepository,
    CaptureSessionGroupRepository,
    CaptureSessionItemRepository,
    CaptureSessionRepository,
)
from src.application.ports.clock import Clock
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    PositionRepository,
    SourceAssetRepository,
)
from src.application.services.inventory_access_policy import InventoryAccessPolicy
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.use_cases.aisles.create_aisle import CreateAisleUseCase
from src.runtime.v3_deps import (
    get_aisle_repo,
    get_capture_session_confirm_repo,
    get_capture_session_group_repo,
    get_capture_session_item_repo,
    get_capture_session_repo,
    get_clock,
    get_inventory_repo,
    get_ordered_capture_session_repo,
    get_position_repo,
    get_source_asset_repo,
)


def get_create_capture_session_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    session_repo: CaptureSessionRepository = Depends(get_capture_session_repo),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.capture_sessions.create_capture_session import (
        CreateCaptureSessionUseCase,
    )
    from src.config import load_settings

    s = load_settings()
    return CreateCaptureSessionUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        session_repo=session_repo,
        clock=clock,
        max_open_sessions_per_aisle=s.v3_capture_max_open_sessions_per_aisle,
    )


def get_close_capture_session_use_case(
    session_repo: CaptureSessionRepository = Depends(get_capture_session_repo),
    item_repo: CaptureSessionItemRepository = Depends(get_capture_session_item_repo),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.capture_sessions.close_capture_session import (
        CloseCaptureSessionUseCase,
    )

    return CloseCaptureSessionUseCase(session_repo=session_repo, item_repo=item_repo, clock=clock)


def get_cancel_capture_session_use_case(
    session_repo: CaptureSessionRepository = Depends(get_capture_session_repo),
    item_repo: CaptureSessionItemRepository = Depends(get_capture_session_item_repo),
    artifact_storage=Depends(get_artifact_storage),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.capture_sessions.cancel_capture_session import (
        CancelCaptureSessionUseCase,
    )

    return CancelCaptureSessionUseCase(
        session_repo=session_repo,
        item_repo=item_repo,
        artifact_storage=artifact_storage,
        clock=clock,
    )


def get_list_capture_sessions_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    session_repo: CaptureSessionRepository = Depends(get_capture_session_repo),
):
    from src.application.use_cases.capture_sessions.list_capture_sessions import (
        ListCaptureSessionsUseCase,
    )
    from src.config import load_settings

    s = load_settings()
    return ListCaptureSessionsUseCase(
        inventory_repo=inventory_repo,
        session_repo=session_repo,
        default_page_size=s.v3_capture_session_list_default_page_size,
        max_page_size=s.v3_capture_session_list_max_page_size,
    )


def get_get_capture_session_detail_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    session_repo: CaptureSessionRepository = Depends(get_capture_session_repo),
    item_repo: CaptureSessionItemRepository = Depends(get_capture_session_item_repo),
):
    from src.application.use_cases.capture_sessions.get_capture_session_detail import (
        GetCaptureSessionDetailUseCase,
    )

    return GetCaptureSessionDetailUseCase(
        inventory_repo=inventory_repo,
        session_repo=session_repo,
        item_repo=item_repo,
    )


def get_capture_staging_time_metadata_extractor():
    from src.application.services.capture_staging_time_metadata import (
        PillowCaptureStagingTimeMetadataExtractor,
    )
    from src.config import load_settings

    s = load_settings()
    return PillowCaptureStagingTimeMetadataExtractor(
        confidence_exif=s.v3_capture_time_confidence_exif,
        confidence_mtime=s.v3_capture_time_confidence_mtime,
        confidence_fallback=s.v3_capture_time_confidence_fallback,
    )


def get_upload_capture_session_staging_items_use_case(
    session_repo: CaptureSessionRepository = Depends(get_capture_session_repo),
    item_repo: CaptureSessionItemRepository = Depends(get_capture_session_item_repo),
    artifact_storage=Depends(get_artifact_storage),
    clock: Clock = Depends(get_clock),
    time_metadata_extractor=Depends(get_capture_staging_time_metadata_extractor),
    access_policy: InventoryAccessPolicy = Depends(get_capture_session_access_policy),
):
    from src.application.services.upload_request_limits import UploadRequestLimitPolicy
    from src.application.use_cases.capture_sessions.upload_capture_session_staging_items import (
        UploadCaptureSessionStagingItemsUseCase,
    )
    from src.config import load_settings

    s = load_settings()
    policy = UploadRequestLimitPolicy.from_settings(s)
    return UploadCaptureSessionStagingItemsUseCase(
        session_repo=session_repo,
        item_repo=item_repo,
        artifact_storage=artifact_storage,
        clock=clock,
        staging_prefix=s.v3_capture_staging_storage_prefix,
        max_upload_bytes=policy.max_file_size_bytes,
        time_metadata_extractor=time_metadata_extractor,
        access_policy=access_policy,
        upload_policy=policy,
    )


def get_update_capture_session_clock_offset_use_case(
    session_repo: CaptureSessionRepository = Depends(get_capture_session_repo),
    item_repo: CaptureSessionItemRepository = Depends(get_capture_session_item_repo),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.capture_sessions.update_capture_session_clock_offset import (
        UpdateCaptureSessionClockOffsetUseCase,
    )
    from src.config import load_settings

    s = load_settings()
    return UpdateCaptureSessionClockOffsetUseCase(
        session_repo=session_repo,
        item_repo=item_repo,
        clock=clock,
        min_offset_seconds=s.v3_capture_clock_offset_min_seconds,
        max_offset_seconds=s.v3_capture_clock_offset_max_seconds,
    )


def get_compute_capture_session_assignment_preview_use_case(
    session_repo: CaptureSessionRepository = Depends(get_capture_session_repo),
    item_repo: CaptureSessionItemRepository = Depends(get_capture_session_item_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.capture_sessions.compute_capture_session_assignment_preview import (
        ComputeCaptureSessionAssignmentPreviewUseCase,
    )
    from src.config import load_settings

    s = load_settings()
    return ComputeCaptureSessionAssignmentPreviewUseCase(
        session_repo=session_repo,
        item_repo=item_repo,
        position_repo=position_repo,
        clock=clock,
        preview_max_positions=s.v3_capture_preview_max_positions,
    )


def get_compute_capture_session_groups_use_case(
    session_repo: CaptureSessionRepository = Depends(get_capture_session_repo),
    item_repo: CaptureSessionItemRepository = Depends(get_capture_session_item_repo),
    group_repo: CaptureSessionGroupRepository = Depends(get_capture_session_group_repo),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.capture_sessions.compute_capture_session_groups import (
        ComputeCaptureSessionGroupsUseCase,
    )
    from src.config import load_settings

    s = load_settings()
    return ComputeCaptureSessionGroupsUseCase(
        session_repo=session_repo,
        item_repo=item_repo,
        group_repo=group_repo,
        clock=clock,
        max_time_gap_seconds=s.v3_capture_grouping_max_gap_seconds,
    )


def get_get_capture_session_groups_use_case(
    session_repo: CaptureSessionRepository = Depends(get_capture_session_repo),
    group_repo: CaptureSessionGroupRepository = Depends(get_capture_session_group_repo),
):
    from src.application.use_cases.capture_sessions.get_capture_session_groups import (
        GetCaptureSessionGroupsUseCase,
    )

    return GetCaptureSessionGroupsUseCase(session_repo=session_repo, group_repo=group_repo)


def get_assign_capture_session_group_to_existing_aisle_use_case(
    session_repo: CaptureSessionRepository = Depends(get_capture_session_repo),
    group_repo: CaptureSessionGroupRepository = Depends(get_capture_session_group_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.capture_sessions.assign_capture_session_group_to_existing_aisle import (
        AssignCaptureSessionGroupToExistingAisleUseCase,
    )

    return AssignCaptureSessionGroupToExistingAisleUseCase(
        session_repo=session_repo,
        group_repo=group_repo,
        aisle_repo=aisle_repo,
        clock=clock,
    )


def get_create_aisle_and_assign_capture_session_group_use_case(
    session_repo: CaptureSessionRepository = Depends(get_capture_session_repo),
    group_repo: CaptureSessionGroupRepository = Depends(get_capture_session_group_repo),
    create_aisle: CreateAisleUseCase = Depends(get_create_aisle_use_case),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.capture_sessions.create_aisle_and_assign_capture_session_group import (
        CreateAisleAndAssignCaptureSessionGroupUseCase,
    )

    return CreateAisleAndAssignCaptureSessionGroupUseCase(
        session_repo=session_repo,
        group_repo=group_repo,
        create_aisle=create_aisle,
        clock=clock,
    )


def get_compute_materialized_capture_session_group_preview_use_case(
    session_repo: CaptureSessionRepository = Depends(get_capture_session_repo),
    group_repo: CaptureSessionGroupRepository = Depends(get_capture_session_group_repo),
    item_repo: CaptureSessionItemRepository = Depends(get_capture_session_item_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    asset_repo: SourceAssetRepository = Depends(get_source_asset_repo),
):
    from src.application.use_cases.capture_sessions.compute_materialized_capture_session_group_preview import (
        ComputeMaterializedCaptureSessionGroupPreviewUseCase,
    )
    from src.config import load_settings

    s = load_settings()
    return ComputeMaterializedCaptureSessionGroupPreviewUseCase(
        session_repo=session_repo,
        group_repo=group_repo,
        item_repo=item_repo,
        position_repo=position_repo,
        asset_repo=asset_repo,
        preview_max_positions=s.v3_capture_preview_max_positions,
    )


def get_materialize_capture_session_group_use_case(
    session_repo: CaptureSessionRepository = Depends(get_capture_session_repo),
    group_repo: CaptureSessionGroupRepository = Depends(get_capture_session_group_repo),
    item_repo: CaptureSessionItemRepository = Depends(get_capture_session_item_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    asset_repo: SourceAssetRepository = Depends(get_source_asset_repo),
    artifact_storage=Depends(get_artifact_storage),
    status_reconciler: InventoryStatusReconciler = Depends(get_inventory_status_reconciler),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.capture_sessions.materialize_capture_session_group import (
        MaterializeCaptureSessionGroupUseCase,
    )

    return MaterializeCaptureSessionGroupUseCase(
        session_repo=session_repo,
        group_repo=group_repo,
        item_repo=item_repo,
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        artifact_storage=artifact_storage,
        status_reconciler=status_reconciler,
        clock=clock,
    )


def get_materialize_capture_session_use_case(
    session_repo: CaptureSessionRepository = Depends(get_capture_session_repo),
    item_repo: CaptureSessionItemRepository = Depends(get_capture_session_item_repo),
    confirm_repo: CaptureSessionConfirmIdempotencyRepository = Depends(
        get_capture_session_confirm_repo
    ),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    asset_repo: SourceAssetRepository = Depends(get_source_asset_repo),
    artifact_storage=Depends(get_artifact_storage),
    status_reconciler: InventoryStatusReconciler = Depends(get_inventory_status_reconciler),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.capture_sessions.materialize_capture_session import (
        MaterializeCaptureSessionUseCase,
    )

    return MaterializeCaptureSessionUseCase(
        session_repo=session_repo,
        item_repo=item_repo,
        confirm_repo=confirm_repo,
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        artifact_storage=artifact_storage,
        status_reconciler=status_reconciler,
        clock=clock,
    )


def get_create_ordered_capture_session_use_case(
    session_repo=Depends(get_ordered_capture_session_repo),
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.ordered_capture.manage_ordered_capture_session import (
        CreateOrderedCaptureSessionUseCase,
    )

    return CreateOrderedCaptureSessionUseCase(
        session_repo=session_repo,
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        access_policy=access_policy,
        clock=clock,
    )


def get_get_ordered_capture_session_use_case(
    session_repo=Depends(get_ordered_capture_session_repo),
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
):
    from src.application.use_cases.ordered_capture.manage_ordered_capture_session import (
        GetOrderedCaptureSessionUseCase,
    )

    return GetOrderedCaptureSessionUseCase(
        session_repo=session_repo,
        access_policy=access_policy,
    )


def get_seal_ordered_capture_session_use_case(
    session_repo=Depends(get_ordered_capture_session_repo),
    asset_repo: SourceAssetRepository = Depends(get_source_asset_repo),
    access_policy: InventoryAccessPolicy = Depends(get_inventory_access_policy),
    clock: Clock = Depends(get_clock),
):
    from src.application.use_cases.ordered_capture.manage_ordered_capture_session import (
        SealOrderedCaptureSessionUseCase,
    )

    return SealOrderedCaptureSessionUseCase(
        session_repo=session_repo,
        asset_repo=asset_repo,
        access_policy=access_policy,
        clock=clock,
    )
