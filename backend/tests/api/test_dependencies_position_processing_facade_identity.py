"""Regression coverage for Phase 5 position/processing dependency facade."""

import pytest

import src.api.dependencies as public_dependencies
from src.api.deps import infrastructure, positions

POSITION_SYMBOLS = (
    "get_code_scanner",
    "get_source_asset_content_reader",
    "get_match_aisle_code_scan_detections_use_case",
    "get_run_aisle_code_scan_use_case",
    "get_list_aisle_code_scans_use_case",
    "get_summarize_aisle_code_scans_use_case",
    "get_get_position_code_scan_evidence_use_case",
    "get_get_aisle_code_scan_review_signals_use_case",
    "get_export_aisle_code_scans_use_case",
    "get_list_aisle_positions_use_case",
    "get_list_review_queue_use_case",
    "get_get_position_detail_use_case",
    "get_confirm_position_use_case",
    "get_update_product_quantity_use_case",
    "get_update_product_sku_use_case",
    "get_update_position_code_use_case",
    "get_mark_position_unknown_use_case",
    "get_mark_position_image_mismatch_use_case",
    "get_delete_position_use_case",
    "get_preview_merge_positions_use_case",
    "get_confirm_merge_positions_use_case",
    "get_list_job_image_results_use_case",
    "get_processing_action_idempotency_service",
    "get_list_asset_processing_use_case",
    "get_get_asset_processing_detail_use_case",
    "get_list_processing_events_use_case",
    "get_reprocess_asset_use_case",
    "get_retry_asset_persistence_use_case",
    "get_send_asset_to_external_use_case",
    "get_invalidate_asset_result_use_case",
    "get_single_asset_command_executor",
    "get_create_manual_image_result_use_case",
    "get_position_override_scope_resolver",
    "get_effective_position_reader",
    "get_manage_position_override_use_case",
    "get_list_position_override_history_use_case",
    "get_reconcile_job_positions_use_case",
    "get_aisle_operational_positioning_view_use_case",
    "get_aisle_positioning_sequence_use_case",
    "get_reprocess_aisle_positioning_use_case",
)

INFRASTRUCTURE_RELOCATION_SYMBOLS = ("get_position_materialization_service",)


@pytest.mark.parametrize(
    ("implementation_module", "symbol"),
    [
        *((positions, symbol) for symbol in POSITION_SYMBOLS),
        *((infrastructure, symbol) for symbol in INFRASTRUCTURE_RELOCATION_SYMBOLS),
    ],
)
def test_phase5_public_dependency_facade_preserves_callable_identity(
    implementation_module: object,
    symbol: str,
) -> None:
    assert getattr(public_dependencies, symbol) is getattr(implementation_module, symbol)


def test_phase5_modules_import_without_facade_reverse_dependency() -> None:
    import src.api.deps.infrastructure as infrastructure_module
    import src.api.deps.positions as positions_module

    assert "src.api.dependencies" not in positions_module.__dict__
    assert "src.api.dependencies" not in infrastructure_module.__dict__
