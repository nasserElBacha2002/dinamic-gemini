"""Offline configuration package for Raspberry Pi (JSON file transfer)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.api.schemas.offline_recognition_bundle_schemas import (
    OfflineRaspberryRecognitionBundleResponse,
    OfflineRecognitionBundleResponse,
    RaspberryInventoryListItemDto,
)
from src.application.use_cases.raspberry.offline_package_constants import (
    RASPBERRY_OFFLINE_PACKAGE_SCHEMA_VERSION,
)


class RaspberryOfflinePackageResponse(BaseModel):
    """Single JSON artifact: global recognition + inventories + per-inventory context."""

    model_config = ConfigDict(extra="ignore")

    package_schema_version: int = RASPBERRY_OFFLINE_PACKAGE_SCHEMA_VERSION
    generated_at: datetime
    recognition: OfflineRaspberryRecognitionBundleResponse
    inventories: list[RaspberryInventoryListItemDto] = Field(default_factory=list)
    inventory_recognition_configs: list[OfflineRecognitionBundleResponse] = Field(
        default_factory=list,
        description="Per-inventory aisle bindings (same contract as mobile/raspberry sync).",
    )
