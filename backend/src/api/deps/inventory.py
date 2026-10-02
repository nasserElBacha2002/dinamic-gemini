"""Inventory, client, and supplier API dependency providers.

Implementation is mechanically extracted from src.api.dependencies. The
historical module remains the public compatibility facade.
"""

from __future__ import annotations

from fastapi import Depends

from src.api.deps.infrastructure import (
    get_artifact_storage,
    get_client_supplier_label_profile_repo,
    get_operational_execution_config_resolver,
    get_result_context_resolver,
    get_supplier_extraction_profile_repo,
)
from src.application.ports.clock import Clock
from src.application.ports.repositories import (
    AisleRepository,
    ClientRepository,
    ClientSupplierRepository,
    InventoryRepository,
    JobRepository,
    PositionRepository,
    ProductRecordRepository,
    SupplierPromptConfigRepository,
    SupplierReferenceImageRepository,
)
from src.application.ports.services import MetricsCalculator
from src.application.ports.supplier_extraction_profile_repository import (
    SupplierExtractionProfileRepository,
)
from src.application.services.operational_execution_config_resolver import (
    OperationalExecutionConfigResolver,
)
from src.application.services.result_context_resolver import ResultContextResolver
from src.application.use_cases.clients.create_client import CreateClientUseCase
from src.application.use_cases.clients.get_client import GetClientUseCase
from src.application.use_cases.clients.get_client_recognition_config import (
    GetClientRecognitionConfigUseCase,
)
from src.application.use_cases.clients.get_raspberry_recognition_config import (
    GetRaspberryRecognitionConfigUseCase,
)
from src.application.use_cases.clients.list_clients import ListClientsUseCase
from src.application.use_cases.clients.update_client import UpdateClientUseCase
from src.application.use_cases.inventories.create_inventory import CreateInventoryUseCase
from src.application.use_cases.inventories.export_inventory_business import (
    ExportAisleBusinessCsvUseCase,
    ExportInventoryPackageZipUseCase,
    ExportInventorySummaryCsvUseCase,
)
from src.application.use_cases.inventories.export_inventory_results import (
    ExportAisleResultsCsvUseCase,
    ExportInventoryResultsUseCase,
)
from src.application.use_cases.inventories.get_inventory import GetInventoryUseCase
from src.application.use_cases.inventories.get_inventory_metrics import GetInventoryMetricsUseCase
from src.application.use_cases.inventories.list_inventories import ListInventoriesUseCase
from src.application.use_cases.inventories.list_inventory_list_items import (
    ListInventoryListItemsUseCase,
)
from src.application.use_cases.inventories.soft_delete_inventories import (
    SoftDeleteInventoriesUseCase,
)
from src.application.use_cases.inventories.update_inventory_name import UpdateInventoryNameUseCase
from src.application.use_cases.suppliers.create_client_supplier import CreateClientSupplierUseCase
from src.application.use_cases.suppliers.get_client_supplier import GetClientSupplierUseCase
from src.application.use_cases.suppliers.list_client_suppliers import ListClientSuppliersUseCase
from src.application.use_cases.suppliers.manage_supplier_prompt_configs import (
    ActivateSupplierPromptConfigVersionUseCase,
    CreateSupplierPromptConfigVersionUseCase,
    GetActiveSupplierPromptConfigUseCase,
    GetSupplierPromptConfigUseCase,
    ListSupplierPromptConfigsUseCase,
)
from src.application.use_cases.suppliers.manage_supplier_reference_images import (
    DeleteSupplierReferenceImageUseCase,
    GetSupplierReferenceImageUseCase,
)
from src.application.use_cases.suppliers.upload_supplier_reference_images import (
    ListSupplierReferenceImagesUseCase,
    UploadSupplierReferenceImagesUseCase,
)
from src.runtime.app_container import get_app_container
from src.runtime.v3_deps import (
    get_aisle_repo,
    get_client_repo,
    get_client_supplier_repo,
    get_clock,
    get_inventory_repo,
    get_job_repo,
    get_metrics_calculator,
    get_position_repo,
    get_product_record_repo,
    get_supplier_prompt_config_repo,
    get_supplier_reference_image_repo,
)


def get_create_inventory_use_case(
    repo: InventoryRepository = Depends(get_inventory_repo),
    client_repo: ClientRepository = Depends(get_client_repo),
    clock: Clock = Depends(get_clock),
    operational_resolver: OperationalExecutionConfigResolver = Depends(
        get_operational_execution_config_resolver
    ),
) -> CreateInventoryUseCase:
    from src.config import load_settings as _load_settings

    return CreateInventoryUseCase(
        inventory_repo=repo,
        client_repo=client_repo,
        clock=clock,
        operational_resolver=operational_resolver,
        settings_loader=_load_settings,
    )


def get_update_inventory_name_use_case(
    repo: InventoryRepository = Depends(get_inventory_repo),
    clock: Clock = Depends(get_clock),
) -> UpdateInventoryNameUseCase:
    return UpdateInventoryNameUseCase(inventory_repo=repo, clock=clock)


def get_soft_delete_inventories_use_case(
    repo: InventoryRepository = Depends(get_inventory_repo),
    clock: Clock = Depends(get_clock),
) -> SoftDeleteInventoriesUseCase:
    return SoftDeleteInventoriesUseCase(inventory_repo=repo, clock=clock)


def get_create_client_use_case(
    repo: ClientRepository = Depends(get_client_repo),
    clock: Clock = Depends(get_clock),
) -> CreateClientUseCase:
    return CreateClientUseCase(client_repo=repo, clock=clock)


def get_update_client_use_case(
    repo: ClientRepository = Depends(get_client_repo),
    clock: Clock = Depends(get_clock),
) -> UpdateClientUseCase:
    return UpdateClientUseCase(client_repo=repo, clock=clock)


def get_create_client_supplier_use_case(
    client_repo: ClientRepository = Depends(get_client_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
    clock: Clock = Depends(get_clock),
) -> CreateClientSupplierUseCase:
    return CreateClientSupplierUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        clock=clock,
    )


def get_list_inventories_use_case(
    repo: InventoryRepository = Depends(get_inventory_repo),
) -> ListInventoriesUseCase:
    return ListInventoriesUseCase(inventory_repo=repo)


def get_list_clients_use_case(
    repo: ClientRepository = Depends(get_client_repo),
) -> ListClientsUseCase:
    return ListClientsUseCase(client_repo=repo)


def get_list_client_suppliers_use_case(
    client_repo: ClientRepository = Depends(get_client_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
) -> ListClientSuppliersUseCase:
    return ListClientSuppliersUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
    )


def get_list_inventory_list_items_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    client_repo: ClientRepository = Depends(get_client_repo),
) -> ListInventoryListItemsUseCase:
    return ListInventoryListItemsUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        client_repo=client_repo,
    )


def get_inventory_recognition_config_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    extraction_profile_repo: SupplierExtractionProfileRepository = Depends(
        get_supplier_extraction_profile_repo
    ),
    label_profile_repo=Depends(get_client_supplier_label_profile_repo),
):
    from src.application.use_cases.inventories.get_inventory_recognition_config import (
        GetInventoryRecognitionConfigUseCase,
    )

    return GetInventoryRecognitionConfigUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        extraction_profile_repo=extraction_profile_repo,
        label_profile_repo=label_profile_repo,
    )


def get_client_recognition_config_use_case(
    client_repo: ClientRepository = Depends(get_client_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
    extraction_profile_repo: SupplierExtractionProfileRepository = Depends(
        get_supplier_extraction_profile_repo
    ),
    label_profile_repo=Depends(get_client_supplier_label_profile_repo),
) -> GetClientRecognitionConfigUseCase:
    return GetClientRecognitionConfigUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        extraction_profile_repo=extraction_profile_repo,
        label_profile_repo=label_profile_repo,
    )


def get_raspberry_recognition_config_use_case(
    client_repo: ClientRepository = Depends(get_client_repo),
    client_recognition_use_case: GetClientRecognitionConfigUseCase = Depends(
        get_client_recognition_config_use_case
    ),
) -> GetRaspberryRecognitionConfigUseCase:
    return GetRaspberryRecognitionConfigUseCase(
        client_repo=client_repo,
        client_recognition_use_case=client_recognition_use_case,
    )


def get_get_inventory_use_case(
    repo: InventoryRepository = Depends(get_inventory_repo),
) -> GetInventoryUseCase:
    return GetInventoryUseCase(inventory_repo=repo)


def get_get_client_use_case(
    repo: ClientRepository = Depends(get_client_repo),
) -> GetClientUseCase:
    return GetClientUseCase(client_repo=repo)


def get_get_client_supplier_use_case(
    client_repo: ClientRepository = Depends(get_client_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
) -> GetClientSupplierUseCase:
    return GetClientSupplierUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
    )


def get_export_inventory_results_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    product_record_repo: ProductRecordRepository = Depends(get_product_record_repo),
    result_context_resolver: ResultContextResolver = Depends(get_result_context_resolver),
) -> ExportInventoryResultsUseCase:
    return ExportInventoryResultsUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        product_record_repo=product_record_repo,
        result_context_resolver=result_context_resolver,
        reconciliation_repo=get_app_container().get_position_reconciliation_repo(),
        override_repo=get_app_container().get_manual_position_override_repo(),
        label_repo=get_app_container().get_client_position_label_repo(),
    )


def get_export_aisle_results_csv_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    product_record_repo: ProductRecordRepository = Depends(get_product_record_repo),
    result_context_resolver: ResultContextResolver = Depends(get_result_context_resolver),
) -> ExportAisleResultsCsvUseCase:
    return ExportAisleResultsCsvUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        product_record_repo=product_record_repo,
        result_context_resolver=result_context_resolver,
        reconciliation_repo=get_app_container().get_position_reconciliation_repo(),
        override_repo=get_app_container().get_manual_position_override_repo(),
        label_repo=get_app_container().get_client_position_label_repo(),
    )


def get_export_inventory_summary_csv_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    product_record_repo: ProductRecordRepository = Depends(get_product_record_repo),
    result_context_resolver: ResultContextResolver = Depends(get_result_context_resolver),
    client_repo: ClientRepository = Depends(get_client_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
    job_repo: JobRepository = Depends(get_job_repo),
) -> ExportInventorySummaryCsvUseCase:
    return ExportInventorySummaryCsvUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        product_record_repo=product_record_repo,
        result_context_resolver=result_context_resolver,
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        job_repo=job_repo,
    )


def get_export_inventory_package_zip_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    product_record_repo: ProductRecordRepository = Depends(get_product_record_repo),
    result_context_resolver: ResultContextResolver = Depends(get_result_context_resolver),
    client_repo: ClientRepository = Depends(get_client_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
    job_repo: JobRepository = Depends(get_job_repo),
) -> ExportInventoryPackageZipUseCase:
    return ExportInventoryPackageZipUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        product_record_repo=product_record_repo,
        result_context_resolver=result_context_resolver,
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        job_repo=job_repo,
    )


def get_export_aisle_business_csv_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    position_repo: PositionRepository = Depends(get_position_repo),
    product_record_repo: ProductRecordRepository = Depends(get_product_record_repo),
    result_context_resolver: ResultContextResolver = Depends(get_result_context_resolver),
    client_repo: ClientRepository = Depends(get_client_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
) -> ExportAisleBusinessCsvUseCase:
    return ExportAisleBusinessCsvUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        position_repo=position_repo,
        product_record_repo=product_record_repo,
        result_context_resolver=result_context_resolver,
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
    )


def get_get_inventory_metrics_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    metrics_calculator: MetricsCalculator = Depends(get_metrics_calculator),
) -> GetInventoryMetricsUseCase:
    return GetInventoryMetricsUseCase(
        inventory_repo=inventory_repo,
        metrics_calculator=metrics_calculator,
    )


def get_upload_supplier_reference_images_use_case(
    client_repo: ClientRepository = Depends(get_client_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
    reference_repo: SupplierReferenceImageRepository = Depends(get_supplier_reference_image_repo),
    artifact_storage=Depends(get_artifact_storage),
    clock: Clock = Depends(get_clock),
) -> UploadSupplierReferenceImagesUseCase:
    return UploadSupplierReferenceImagesUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        reference_repo=reference_repo,
        artifact_storage=artifact_storage,
        clock=clock,
    )


def get_list_supplier_reference_images_use_case(
    client_repo: ClientRepository = Depends(get_client_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
    reference_repo: SupplierReferenceImageRepository = Depends(get_supplier_reference_image_repo),
) -> ListSupplierReferenceImagesUseCase:
    return ListSupplierReferenceImagesUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        reference_repo=reference_repo,
    )


def get_get_supplier_reference_image_use_case(
    client_repo: ClientRepository = Depends(get_client_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
    reference_repo: SupplierReferenceImageRepository = Depends(get_supplier_reference_image_repo),
) -> GetSupplierReferenceImageUseCase:
    return GetSupplierReferenceImageUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        reference_repo=reference_repo,
    )


def get_delete_supplier_reference_image_use_case(
    client_repo: ClientRepository = Depends(get_client_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
    reference_repo: SupplierReferenceImageRepository = Depends(get_supplier_reference_image_repo),
    artifact_storage=Depends(get_artifact_storage),
) -> DeleteSupplierReferenceImageUseCase:
    return DeleteSupplierReferenceImageUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        reference_repo=reference_repo,
        artifact_storage=artifact_storage,
    )


def get_list_supplier_prompt_configs_use_case(
    client_repo: ClientRepository = Depends(get_client_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
    prompt_config_repo: SupplierPromptConfigRepository = Depends(get_supplier_prompt_config_repo),
) -> ListSupplierPromptConfigsUseCase:
    from src.config import load_settings

    return ListSupplierPromptConfigsUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        prompt_config_repo=prompt_config_repo,
        settings=load_settings(),
    )


def get_create_supplier_prompt_config_version_use_case(
    client_repo: ClientRepository = Depends(get_client_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
    prompt_config_repo: SupplierPromptConfigRepository = Depends(get_supplier_prompt_config_repo),
    clock: Clock = Depends(get_clock),
) -> CreateSupplierPromptConfigVersionUseCase:
    from src.config import load_settings

    return CreateSupplierPromptConfigVersionUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        prompt_config_repo=prompt_config_repo,
        clock=clock,
        settings=load_settings(),
    )


def get_get_active_supplier_prompt_config_use_case(
    client_repo: ClientRepository = Depends(get_client_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
    prompt_config_repo: SupplierPromptConfigRepository = Depends(get_supplier_prompt_config_repo),
) -> GetActiveSupplierPromptConfigUseCase:
    from src.config import load_settings

    return GetActiveSupplierPromptConfigUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        prompt_config_repo=prompt_config_repo,
        settings=load_settings(),
    )


def get_activate_supplier_prompt_config_version_use_case(
    client_repo: ClientRepository = Depends(get_client_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
    prompt_config_repo: SupplierPromptConfigRepository = Depends(get_supplier_prompt_config_repo),
) -> ActivateSupplierPromptConfigVersionUseCase:
    return ActivateSupplierPromptConfigVersionUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        prompt_config_repo=prompt_config_repo,
    )


def get_get_supplier_prompt_config_use_case(
    client_repo: ClientRepository = Depends(get_client_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
    prompt_config_repo: SupplierPromptConfigRepository = Depends(get_supplier_prompt_config_repo),
) -> GetSupplierPromptConfigUseCase:
    return GetSupplierPromptConfigUseCase(
        client_repo=client_repo,
        client_supplier_repo=client_supplier_repo,
        prompt_config_repo=prompt_config_repo,
    )


def get_list_supplier_extraction_profiles_use_case():
    return get_app_container().get_list_supplier_extraction_profiles_use_case()


def get_get_active_supplier_extraction_profile_use_case():
    return get_app_container().get_get_active_supplier_extraction_profile_use_case()


def get_get_supplier_extraction_profile_by_version_use_case():
    return get_app_container().get_get_supplier_extraction_profile_by_version_use_case()


def get_create_supplier_extraction_profile_version_use_case():
    return get_app_container().get_create_supplier_extraction_profile_version_use_case()


def get_activate_supplier_extraction_profile_version_use_case():
    return get_app_container().get_activate_supplier_extraction_profile_version_use_case()


def get_test_label_recognition_code_use_case():
    return get_app_container().get_test_label_recognition_code_use_case()


def get_clone_supplier_extraction_profile_use_case():
    return get_app_container().get_clone_supplier_extraction_profile_use_case()


def get_list_supplier_reference_annotations_use_case():
    return get_app_container().get_list_supplier_reference_annotations_use_case()


def get_replace_supplier_reference_annotations_use_case():
    return get_app_container().get_replace_supplier_reference_annotations_use_case()


def get_list_client_supplier_label_profiles_use_case():
    from src.application.use_cases.suppliers.manage_client_supplier_label_profiles import (
        ListClientSupplierLabelProfilesUseCase,
    )

    container = get_app_container()
    return ListClientSupplierLabelProfilesUseCase(
        client_supplier_repo=container.get_client_supplier_repo(),
        label_profile_repo=container.get_client_supplier_label_profile_repo(),
    )


def get_upsert_client_supplier_label_profile_use_case():
    from src.application.use_cases.suppliers.manage_client_supplier_label_profiles import (
        UpsertClientSupplierLabelProfileUseCase,
    )

    container = get_app_container()
    return UpsertClientSupplierLabelProfileUseCase(
        client_supplier_repo=container.get_client_supplier_repo(),
        label_profile_repo=container.get_client_supplier_label_profile_repo(),
        clock=container.get_clock(),
    )
