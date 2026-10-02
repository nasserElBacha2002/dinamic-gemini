"""Regression coverage for Phase 4 aisle and import dependency facade."""

import pytest

import src.api.dependencies as public_dependencies
from src.api.deps import aisles, imports

AISLE_SYMBOLS = (
    "get_create_aisle_use_case",
    "get_aisle_review_lifecycle_sync",
    "get_aisle_identification_configuration_query",
    "get_update_aisle_code_use_case",
    "get_deactivate_aisle_use_case",
    "get_activate_aisle_use_case",
    "get_list_aisles_by_inventory_use_case",
    "get_list_aisles_with_status_use_case",
    "get_aisle_job_launch_service",
    "get_start_aisle_processing_use_case",
    "get_get_aisle_processing_status_use_case",
    "get_cancel_aisle_job_use_case",
    "get_recover_stale_job_use_case",
    "get_recover_aisle_processing_use_case",
    "get_retry_aisle_job_use_case",
    "get_upload_aisle_assets_use_case",
    "get_list_aisle_assets_use_case",
    "get_upsert_preliminary_detection_use_case",
    "get_persist_authoritative_local_code_scan_use_case",
    "get_evaluate_authoritative_aisle_readiness",
    "get_finalize_authoritative_aisle_use_case",
    "get_reconcile_preliminary_detections_use_case",
    "get_process_preliminary_reconciliations_use_case",
    "get_list_preliminary_reconciliations_use_case",
    "get_delete_aisle_source_asset_use_case",
    "get_run_aisle_merge_use_case",
    "get_get_aisle_merge_results_use_case",
    "get_list_aisle_jobs_use_case",
    "get_resolve_aisle_job_for_inventory_read_use_case",
)

IMPORT_SYMBOLS = (
    "build_confirm_local_csv_import",
    "get_preview_local_csv_import_use_case",
    "get_confirm_local_csv_import_use_case",
    "get_get_local_csv_import_use_case",
    "get_preview_local_inventory_package_use_case",
    "get_confirm_local_inventory_package_use_case",
    "get_get_local_inventory_package_use_case",
    "get_preview_dinamic_scanner_txt_import_use_case",
    "get_confirm_dinamic_scanner_txt_import_use_case",
)


@pytest.mark.parametrize(
    ("implementation_module", "symbol"),
    [
        *((aisles, symbol) for symbol in AISLE_SYMBOLS),
        *((imports, symbol) for symbol in IMPORT_SYMBOLS),
    ],
)
def test_phase4_public_dependency_facade_preserves_callable_identity(
    implementation_module: object,
    symbol: str,
) -> None:
    assert getattr(public_dependencies, symbol) is getattr(implementation_module, symbol)


def test_phase4_modules_import_without_facade_reverse_dependency() -> None:
    import src.api.deps.aisles as aisles_module
    import src.api.deps.imports as imports_module

    assert "src.api.dependencies" not in aisles_module.__dict__
    assert "src.api.dependencies" not in imports_module.__dict__
