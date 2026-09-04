"""API schemas for ClientSupplier label profile configuration (Phase 1)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

LabelKindLiteral = Literal["ITEM", "POSITION"]
LabelProfileSourceLiteral = Literal["DINAMIC", "SUPPLIER"]
LabelProfileSourceOverrideLiteral = Literal["DINAMIC", "SUPPLIER"]


class ClientSupplierLabelProfileResponse(BaseModel):
    label_kind: LabelKindLiteral
    source: LabelProfileSourceLiteral
    profile_config_id: str | None = None
    updated_at: datetime | None = None


class UpsertClientSupplierLabelProfileRequest(BaseModel):
    source: LabelProfileSourceLiteral
