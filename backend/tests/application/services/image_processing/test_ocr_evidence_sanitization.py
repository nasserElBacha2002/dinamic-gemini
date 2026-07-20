"""Evidence sanitization must not persist secrets from arbitrary __str__."""

from __future__ import annotations

from src.application.services.image_processing.ocr_candidate_to_field_candidate_mapper import (
    serialize_ocr_candidate_evidence,
)


class _SecretObj:
    def __str__(self) -> str:
        return "SECRET_TOKEN_DO_NOT_LEAK"

    def __repr__(self) -> str:
        return "SECRET_TOKEN_DO_NOT_LEAK"


def test_unsupported_type_does_not_call_str() -> None:
    payload = {"obj": _SecretObj(), "ok": 1}
    out = serialize_ocr_candidate_evidence(payload)
    assert out["ok"] == 1
    assert out["obj"] == {"unsupported_type": "_SecretObj"}
    blob = str(out)
    assert "SECRET_TOKEN_DO_NOT_LEAK" not in blob
