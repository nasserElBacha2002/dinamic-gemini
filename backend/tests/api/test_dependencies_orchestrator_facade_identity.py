"""Regression coverage for the orchestrator dependency compatibility facade."""

import pytest

import src.api.dependencies as public_dependencies
from src.api.deps import analytics, inventory

INVENTORY_SYMBOLS = (
    "get_create_inventory_use_case",
    "get_update_inventory_name_use_case",
    "get_soft_delete_inventories_use_case",
    "get_list_inventories_use_case",
    "get_list_inventory_list_items_use_case",
    "get_inventory_recognition_config_use_case",
    "get_client_recognition_config_use_case",
    "get_raspberry_recognition_config_use_case",
    "get_get_inventory_use_case",
    "get_get_client_use_case",
    "get_get_client_supplier_use_case",
    "get_export_inventory_results_use_case",
    "get_export_aisle_results_csv_use_case",
    "get_export_inventory_summary_csv_use_case",
    "get_export_inventory_package_zip_use_case",
    "get_export_aisle_business_csv_use_case",
    "get_get_inventory_metrics_use_case",
    "get_upload_supplier_reference_images_use_case",
    "get_list_supplier_reference_images_use_case",
    "get_get_supplier_reference_image_use_case",
    "get_delete_supplier_reference_image_use_case",
    "get_list_supplier_prompt_configs_use_case",
    "get_create_supplier_prompt_config_version_use_case",
    "get_get_active_supplier_prompt_config_use_case",
    "get_activate_supplier_prompt_config_version_use_case",
    "get_get_supplier_prompt_config_use_case",
    "get_list_supplier_extraction_profiles_use_case",
    "get_get_active_supplier_extraction_profile_use_case",
    "get_get_supplier_extraction_profile_by_version_use_case",
    "get_create_supplier_extraction_profile_version_use_case",
    "get_activate_supplier_extraction_profile_version_use_case",
    "get_test_label_recognition_code_use_case",
    "get_clone_supplier_extraction_profile_use_case",
    "get_list_supplier_reference_annotations_use_case",
    "get_replace_supplier_reference_annotations_use_case",
    "get_list_client_supplier_label_profiles_use_case",
    "get_upsert_client_supplier_label_profile_use_case",
    "get_create_client_use_case",
    "get_update_client_use_case",
    "get_create_client_supplier_use_case",
    "get_list_clients_use_case",
    "get_list_client_suppliers_use_case",
)

ANALYTICS_SYMBOLS = (
    "get_compare_aisle_runs_use_case",
    "get_compare_many_aisle_runs_use_case",
    "get_promote_aisle_operational_job_use_case",
    "get_export_aisle_benchmark_run_csv_use_case",
    "get_export_aisle_benchmark_compare_csv_use_case",
    "get_analytics_query_service",
    "get_analytics_cost_summary_service",
)


@pytest.mark.parametrize(
    ("implementation_module", "symbol"),
    [
        *((inventory, symbol) for symbol in INVENTORY_SYMBOLS),
        *((analytics, symbol) for symbol in ANALYTICS_SYMBOLS),
    ],
)
def test_phase2_public_dependency_facade_preserves_callable_identity(
    implementation_module: object,
    symbol: str,
) -> None:
    assert getattr(public_dependencies, symbol) is getattr(implementation_module, symbol)
