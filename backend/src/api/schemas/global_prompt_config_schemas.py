from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CreateGlobalPromptConfigRequest(BaseModel):
    instructions_text: str
    activate: bool = True


class GlobalPromptConfigResponse(BaseModel):
    id: str
    scope_type: str
    provider_name: str | None
    model_name: str | None
    instructions_text: str
    version: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class GlobalPromptConfigsListResponse(BaseModel):
    items: list[GlobalPromptConfigResponse]
