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


def test_hierarchy_png_keeps_scannable_qr_on_100x100() -> None:
    """Hierarchy fields must not push QR off-canvas on MM_100x100."""
    svc = PositioningLabelSigningService(
        PositioningLabelSigningConfig(secret="render-secret", key_version=1)
    )
    payload = svc.sign_payload(
        build_positioning_label_payload(
            public_label_id="pos_hier_qr",
            version=2,
            pallet="02",
            side="LEFT",
            level=1,
            marker_index=6,
            marker_total=10,
        )
    )
    display = PositioningLabelDisplayData(
        depot_name="etiquetas-interna",
        aisle_code="",
        position_code="02 LEFT N1 06/10",
        public_label_id="pos_hier_qr",
        payload_version=2,
        marker_version=1,
        template_version=2,
        pallet="02",
        side="LEFT",
        level=1,
        marker_index=6,
        marker_total=10,
    )
    preset = get_positioning_label_preset("MM_100x100")
    png = PositioningLabelRenderer().render(
        payload=payload, display=display, preset=preset, fmt="PNG"
    )
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
    assert decoded, "hierarchy PNG must keep a scannable QR"
    assert "DINAMIC_POSITION" in decoded
    assert "pos_hier_qr" in decoded
    # Lower third should contain substantial QR ink (not crushed into footer).
    lower = img.crop((0, img.height * 2 // 5, img.width, img.height))
    ink = sum(1 for px in lower.getdata() if px != (255, 255, 255))
    assert ink > 5000, f"expected QR ink in lower band, got {ink}"
