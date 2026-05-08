from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.dependencies import (
    get_activate_global_prompt_config_version_use_case,
    get_create_global_prompt_config_version_use_case,
    get_get_active_global_prompt_config_use_case,
    get_get_global_prompt_config_use_case,
    get_list_global_prompt_configs_use_case,
)
from src.api.errors.error_mapping import reraise_if_mapped
from src.api.schemas.global_prompt_config_schemas import (
    CreateGlobalPromptConfigRequest,
    GlobalPromptConfigResponse,
    GlobalPromptConfigsListResponse,
)
from src.application.errors import GlobalPromptConfigNotFoundError
from src.application.use_cases.manage_global_prompt_configs import (
    ActivateGlobalPromptConfigVersionCommand,
    ActivateGlobalPromptConfigVersionUseCase,
    CreateGlobalPromptConfigVersionCommand,
    CreateGlobalPromptConfigVersionUseCase,
    GetActiveGlobalPromptConfigCommand,
    GetActiveGlobalPromptConfigUseCase,
    GetGlobalPromptConfigCommand,
    GetGlobalPromptConfigUseCase,
    ListGlobalPromptConfigsCommand,
    ListGlobalPromptConfigsUseCase,
)
from src.auth.dependencies import get_current_admin
from src.domain.global_prompt_config import GlobalPromptConfig

router = APIRouter(
    prefix="/api/v3/prompt-configs/global",
    tags=["prompt-configs-v3"],
    dependencies=[Depends(get_current_admin)],
)


def _global_prompt_config_to_response(row: GlobalPromptConfig) -> GlobalPromptConfigResponse:
    return GlobalPromptConfigResponse(
        id=row.id,
        scope_type=row.scope_type,
        provider_name=row.provider_name,
        model_name=row.model_name,
        instructions_text=row.instructions_text,
        version=int(row.version),
        is_active=bool(row.is_active),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("", response_model=GlobalPromptConfigsListResponse)
def list_global_prompt_configs(
    use_case: ListGlobalPromptConfigsUseCase = Depends(get_list_global_prompt_configs_use_case),
) -> GlobalPromptConfigsListResponse:
    try:
        rows = use_case.execute(ListGlobalPromptConfigsCommand())
        return GlobalPromptConfigsListResponse(
            items=[_global_prompt_config_to_response(row) for row in rows]
        )
    except Exception as e:
        reraise_if_mapped(e)
        raise


@router.post("", response_model=GlobalPromptConfigResponse, status_code=201)
def create_global_prompt_config(
    payload: CreateGlobalPromptConfigRequest,
    use_case: CreateGlobalPromptConfigVersionUseCase = Depends(
        get_create_global_prompt_config_version_use_case
    ),
) -> GlobalPromptConfigResponse:
    try:
        created = use_case.execute(
            CreateGlobalPromptConfigVersionCommand(
                instructions_text=payload.instructions_text,
                activate=payload.activate,
            )
        )
        return _global_prompt_config_to_response(created)
    except Exception as e:
        reraise_if_mapped(e)
        raise


@router.get(
    "/active",
    response_model=GlobalPromptConfigResponse,
)
def get_active_global_prompt_config(
    use_case: GetActiveGlobalPromptConfigUseCase = Depends(
        get_get_active_global_prompt_config_use_case
    ),
) -> GlobalPromptConfigResponse:
    try:
        active = use_case.execute(GetActiveGlobalPromptConfigCommand())
        if active is None:
            raise GlobalPromptConfigNotFoundError(
                "Global prompt config not found in requested scope"
            )
        return _global_prompt_config_to_response(active)
    except Exception as e:
        reraise_if_mapped(e)
        raise


@router.get("/{config_id}", response_model=GlobalPromptConfigResponse)
def get_global_prompt_config(
    config_id: str,
    use_case: GetGlobalPromptConfigUseCase = Depends(get_get_global_prompt_config_use_case),
) -> GlobalPromptConfigResponse:
    try:
        row = use_case.execute(GetGlobalPromptConfigCommand(config_id=config_id))
        return _global_prompt_config_to_response(row)
    except Exception as e:
        reraise_if_mapped(e)
        raise


@router.post("/{config_id}/activate", response_model=GlobalPromptConfigResponse)
def activate_global_prompt_config(
    config_id: str,
    use_case: ActivateGlobalPromptConfigVersionUseCase = Depends(
        get_activate_global_prompt_config_version_use_case
    ),
) -> GlobalPromptConfigResponse:
    try:
        activated = use_case.execute(
            ActivateGlobalPromptConfigVersionCommand(config_id=config_id)
        )
        return _global_prompt_config_to_response(activated)
    except Exception as e:
        reraise_if_mapped(e)
        raise
