"""Regression: missing Tesseract must not raise when reading attempt_model / engine_version."""

from __future__ import annotations

import pytest

from src.application.ports.internal_label_reader import InternalOcrEngineUnavailableError
from src.infrastructure.ocr.tesseract_internal_label_reader import (
    TesseractInternalLabelReader,
)


def test_engine_version_property_does_not_raise_when_tesseract_missing(monkeypatch) -> None:
    reader = TesseractInternalLabelReader()

    def _force_unavailable() -> None:
        reader._probed = True
        reader._version = None
        reader._probe_error = (
            "tesseract unavailable: tesseract is not installed or it's not in your PATH"
        )

    monkeypatch.setattr(reader, "_probe_once", _force_unavailable)

    # Property must return None, not raise (used before process() for attempt metadata).
    assert reader.engine_version is None

    # read path still fails closed with the domain error.
    with pytest.raises(InternalOcrEngineUnavailableError, match="tesseract unavailable"):
        reader._ensure_available()
