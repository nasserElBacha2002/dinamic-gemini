"""Shared offline recognition vectors — backend LabelValidationService parity."""

from __future__ import annotations

import json
from pathlib import Path

from src.application.services.image_processing.extraction_profile_configuration import (
    parse_extraction_configuration,
)
from src.application.services.label_validation import LabelValidationService
from src.domain.label_profiles.entities import ResolvedLabelProfile, ResolvedLabelProfiles
from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource
from src.domain.label_validation import (
    CandidateLabel,
    LabelValidationStatus,
    RecognitionSource,
)
from src.domain.label_validation.context import LabelValidationContext

VECTORS = Path(__file__).resolve().parents[3] / "contracts/offline-recognition/v1/minimal-vectors.json"


def _profiles(kind: LabelKind) -> ResolvedLabelProfiles:
    item_source = (
        LabelProfileSource.SUPPLIER if kind is LabelKind.ITEM else LabelProfileSource.DINAMIC
    )
    pos_source = (
        LabelProfileSource.SUPPLIER if kind is LabelKind.POSITION else LabelProfileSource.DINAMIC
    )
    return ResolvedLabelProfiles(
        item=ResolvedLabelProfile(
            label_kind=LabelKind.ITEM,
            source=item_source,
            client_supplier_id="sup-1",
            resolution_source="CLIENT_SUPPLIER",
        ),
        position=ResolvedLabelProfile(
            label_kind=LabelKind.POSITION,
            source=pos_source,
            client_supplier_id="sup-1",
            resolution_source="CLIENT_SUPPLIER",
        ),
    )


def _map_mobile_status(backend_status: LabelValidationStatus, error_code: str | None) -> str:
    if backend_status is LabelValidationStatus.VALID:
        return "VALID"
    if error_code in {
        "LABEL_PREFIX_MISMATCH",
        "LABEL_LENGTH_MISMATCH",
        "LABEL_CHARSET_MISMATCH",
        "LABEL_SUFFIX_MISMATCH",
        "LABEL_SEGMENT_COUNT_MISMATCH",
    }:
        return "NOT_APPLICABLE"
    return "INVALID"


def test_shared_offline_recognition_vectors() -> None:
    data = json.loads(VECTORS.read_text(encoding="utf-8"))
    svc = LabelValidationService()
    for vector in data["vectors"]:
        kind = LabelKind(vector["label_kind"])
        cfg = parse_extraction_configuration(vector["configuration"])
        ctx = LabelValidationContext(
            resolved_profiles=_profiles(kind),
            item_extraction_configuration=cfg if kind is LabelKind.ITEM else None,
            position_extraction_configuration=cfg if kind is LabelKind.POSITION else None,
        )
        result = svc.validate(
            CandidateLabel(
                raw_payload=vector["raw_payload"],
                recognition_source=RecognitionSource.VISION,
                label_kind_hint=kind,
                symbology="QR",
            ),
            context=ctx,
            label_kind=kind,
        )
        expected = vector["expected"]
        mapped = _map_mobile_status(result.status, result.error_code)
        assert mapped == expected["status"], vector["id"]
        if expected.get("error_code"):
            assert result.error_code == expected["error_code"], vector["id"]
        if expected.get("label_id") is not None or "label_id" in expected:
            label = result.label
            got = getattr(label, "label_id", None) if label is not None else None
            assert got == expected.get("label_id"), vector["id"]
        if "sku" in expected:
            label = result.label
            got = getattr(label, "sku", None) if label is not None else None
            assert got == expected.get("sku"), vector["id"]
        if "quantity" in expected:
            label = result.label
            got = getattr(label, "quantity", None) if label is not None else None
            assert got == expected.get("quantity"), vector["id"]
        if "position_id" in expected:
            label = result.label
            got = getattr(label, "position_id", None) if label is not None else None
            assert got == expected.get("position_id"), vector["id"]
