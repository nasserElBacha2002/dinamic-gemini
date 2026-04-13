"""Admin-only read-only AI / provider configuration inspection (username ``admin`` only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.application.services.admin_ai_config_inspection import build_admin_ai_config_payload
from src.auth.dependencies import require_username_admin_for_ai_config
from src.api.schemas.admin_ai_config_schemas import AdminAiConfigResponse
from src.config import load_settings

router = APIRouter(
    prefix="/api/v3/admin",
    tags=["admin-v3"],
    dependencies=[Depends(require_username_admin_for_ai_config)],
)


@router.get("/ai-config", response_model=AdminAiConfigResponse)
def get_admin_ai_config() -> AdminAiConfigResponse:
    raw = build_admin_ai_config_payload(load_settings())
    return AdminAiConfigResponse.model_validate(raw)
