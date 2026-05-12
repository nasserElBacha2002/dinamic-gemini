from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CreateSupplierPromptConfigRequest(BaseModel):
    provider_name: str | None = None
    model_name: str | None = None
    instructions_text: str
    activate: bool = True


class SupplierPromptConfigResponse(BaseModel):
    id: str
    client_supplier_id: str
    provider_name: str | None
    model_name: str | None
    instructions_text: str
    version: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SupplierPromptConfigsListResponse(BaseModel):
    items: list[SupplierPromptConfigResponse]
