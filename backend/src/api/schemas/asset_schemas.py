"""v3.0 Asset API schemas (upload, list)."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


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


class SourceAssetImageDisplayUrlResponse(BaseModel):
    """JSON contract for SPA image display (avoids reading redirect ``Location`` from fetch).

    When ``image_url`` is set, it is safe for ``<img src>`` without ``Authorization``.
    When ``requires_authenticated_fetch`` is true, the client must GET ``.../file`` with Bearer
    and display bytes via a blob URL (local storage, legacy rows, HEIC normalized preview).
    """

    image_url: Optional[str] = Field(
        default=None,
        description="Presigned HTTPS URL when storage is S3; omit when client must fetch /file.",
    )
    requires_authenticated_fetch: bool = Field(
        default=False,
        description="When true, GET the asset /file endpoint with auth and use the response body.",
    )
