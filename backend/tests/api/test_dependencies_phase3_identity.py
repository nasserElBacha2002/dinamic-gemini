"""Regression coverage for Phase 2 correction and Phase 3 dependency facade."""

import pytest

import src.api.dependencies as public_dependencies
from src.api.deps import aisles, capture, infrastructure, locations

PHASE2_CORRECTION_SYMBOLS = ("get_result_context_resolver",)

CAPTURE_SYMBOLS = (
    "get_create_capture_session_use_case",
    "get_close_capture_session_use_case",
    "get_cancel_capture_session_use_case",
    "get_list_capture_sessions_use_case",
    "get_get_capture_session_detail_use_case",
    "get_capture_staging_time_metadata_extractor",
    "get_upload_capture_session_staging_items_use_case",
    "get_update_capture_session_clock_offset_use_case",
    "get_compute_capture_session_assignment_preview_use_case",
    "get_compute_capture_session_groups_use_case",
    "get_get_capture_session_groups_use_case",
    "get_assign_capture_session_group_to_existing_aisle_use_case",
    "get_create_aisle_and_assign_capture_session_group_use_case",
    "get_compute_materialized_capture_session_group_preview_use_case",
    "get_materialize_capture_session_group_use_case",
    "get_materialize_capture_session_use_case",
    "get_create_ordered_capture_session_use_case",
    "get_get_ordered_capture_session_use_case",
    "get_seal_ordered_capture_session_use_case",
)

LOCATIONS_SYMBOLS = (
    "get_create_aisle_location_use_case",
    "get_list_aisle_locations_use_case",
    "get_get_aisle_location_use_case",
    "get_update_aisle_location_use_case",
    "get_issue_aisle_location_label_use_case",
    "get_render_aisle_location_label_use_case",
    "get_download_aisle_location_label_use_case",
    "get_get_aisle_location_label_use_case",
    "get_replace_aisle_location_label_use_case",
    "get_batch_render_aisle_location_labels_use_case",
    "get_list_aisle_location_labels_use_case",
    "get_invalidate_aisle_location_label_use_case",
)


@pytest.mark.parametrize("symbol", PHASE2_CORRECTION_SYMBOLS)
def test_phase2_correction_result_context_resolver_facade_identity(symbol: str) -> None:
    assert getattr(public_dependencies, symbol) is getattr(infrastructure, symbol)


def test_structural_aisle_create_provider_facade_identity() -> None:
    assert public_dependencies.get_create_aisle_use_case is aisles.get_create_aisle_use_case


@pytest.mark.parametrize(
    ("implementation_module", "symbol"),
    [
        *((capture, symbol) for symbol in CAPTURE_SYMBOLS),
        *((locations, symbol) for symbol in LOCATIONS_SYMBOLS),
    ],
)
def test_phase3_public_dependency_facade_preserves_callable_identity(
    implementation_module: object,
    symbol: str,
) -> None:
    assert getattr(public_dependencies, symbol) is getattr(implementation_module, symbol)
