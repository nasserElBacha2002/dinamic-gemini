"""Device-authenticated Raspberry recognition-config endpoints."""

from fastapi import APIRouter, Depends, Query

from src.api.constants.route_paths import (
    API_V3_CLIENTS_ROUTER_PREFIX,
    API_V3_PREFIX,
)
from src.api.dependencies import (
    get_client_recognition_config_use_case,
    get_inventory_recognition_config_use_case,
    get_raspberry_recognition_config_use_case,
    require_raspberry_device_token,
)
from src.api.deps.inventory import get_list_raspberry_inventories_use_case
from src.api.errors import reraise_if_mapped
from src.api.schemas.offline_recognition_bundle_schemas import (
    OfflineAisleRecognitionConfigDto,
    OfflineClientRecognitionBundleResponse,
    OfflineClientSupplierRecognitionConfigDto,
    OfflineRaspberryClientRecognitionConfigDto,
    OfflineRaspberryRecognitionBundleResponse,
    OfflineRecognitionBundleResponse,
    OfflineRecognitionProfileDto,
    OfflineSupplierRecognitionConfigDto,
    RaspberryInventoryListItemDto,
    RaspberryInventoryListResponse,
)
from src.application.errors import InventoryNotFoundError
from src.application.use_cases.clients.get_client_recognition_config import (
    ClientRecognitionConfigCommand,
    GetClientRecognitionConfigUseCase,
)
from src.application.use_cases.clients.get_raspberry_recognition_config import (
    GetRaspberryRecognitionConfigUseCase,
)
from src.application.use_cases.inventories.get_inventory_recognition_config import (
    GetInventoryRecognitionConfigCommand,
    GetInventoryRecognitionConfigUseCase,
    OfflineRecognitionBundle,
)
from src.application.use_cases.inventories.list_raspberry_inventories import (
    ListRaspberryInventoriesCommand,
    ListRaspberryInventoriesUseCase,
)

router = APIRouter(
    prefix=API_V3_CLIENTS_ROUTER_PREFIX,
    tags=["clients-v3-device"],
)

raspberry_router = APIRouter(
    prefix=f"{API_V3_PREFIX}/raspberry",
    tags=["raspberry-v3-device"],
)


@router.get(
    "/{client_id}/recognition-config",
    response_model=OfflineClientRecognitionBundleResponse,
    summary="Offline recognition config bundle for one Raspberry client",
)
def get_client_recognition_config(
    client_id: str,
    _authenticated: None = Depends(require_raspberry_device_token),
    use_case: GetClientRecognitionConfigUseCase = Depends(
        get_client_recognition_config_use_case
    ),
) -> OfflineClientRecognitionBundleResponse:
    try:
        bundle = use_case.execute(
            ClientRecognitionConfigCommand(client_id=client_id)
        )
    except Exception as exc:
        reraise_if_mapped(exc)
        raise

    return OfflineClientRecognitionBundleResponse(
        bundle_schema_version=bundle.bundle_schema_version,
        client_id=bundle.client_id,
        generated_at=bundle.generated_at,
        suppliers=[
            OfflineClientSupplierRecognitionConfigDto(
                client_supplier_id=supplier.client_supplier_id,
                name=supplier.name,
                item_source=supplier.item_source,  # type: ignore[arg-type]
                position_source=supplier.position_source,  # type: ignore[arg-type]
            )
            for supplier in bundle.suppliers
        ],
        profiles=[
            OfflineRecognitionProfileDto(
                client_supplier_id=profile.client_supplier_id,
                label_kind=profile.label_kind,  # type: ignore[arg-type]
                source="SUPPLIER",
                profile_id=profile.profile_id,
                profile_version=profile.profile_version,
                configuration_schema_version=profile.configuration_schema_version,
                recognition_mode=profile.recognition_mode,
                semantic_type=profile.semantic_type,
                configuration=profile.configuration,
            )
            for profile in bundle.profiles
        ],
        bundle_revision=bundle.bundle_revision,
    )


@raspberry_router.get(
    "/recognition-config",
    response_model=OfflineRaspberryRecognitionBundleResponse,
    summary="Offline recognition config bundle for Raspberry devices",
)
def get_raspberry_recognition_config(
    _authenticated: None = Depends(require_raspberry_device_token),
    use_case: GetRaspberryRecognitionConfigUseCase = Depends(
        get_raspberry_recognition_config_use_case
    ),
) -> OfflineRaspberryRecognitionBundleResponse:
    try:
        bundle = use_case.execute()
    except Exception as exc:
        reraise_if_mapped(exc)
        raise

    return OfflineRaspberryRecognitionBundleResponse(
        bundle_schema_version=bundle.bundle_schema_version,
        generated_at=bundle.generated_at,
        clients=[
            OfflineRaspberryClientRecognitionConfigDto(
                client_id=client.client_id,
                name=client.name,
                suppliers=[
                    OfflineClientSupplierRecognitionConfigDto(
                        client_supplier_id=supplier.client_supplier_id,
                        name=supplier.name,
                        item_source=supplier.item_source,  # type: ignore[arg-type]
                        position_source=supplier.position_source,  # type: ignore[arg-type]
                    )
                    for supplier in client.recognition.suppliers
                ],
                profiles=[
                    OfflineRecognitionProfileDto(
                        client_supplier_id=profile.client_supplier_id,
                        label_kind=profile.label_kind,  # type: ignore[arg-type]
                        source="SUPPLIER",
                        profile_id=profile.profile_id,
                        profile_version=profile.profile_version,
                        configuration_schema_version=(
                            profile.configuration_schema_version
                        ),
                        recognition_mode=profile.recognition_mode,
                        semantic_type=profile.semantic_type,
                        configuration=profile.configuration,
                    )
                    for profile in client.recognition.profiles
                ],
                bundle_revision=client.recognition.bundle_revision,
            )
            for client in bundle.clients
        ],
       bundle_revision=bundle.bundle_revision,
    )


@raspberry_router.get(
    "/inventories",
    response_model=RaspberryInventoryListResponse,
    summary="Inventories for one client, authenticating as a Raspberry device",
)
def list_raspberry_inventories(
    client_id: str = Query(..., min_length=1),
    _authenticated: None = Depends(require_raspberry_device_token),
    use_case: ListRaspberryInventoriesUseCase = Depends(
        get_list_raspberry_inventories_use_case
    ),
) -> RaspberryInventoryListResponse:
    try:
        inventories = use_case.execute(
            ListRaspberryInventoriesCommand(client_id=client_id.strip())
        )
    except Exception as exc:
        reraise_if_mapped(exc)
        raise
    return RaspberryInventoryListResponse(
        items=[
            RaspberryInventoryListItemDto(
                id=inventory.id,
                name=inventory.name,
                client_id=client_id.strip(),
                status=inventory.status.value,
            )
            for inventory in inventories
        ]
    )


@raspberry_router.get(
    "/inventories/{inventory_id}/recognition-config",
    response_model=OfflineRecognitionBundleResponse,
    summary="Inventory recognition-config for Raspberry device sync",
)
def get_raspberry_inventory_recognition_config(
    inventory_id: str,
    client_id: str = Query(..., min_length=1),
    _authenticated: None = Depends(require_raspberry_device_token),
    use_case: GetInventoryRecognitionConfigUseCase = Depends(
        get_inventory_recognition_config_use_case
    ),
) -> OfflineRecognitionBundleResponse:
    wanted_client = client_id.strip()
    try:
        bundle = use_case.execute(
            GetInventoryRecognitionConfigCommand(inventory_id=inventory_id)
        )
        if bundle.client_id != wanted_client:
            raise InventoryNotFoundError(f"Inventory not found: {inventory_id}")
    except Exception as exc:
        reraise_if_mapped(exc)
        raise
    return _offline_recognition_bundle_response(bundle)


def _offline_recognition_bundle_response(
    bundle: OfflineRecognitionBundle,
) -> OfflineRecognitionBundleResponse:
    return OfflineRecognitionBundleResponse(
        bundle_schema_version=bundle.bundle_schema_version,
        inventory_id=bundle.inventory_id,
        client_id=bundle.client_id,
        generated_at=bundle.generated_at,
        aisles=[
            OfflineAisleRecognitionConfigDto(
                aisle_id=a.aisle_id,
                aisle_code=a.aisle_code,
                client_supplier_id=a.client_supplier_id,
                item_profile_source_override=a.item_profile_source_override,  # type: ignore[arg-type]
                position_profile_source_override=a.position_profile_source_override,  # type: ignore[arg-type]
                effective_item_source=a.effective_item_source,  # type: ignore[arg-type]
                effective_position_source=a.effective_position_source,  # type: ignore[arg-type]
            )
            for a in bundle.aisles
        ],
        suppliers=[
            OfflineSupplierRecognitionConfigDto(
                client_supplier_id=s.client_supplier_id,
                item_source=s.item_source,  # type: ignore[arg-type]
                position_source=s.position_source,  # type: ignore[arg-type]
            )
            for s in bundle.suppliers
        ],
        profiles=[
            OfflineRecognitionProfileDto(
                client_supplier_id=p.client_supplier_id,
                label_kind=p.label_kind,  # type: ignore[arg-type]
                source="SUPPLIER",
                profile_id=p.profile_id,
                profile_version=p.profile_version,
                configuration_schema_version=p.configuration_schema_version,
                recognition_mode=p.recognition_mode,
                semantic_type=p.semantic_type,
                configuration=p.configuration,
            )
            for p in bundle.profiles
        ],
        bundle_revision=bundle.bundle_revision,
    )
