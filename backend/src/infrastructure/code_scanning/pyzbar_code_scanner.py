"""Real QR/barcode scanner using pyzbar (Phase 2)."""

from __future__ import annotations

import logging
from typing import Any

from src.application.ports.code_scanner import CodeScanDetectionCandidate
from src.domain.assets.entities import SourceAsset
from src.domain.code_scans.bounding_box import bounding_box_rect_polygon
from src.domain.code_scans.entities import CodeScanDetectionStatus
from src.infrastructure.code_scanning.image_decode import (
    UnsupportedImageFormatError,
    decode_bytes_to_rgb_image,
    is_supported_image_asset,
)
from src.infrastructure.code_scanning.pyzbar_type_mapping import (
    decode_symbol_bytes,
    map_pyzbar_type_name,
)

logger = logging.getLogger(__name__)


class PyzbarUnavailableError(RuntimeError):
    """Raised when pyzbar or libzbar is not installed."""


def _import_pyzbar():
    try:
        from pyzbar.pyzbar import decode as pyzbar_decode
    except ImportError as exc:
        raise PyzbarUnavailableError(
            "pyzbar is not installed; install pyzbar and system libzbar0"
        ) from exc
    return pyzbar_decode


class PyzbarCodeScanner:
    def __init__(self) -> None:
        self._decode = _import_pyzbar()

    @property
    def engine_name(self) -> str:
        return "pyzbar"

    def scan_asset(
        self,
        asset: SourceAsset,
        content: bytes | None = None,
    ) -> list[CodeScanDetectionCandidate]:
        if content is None:
            raise ValueError("PyzbarCodeScanner requires image bytes; content=None")
        if not is_supported_image_asset(asset):
            raise UnsupportedImageFormatError(
                f"Unsupported image format for asset {asset.id}"
            )
        image = decode_bytes_to_rgb_image(content, asset=asset)
        try:
            symbols = self._decode(image)
        except Exception as exc:
            logger.warning(
                "code_scan pyzbar_decode_failed asset_id=%s error=%s",
                asset.id,
                type(exc).__name__,
            )
            raise ValueError(f"pyzbar decode failed for asset {asset.id}") from exc
        finally:
            image.close()

        candidates: list[CodeScanDetectionCandidate] = []
        for sym in symbols:
            code_value = decode_symbol_bytes(sym.data)
            type_name = sym.type.name if hasattr(sym.type, "name") else str(sym.type)
            code_type = map_pyzbar_type_name(type_name)
            bbox = _symbol_bounding_box(sym)
            meta: dict[str, Any] = {"pyzbar_type": type_name}
            if getattr(sym, "quality", None) is not None:
                meta["quality"] = int(sym.quality)
            candidates.append(
                CodeScanDetectionCandidate(
                    code_type=code_type,
                    code_value=code_value,
                    detection_status=CodeScanDetectionStatus.DETECTED,
                    bounding_box_json=bbox,
                    confidence=None,
                    metadata_json=meta,
                )
            )
        return candidates


def _symbol_bounding_box(sym: Any) -> dict[str, Any] | None:
    rect = getattr(sym, "rect", None)
    polygon = getattr(sym, "polygon", None)
    if rect is None:
        return None
    left = float(rect.left)
    top = float(rect.top)
    width = float(rect.width)
    height = float(rect.height)
    points: list[list[float]] = []
    if polygon:
        for pt in polygon:
            points.append([float(pt.x), float(pt.y)])
    else:
        points = [
            [left, top],
            [left + width, top],
            [left + width, top + height],
            [left, top + height],
        ]
    return bounding_box_rect_polygon(
        left=left,
        top=top,
        width=width,
        height=height,
        polygon=points,
    )
