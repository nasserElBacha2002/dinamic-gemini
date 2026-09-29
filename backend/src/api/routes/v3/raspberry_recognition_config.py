"""Device-authenticated Raspberry recognition-config endpoints."""

from fastapi import APIRouter, Depends

from src.api.constants.route_paths import (
    API_V3_CLIENTS_ROUTER_PREFIX,
    API_V3_PREFIX,
)
from src.api.dependencies import (
    get_client_recognition_config_use_case,
    get_raspberry_recognition_config_use_case,
    require_raspberry_device_token,
)
from src.api.errors import reraise_if_mapped
from src.api.schemas.offline_recognition_bundle_schemas import (
    OfflineClientRecognitionBundleResponse,
    OfflineClientSupplierRecognitionConfigDto,
    OfflineRaspberryClientRecognitionConfigDto,
    OfflineRaspberryRecognitionBundleResponse,
    OfflineRecognitionProfileDto,
)
from src.application.use_cases.clients.get_client_recognition_config import (
    ClientRecognitionConfigCommand,
    GetClientRecognitionConfigUseCase,
)
from src.application.use_cases.clients.get_raspberry_recognition_config import (
    GetRaspberryRecognitionConfigUseCase,
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
