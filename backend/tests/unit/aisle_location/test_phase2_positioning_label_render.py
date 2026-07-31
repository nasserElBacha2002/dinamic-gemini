"""Phase 2 positioning label signing + render unit tests."""

from __future__ import annotations

import io

import pytest

from src.application.services.positioning_label_presets import get_positioning_label_preset
from src.application.services.positioning_label_renderer import (
    PositioningLabelDisplayData,
    PositioningLabelRenderer,
)
from src.application.services.positioning_label_signing import (
    PositioningLabelSigningConfig,
    PositioningLabelSigningService,
    parse_previous_secrets,
)
from src.domain.aisle_location.payload import (
    build_positioning_label_payload,
    canonicalize_positioning_payload_for_signing,
    validate_positioning_payload,
)


def test_canonicalize_excludes_signature() -> None:
    payload = {
        "type": "DINAMIC_POSITION",
        "version": 1,
        "label_id": "pl_a",
        "position_id": "loc_1",
        "key_version": 1,
        "signature": "abc",
    }
    canon = canonicalize_positioning_payload_for_signing(payload)
    assert "signature" not in canon
    assert "key_version" in canon


def test_hmac_sign_and_verify() -> None:
    svc = PositioningLabelSigningService(
        PositioningLabelSigningConfig(secret="test-secret", key_version=1)
    )
    base = build_positioning_label_payload(public_label_id="pl_x", public_position_id="pos_1")
    signed = svc.sign_payload(base)
    assert signed["signature"]
    assert signed["key_version"] == 1
    assert svc.verify_payload(signed) is True
    tampered = dict(signed)
    tampered["position_id"] = "other"
    assert svc.verify_payload(tampered) is False


def test_hmac_rotation_previous_secret() -> None:
    parse_previous_secrets("1:old-secret")
    svc = PositioningLabelSigningService(
        PositioningLabelSigningConfig(
            secret="new-secret",
            key_version=2,
            previous_secrets=((1, "old-secret"),),
        )
    )
    old_svc = PositioningLabelSigningService(
        PositioningLabelSigningConfig(secret="old-secret", key_version=1)
    )
    signed_old = old_svc.sign_payload(
        build_positioning_label_payload(public_label_id="pl_y", public_position_id="pos_2")
    )
    assert svc.verify_payload(signed_old) is True


def test_payload_forbids_item_fields() -> None:
    payload = build_positioning_label_payload(public_label_id="pl_z", public_position_id="pos_3")
    payload["sku"] = "X"
    with pytest.raises(ValueError, match="sku"):
        validate_positioning_payload(payload)


def test_presets_known() -> None:
    p = get_positioning_label_preset("MM_100x100")
    assert p.width_mm == 100.0
    assert p.dpi == 300
    with pytest.raises(ValueError):
        get_positioning_label_preset("NOPE")


def test_render_png_and_pdf_and_decode_qr_final_artifact() -> None:
    """Final rendered PNG must decode; no fallback to private QR builder."""
    svc = PositioningLabelSigningService(
        PositioningLabelSigningConfig(secret="render-secret", key_version=1)
    )
    payload = svc.sign_payload(
        build_positioning_label_payload(public_label_id="pl_render", public_position_id="pos_r")
    )
    display = PositioningLabelDisplayData(
        depot_name="Depósito Test",
        aisle_code="A-01",
        position_code="P-01",
        public_label_id="pl_render",
        payload_version=1,
        marker_version=1,
        template_version=1,
    )
    preset = get_positioning_label_preset("MM_100x100")
    renderer = PositioningLabelRenderer()
    png = renderer.render(payload=payload, display=display, preset=preset, fmt="PNG")
    pdf = renderer.render(payload=payload, display=display, preset=preset, fmt="PDF")
    assert png.content.startswith(b"\x89PNG")
    assert pdf.content.startswith(b"%PDF")
    assert len(png.content) > 500
    assert len(pdf.content) > 500

    from PIL import Image

    img = Image.open(io.BytesIO(png.content)).convert("RGB")
    decoded = ""
    try:
        from pyzbar.pyzbar import decode as zbar_decode

        decoded_list = zbar_decode(img)
        if decoded_list:
            decoded = decoded_list[0].data.decode("utf-8")
    except Exception:
        decoded = ""
    if not decoded:
        import cv2
        import numpy as np

        decoded, _pts, _ = cv2.QRCodeDetector().detectAndDecode(np.array(img))
    assert decoded, "final PNG artifact must be decodable without private QR fallback"
    assert "DINAMIC_POSITION" in decoded
    assert "pl_render" in decoded
    assert payload["signature"] in decoded
    assert "pos_r" in decoded


def test_render_idempotent_hash_stable() -> None:
    payload = build_positioning_label_payload(public_label_id="pl_h", public_position_id="pos_h")
    display = PositioningLabelDisplayData(
        depot_name="D",
        aisle_code="A",
        position_code="P",
        public_label_id="pl_h",
        payload_version=1,
        marker_version=1,
        template_version=1,
    )
    preset = get_positioning_label_preset("THERMAL")
    renderer = PositioningLabelRenderer()
    a = renderer.render(payload=payload, display=display, preset=preset, fmt="PNG")
    b = renderer.render(payload=payload, display=display, preset=preset, fmt="PNG")
    assert a.artifact_hash == b.artifact_hash
