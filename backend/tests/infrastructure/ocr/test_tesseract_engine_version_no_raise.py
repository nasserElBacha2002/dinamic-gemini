"""Regression: missing Tesseract must not raise when reading attempt_model / engine_version."""

from __future__ import annotations

from src.application.ports.internal_label_reader import InternalOcrEngineUnavailableError
from src.infrastructure.ocr.tesseract_internal_label_reader import (
    TesseractInternalLabelReader,
)


def test_engine_version_property_does_not_raise_when_tesseract_missing(monkeypatch) -> None:
    reader = TesseractInternalLabelReader()

    def _boom():
        raise RuntimeError("tesseract is not installed or it's not in your PATH")

    import pytesseract

    monkeypatch.setattr(pytesseract, "get_tesseract_version", _boom)

    # Property must return None, not raise (used before process() for attempt metadata).
    assert reader.engine_version is None

    # read path still fails closed with the domain error.
    try:
        reader._ensure_available()
        raised = False
    except InternalOcrEngineUnavailableError as exc:
        raised = True
        assert "tesseract unavailable" in str(exc)
    assert raised is True
