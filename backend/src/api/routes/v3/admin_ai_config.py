"""Admin-only read-only AI / provider configuration inspection (primary principal ``AuthUser.id`` only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.constants.error_wire import HTTP_DETAIL_ADMIN_AI_UNKNOWN_PROMPT_PROFILE_COMBINATION
from src.api.constants.route_paths import API_V3_ADMIN_ROUTER_PREFIX
from src.api.schemas.admin_ai_config_schemas import (
    AdminAiComposedPromptResponse,
    AdminAiConfigResponse,
)
from src.application.services.admin_ai_config_inspection import (
    build_admin_ai_config_payload,
    compose_prompt_variant_for_inspection,
)
from src.auth.dependencies import require_ai_config_inspection_user
from src.config import load_settings

router = APIRouter(
    prefix=API_V3_ADMIN_ROUTER_PREFIX,
    tags=["admin-v3"],
    dependencies=[Depends(require_ai_config_inspection_user)],
)


@router.get("/ai-config", response_model=AdminAiConfigResponse)
def get_admin_ai_config() -> AdminAiConfigResponse:
    """Overview + capabilities + contracts; composed prompt text is loaded via ``composed-prompt``."""
    raw = build_admin_ai_config_payload(load_settings())
    return AdminAiConfigResponse.model_validate(raw)


@router.get("/ai-config/composed-prompt", response_model=AdminAiComposedPromptResponse)
def get_admin_ai_config_composed_prompt(
    prompt_key: str = Query(..., min_length=1, description="Registered hybrid profile key."),
    pipeline_provider_key: str = Query(..., min_length=1, description="Pipeline provider key."),
    prompt_parity_mode: bool = Query(
        False, description="OpenAI-only parity flag; must be false for other providers."
    ),
) -> AdminAiComposedPromptResponse:
    """Lazy composed hybrid base text for one variant (keeps main payload small)."""
    raw = compose_prompt_variant_for_inspection(
        prompt_key=prompt_key,
        pipeline_provider_key=pipeline_provider_key,
        prompt_parity_mode=prompt_parity_mode,
    )
    if raw is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=HTTP_DETAIL_ADMIN_AI_UNKNOWN_PROMPT_PROFILE_COMBINATION,
        )
    return AdminAiComposedPromptResponse.model_validate(raw)
