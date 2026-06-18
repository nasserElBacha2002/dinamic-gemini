"""Phase 4.4 corrections — MIME inference policy."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.pipeline.services.provider_execution_errors import PROVIDER_IMAGE_UNSUPPORTED_FORMAT
from src.pipeline.services.provider_execution_request import infer_mime_type


def test_supported_declared_jpeg() -> None:
    assert infer_mime_type(declared_mime="image/jpeg", storage_path=None) == "image/jpeg"


def test_supported_declared_png() -> None:
    assert infer_mime_type(declared_mime="image/png", storage_path=None) == "image/png"


def test_unsupported_declared_tiff_rejected() -> None:
    with pytest.raises(Exception, match=PROVIDER_IMAGE_UNSUPPORTED_FORMAT):
        infer_mime_type(declared_mime="image/tiff", storage_path=Path("x.tiff"))


def test_unsupported_declared_pdf_rejected() -> None:
    with pytest.raises(Exception, match=PROVIDER_IMAGE_UNSUPPORTED_FORMAT):
        infer_mime_type(declared_mime="application/pdf", storage_path=Path("x.pdf"))


def test_absent_mime_png_filename() -> None:
    assert infer_mime_type(declared_mime=None, storage_path=Path("a.png")) == "image/png"


def test_absent_mime_unknown_extension_defaults_jpeg() -> None:
    assert infer_mime_type(declared_mime=None, storage_path=Path("a.bin")) == "image/jpeg"
