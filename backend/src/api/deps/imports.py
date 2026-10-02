"""Local CSV, package, and scanner import API dependency providers.

Implementation is mechanically extracted from src.api.dependencies. The
historical module remains the public compatibility facade.
"""

from __future__ import annotations

from fastapi import Depends

from src.api.deps.aisles import get_create_aisle_use_case
from src.api.deps.infrastructure import get_artifact_storage, get_inventory_status_reconciler
from src.application.ports.clock import Clock
from src.application.ports.local_csv_import_repository import LocalCsvImportRepository
from src.application.ports.repositories import (
    AisleRepository,
    ClientSupplierRepository,
    InventoryRepository,
    PositionRepository,
    ProductRecordRepository,
    SourceAssetRepository,
)
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.use_cases.aisles.create_aisle import CreateAisleUseCase
from src.runtime.app_container import get_app_container
from src.runtime.import_composition import (
    _build_import_canonical_position_materializer,
    build_confirm_local_csv_import,
)
from src.runtime.v3_deps import (
    get_aisle_repo,
    get_client_supplier_repo,
    get_clock,
    get_inventory_repo,
    get_position_repo,
    get_product_record_repo,
    get_source_asset_repo,
)


def _build_preview_local_csv_import(
    *,
    inventory_repo: InventoryRepository,
    aisle_repo: AisleRepository,
    import_repo: LocalCsvImportRepository,
    clock: Clock,
    enabled: bool,
):
    from src.application.services.supplier_local_csv_row_revalidator import (
        build_supplier_local_csv_row_revalidator,
    )
    from src.application.use_cases.inventories.manage_local_csv_import import (
        PreviewLocalCsvImport,
    )

    container = get_app_container()
    return PreviewLocalCsvImport(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        import_repo=import_repo,
        clock=clock,
        enabled=enabled,
        supplier_revalidator=build_supplier_local_csv_row_revalidator(
            inventory_repo=inventory_repo,
            aisle_repo=aisle_repo,
            client_supplier_repo=container.get_client_supplier_repo(),
            extraction_profile_repo=container.get_supplier_extraction_profile_repo(),
        ),
    )


def _dinamic_scanner_txt_import_enabled(settings) -> bool:
    return bool(getattr(settings, "server_dinamic_scanner_txt_import_enabled", False))


def _csv_import_pipeline_enabled(settings) -> bool:
    return (
        bool(getattr(settings, "server_csv_import_enabled", False))
        or bool(getattr(settings, "server_local_inventory_package_enabled", False))
        or _dinamic_scanner_txt_import_enabled(settings)
    )


def get_preview_local_csv_import_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    clock: Clock = Depends(get_clock),
):
    from src.config import load_settings

    settings = load_settings()
    return _build_preview_local_csv_import(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        import_repo=get_app_container().get_local_csv_import_repo(),
        clock=clock,
        enabled=bool(getattr(settings, "server_csv_import_enabled", False)),
    )


def get_confirm_local_csv_import_use_case(
    clock: Clock = Depends(get_clock),
    position_repo: PositionRepository = Depends(get_position_repo),
    product_record_repo: ProductRecordRepository = Depends(get_product_record_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    status_reconciler: InventoryStatusReconciler = Depends(get_inventory_status_reconciler),
):
    return build_confirm_local_csv_import(
        container=get_app_container(),
        clock=clock,
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        product_record_repo=product_record_repo,
        status_reconciler=status_reconciler,
    )


def get_get_local_csv_import_use_case():
    from src.application.use_cases.inventories.manage_local_csv_import import GetLocalCsvImport
    from src.config import load_settings

    settings = load_settings()
    return GetLocalCsvImport(
        import_repo=get_app_container().get_local_csv_import_repo(),
        enabled=bool(getattr(settings, "server_csv_import_enabled", False)),
    )


def get_preview_local_inventory_package_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    clock: Clock = Depends(get_clock),
):
    from pathlib import Path

    from src.application.use_cases.inventories.manage_local_inventory_package import (
        PreviewLocalInventoryPackage,
    )
    from src.config import load_settings

    settings = load_settings()
    container = get_app_container()
    csv_repo = container.get_local_csv_import_repo()
    csv_preview = _build_preview_local_csv_import(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        import_repo=csv_repo,
        clock=clock,
        enabled=bool(getattr(settings, "server_csv_import_enabled", False))
        or bool(getattr(settings, "server_local_inventory_package_enabled", False)),
    )
    staging_root = Path(getattr(settings, "output_dir", "/tmp")) / "local_inventory_packages"
    return PreviewLocalInventoryPackage(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        csv_import_repo=csv_repo,
        package_repo=container.get_local_inventory_package_repo(),
        csv_preview=csv_preview,
        clock=clock,
        enabled=bool(getattr(settings, "server_local_inventory_package_enabled", False)),
        staging_root=staging_root,
    )


def get_confirm_local_inventory_package_use_case(
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    asset_repo: SourceAssetRepository = Depends(get_source_asset_repo),
    artifact_storage=Depends(get_artifact_storage),
    status_reconciler: InventoryStatusReconciler = Depends(get_inventory_status_reconciler),
    clock: Clock = Depends(get_clock),
    position_repo: PositionRepository = Depends(get_position_repo),
    product_record_repo: ProductRecordRepository = Depends(get_product_record_repo),
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
):
    from src.application.services.aisle_source_asset_materializer import (
        AisleSourceAssetMaterializer,
    )
    from src.application.services.local_csv_position_materializer import (
        LocalCsvPositionMaterializer,
    )
    from src.application.services.positioning_label_signing import (
        PositioningLabelSigningConfig,
        PositioningLabelSigningService,
        parse_previous_secrets,
    )
    from src.application.services.product_labels.issued_product_label_resolver import (
        IssuedProductLabelResolver,
    )
    from src.application.use_cases.inventories.manage_local_inventory_package import (
        ConfirmLocalInventoryPackage,
    )
    from src.config import load_settings

    settings = load_settings()
    container = get_app_container()
    materializer = AisleSourceAssetMaterializer(
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        artifact_storage=artifact_storage,
        status_reconciler=status_reconciler,
    )
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
    return ConfirmLocalInventoryPackage(
        package_repo=container.get_local_inventory_package_repo(),
        result_writer=container.get_local_csv_result_writer(),
        materializer=materializer,
        aisle_repo=aisle_repo,
        inventory_repo=inventory_repo,
        clock=clock,
        enabled=bool(getattr(settings, "server_local_inventory_package_enabled", False)),
        position_materializer=LocalCsvPositionMaterializer(
            position_repo=position_repo,
            product_record_repo=product_record_repo,
            counted_product_label_repo=container.get_counted_product_label_repo(),
            issued_label_resolver=IssuedProductLabelResolver(
                issued_repo=container.get_issued_product_label_repo()
            ),
            inventory_repo=inventory_repo,
            client_position_label_repo=container.get_client_position_label_repo(),
            positioning_signing=signing if signing.can_sign else None,
        ),
        canonical_position_materializer=_build_import_canonical_position_materializer(container),
        materialization_lease_sec=int(settings.local_csv_import_recovery_lease_sec),
    )


def get_get_local_inventory_package_use_case():
    from src.application.use_cases.inventories.manage_local_inventory_package import (
        GetLocalInventoryPackage,
    )
    from src.config import load_settings

    settings = load_settings()
    return GetLocalInventoryPackage(
        package_repo=get_app_container().get_local_inventory_package_repo(),
        enabled=bool(getattr(settings, "server_local_inventory_package_enabled", False)),
    )


def get_preview_dinamic_scanner_txt_import_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
    clock: Clock = Depends(get_clock),
    create_aisle: CreateAisleUseCase = Depends(get_create_aisle_use_case),
):
    from src.application.services.dinamic_scanner_aisle_resolver import DinamicScannerAisleResolver
    from src.application.services.label_profile_resolver import LabelProfileResolver
    from src.application.use_cases.inventories.manage_dinamic_scanner_txt_import import (
        PreviewDinamicScannerTxtImport,
    )
    from src.config import load_settings

    settings = load_settings()
    container = get_app_container()
    csv_preview = _build_preview_local_csv_import(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        import_repo=container.get_local_csv_import_repo(),
        clock=clock,
        enabled=_csv_import_pipeline_enabled(settings),
    )
    aisle_resolver = DinamicScannerAisleResolver(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        client_supplier_repo=client_supplier_repo,
        create_aisle=create_aisle,
    )
    label_profile_resolver = LabelProfileResolver(
        label_profile_repo=container.get_client_supplier_label_profile_repo(),
        client_supplier_repo=client_supplier_repo,
        extraction_profile_repo=container.get_supplier_extraction_profile_repo(),
    )
    return PreviewDinamicScannerTxtImport(
        inventory_repo=inventory_repo,
        aisle_resolver=aisle_resolver,
        import_repo=container.get_local_csv_import_repo(),
        csv_preview=csv_preview,
        clock=clock,
        enabled=_dinamic_scanner_txt_import_enabled(settings),
        max_lines=int(getattr(settings, "server_dinamic_scanner_txt_max_lines", 50_000)),
        max_line_length=int(getattr(settings, "server_dinamic_scanner_txt_max_line_length", 512)),
        label_profile_resolver=label_profile_resolver,
        extraction_profile_repo=container.get_supplier_extraction_profile_repo(),
    )


def get_confirm_dinamic_scanner_txt_import_use_case(
    clock: Clock = Depends(get_clock),
    position_repo: PositionRepository = Depends(get_position_repo),
    product_record_repo: ProductRecordRepository = Depends(get_product_record_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
    status_reconciler: InventoryStatusReconciler = Depends(get_inventory_status_reconciler),
    create_aisle: CreateAisleUseCase = Depends(get_create_aisle_use_case),
):
    from src.application.services.dinamic_scanner_aisle_resolver import DinamicScannerAisleResolver
    from src.application.use_cases.inventories.manage_dinamic_scanner_txt_import import (
        ConfirmDinamicScannerTxtImport,
    )
    from src.config import load_settings

    settings = load_settings()
    container = get_app_container()
    csv_confirm = build_confirm_local_csv_import(
        container=container,
        clock=clock,
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        product_record_repo=product_record_repo,
        status_reconciler=status_reconciler,
        enabled=_csv_import_pipeline_enabled(settings),
    )
    aisle_resolver = DinamicScannerAisleResolver(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        client_supplier_repo=client_supplier_repo,
        create_aisle=create_aisle,
    )
    return ConfirmDinamicScannerTxtImport(
        import_repo=container.get_local_csv_import_repo(),
        aisle_resolver=aisle_resolver,
        csv_confirm=csv_confirm,
        enabled=_dinamic_scanner_txt_import_enabled(settings),
    )
