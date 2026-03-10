"""v3.0 Asset API schemas (upload, list)."""

from datetime import datetime

from pydantic import BaseModel


class SourceAssetResponse(BaseModel):
    """Single source asset in list or upload response."""
    id: str
    aisle_id: str
    type: str
    original_filename: str
    storage_path: str
    mime_type: str
    uploaded_at: datetime


class UploadAisleAssetsResponse(BaseModel):
    """Response for POST .../aisles/{aisle_id}/assets."""
    assets: list[SourceAssetResponse]
