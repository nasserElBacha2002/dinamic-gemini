"""Offline recognition config bundle for mobile sync (deterministic profiles only)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Mobile must reject unknown major schema versions.
OFFLINE_RECOGNITION_BUNDLE_SCHEMA_VERSION = 1


class OfflineAisleRecognitionConfigDto(BaseModel):
    model_config = ConfigDict(extra="ignore")

    aisle_id: str
    aisle_code: str | None = None
    client_supplier_id: str | None = None
    item_profile_source_override: Literal["DINAMIC", "SUPPLIER"] | None = None
    position_profile_source_override: Literal["DINAMIC", "SUPPLIER"] | None = None
    #: Effective sources after override → supplier → DINAMIC (informational for mobile UX).
    effective_item_source: Literal["DINAMIC", "SUPPLIER"] = "DINAMIC"
    effective_position_source: Literal["DINAMIC", "SUPPLIER"] = "DINAMIC"


class OfflineRecognitionProfileDto(BaseModel):
    model_config = ConfigDict(extra="ignore")

    client_supplier_id: str
    label_kind: Literal["ITEM", "POSITION"]
    source: Literal["SUPPLIER"] = "SUPPLIER"
    profile_id: str
    profile_version: int
    configuration_schema_version: int
    recognition_mode: str | None = None
    semantic_type: str | None = None
    #: Deterministic-only subset — no prompts, reference images, or visual hard-rules.
    configuration: dict[str, Any]


class OfflineRecognitionBundleResponse(BaseModel):
    """Versioned bundle for mobile offline supplier recognition."""

    model_config = ConfigDict(extra="ignore")

    bundle_schema_version: int = OFFLINE_RECOGNITION_BUNDLE_SCHEMA_VERSION
    inventory_id: str
    client_id: str
    generated_at: datetime
    aisles: list[OfflineAisleRecognitionConfigDto]
    profiles: list[OfflineRecognitionProfileDto]
    #: Optional weak etag for skip-download (ISO generated_at + profile count).
    bundle_revision: str | None = None
