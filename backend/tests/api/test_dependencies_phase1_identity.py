"""Regression coverage for the Phase 1 dependency compatibility facade."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import src.api.dependencies as public_dependencies
import src.config as config_module
from src.api.deps import infrastructure, security
from src.config import load_settings
from src.runtime.app_container import AppContainer

INFRASTRUCTURE_SYMBOLS = (
    "get_artifact_storage",
    "get_worker_launch_service_dep",
    "get_job_stale_reconciler",
    "get_finalization_assessment_service",
    "get_artifact_publication_outbox_store",
    "get_artifact_manifest_store",
    "get_supplier_extraction_profile_repo",
    "get_client_supplier_label_profile_repo",
    "get_result_evidence_repo",
    "get_result_evidence_query_service",
    "get_operational_execution_config_resolver",
    "get_job_source_asset_repo",
    "get_manual_image_coverage_repo",
    "get_job_image_coverage_repo",
    "get_manual_image_result_uow_factory",
    "get_processing_event_repo",
    "get_job_artifact_catalog_service",
    "get_job_retry_chain_service",
    "get_run_auditability_service",
    "get_observability_metrics_service",
    "get_aisle_location_label_artifact_repo",
    "get_image_position_label_detection_repo",
    "get_position_reconciliation_repo",
    "get_materialized_position_identity_reader",
    "get_client_position_label_repo",
    "get_manual_position_override_repo",
)

SECURITY_SYMBOLS = (
    "require_inventory_client_scope",
    "require_client_scope",
    "require_raspberry_device_token",
    "get_access_principal",
    "get_inventory_access_policy",
    "get_capture_session_access_policy",
    "require_capture_session_upload_scope",
)


@pytest.mark.parametrize(
    ("implementation_module", "symbol"),
    [
        *((infrastructure, symbol) for symbol in INFRASTRUCTURE_SYMBOLS),
        *((security, symbol) for symbol in SECURITY_SYMBOLS),
    ],
)
def test_phase1_public_dependency_facade_preserves_callable_identity(
    implementation_module: object,
    symbol: str,
) -> None:
    assert getattr(public_dependencies, symbol) is getattr(implementation_module, symbol)


def test_raspberry_device_guard_keeps_missing_and_invalid_token_behavior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "src.config.load_settings",
        lambda: SimpleNamespace(raspberry_device_token="expected-token"),
    )

    with pytest.raises(HTTPException) as missing:
        public_dependencies.require_raspberry_device_token(x_device_token=None)
    assert missing.value.status_code == 401
    assert missing.value.detail == "Raspberry device authentication is not configured or missing"

    with pytest.raises(HTTPException) as invalid:
        public_dependencies.require_raspberry_device_token(x_device_token="invalid-token")
    assert invalid.value.status_code == 401
    assert invalid.value.detail == "Invalid Raspberry device token"

    assert public_dependencies.require_raspberry_device_token(x_device_token="expected-token") is None


def test_app_container_deferred_csv_recovery_import_still_constructs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise the intentional AppContainer -> API lazy import without moving it."""
    monkeypatch.setattr(config_module, "_settings", None)
    container = AppContainer(load_settings())

    recovery_service = container.get_local_csv_import_recovery_service()

    assert recovery_service is container.get_local_csv_import_recovery_service()
