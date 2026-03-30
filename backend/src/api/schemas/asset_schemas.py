"""v3.0 Asset API schemas (upload, list)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

SourceAssetImageDisplayStrategy = Literal["presigned_url", "authenticated_file_fetch"]


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

    **display_strategy** makes the client contract explicit:

    - ``presigned_url``: use ``image_url`` in ``<img src>`` without ``Authorization``.
    - ``authenticated_file_fetch``: perform an authenticated ``GET`` on the **same** asset's
      ``.../file`` URL (this repo's evidence/reference file route). That endpoint may return:

        - Raw bytes for **local** or **legacy** objects under ``v3_uploads``,
        - A **307 redirect** to S3 when storage is **S3** (not used by the HEIC branch),
        - For **HEIC/HEIF**, a **normalized JPEG** ``FileResponse`` when a preview exists.

      The JSON endpoint only returns this strategy after **non-HEIC** local/legacy paths pass the
      same on-disk checks as ``/file`` would; HEIC returns this strategy only when a normalized
      preview path was found. A follow-up ``/file`` can still fail if the file disappears between
      calls (rare); treat errors like any other ``/file`` response.

    ``requires_authenticated_fetch`` is ``True`` iff ``display_strategy == authenticated_file_fetch``.
    """

    image_url: Optional[str] = Field(
        default=None,
        description="HTTPS presigned URL when strategy is presigned_url; null when client must use /file.",
    )
    requires_authenticated_fetch: bool = Field(
        default=False,
        description="True iff the client must GET .../file with Bearer and display the response body (or follow redirect for non-image flows).",
    )
    display_strategy: SourceAssetImageDisplayStrategy = Field(
        ...,
        description=(
            "presigned_url: set image_url. authenticated_file_fetch: GET the sibling /file route "
            "(local/legacy bytes, HEIC normalized preview, or other /file behavior)."
        ),
    )

    @model_validator(mode="after")
    def _strategy_matches_fields(self) -> SourceAssetImageDisplayUrlResponse:
        if self.display_strategy == "presigned_url":
            if self.requires_authenticated_fetch:
                raise ValueError("presigned_url requires requires_authenticated_fetch=False")
            if not (self.image_url and str(self.image_url).strip()):
                raise ValueError("presigned_url requires a non-empty image_url")
        else:
            if self.image_url is not None:
                raise ValueError("authenticated_file_fetch requires image_url=None")
            if not self.requires_authenticated_fetch:
                raise ValueError("authenticated_file_fetch requires requires_authenticated_fetch=True")
        return self
