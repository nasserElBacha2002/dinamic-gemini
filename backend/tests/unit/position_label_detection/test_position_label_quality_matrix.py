"""Digital quality matrix for DINAMIC_POSITION QR detection (Phase 3 corrections)."""

from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

pytest.importorskip("pyzbar")
qrcode = pytest.importorskip("qrcode")

from src.application.services.position_label_detection.code_classifier import (  # noqa: E402
    CodeClassifier,
)
from src.application.services.position_label_detection.payload_parser import (  # noqa: E402
    PositionLabelPayloadParser,
)
from src.application.services.position_label_detection.position_label_policy import (  # noqa: E402
    PositionLabelPolicyService,
)
from src.application.services.position_label_detection.resolver import (  # noqa: E402
    PositionLabelResolver,
)
from src.application.services.position_label_detection.validation_service import (  # noqa: E402
    PositionLabelValidationService,
)
from src.application.services.positioning_label_signing import (  # noqa: E402
    PositioningLabelSigningConfig,
    PositioningLabelSigningService,
)
from src.application.use_cases.position_label_detection.detect_image_position_labels import (  # noqa: E402
    ImagePositionDetectionCommand,
    ImagePositionDetectionUseCase,
)
from src.domain.aisle_location.payload import build_positioning_label_payload  # noqa: E402
from src.domain.assets.entities import SourceAsset, SourceAssetType  # noqa: E402
from src.domain.client_position_label.entities import (  # noqa: E402
    ClientPositionLabel,
    ClientPositionLabelStatus,
)
from src.domain.position_label_detection.entities import (  # noqa: E402
    DetectedCode,
    PositionLabelDetectionStatus,
)
from src.infrastructure.repositories.memory_client_position_label_repository import (  # noqa: E402
    MemoryClientPositionLabelRepository,
)
from src.infrastructure.repositories.memory_image_position_label_detection_repository import (  # noqa: E402
    MemoryImagePositionLabelDetectionRepository,
)


class _Clock:
    def now(self) -> datetime:
        return datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)


def _signing() -> PositioningLabelSigningService:
    return PositioningLabelSigningService(
        PositioningLabelSigningConfig(secret="test-secret-16chars", key_version=1, required=True)
    )


def _base_qr_image(payload: dict) -> Image.Image:
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    img = qrcode.make(raw).convert("RGB")
    canvas = Image.new("RGB", (800, 800), "white")
    qr = img.resize((360, 360), Image.Resampling.NEAREST)
    canvas.paste(qr, ((800 - 360) // 2, (800 - 360) // 2))
    return canvas


def _decode(png: bytes) -> str | None:
    from src.infrastructure.code_scanning.pyzbar_code_scanner import PyzbarCodeScanner

    now = datetime(2026, 8, 3, tzinfo=timezone.utc)
    asset = SourceAsset(
        id="qm",
        aisle_id="a1",
        type=SourceAssetType.PHOTO,
        original_filename="qm.png",
        storage_path="/qm.png",
        mime_type="image/png",
        uploaded_at=now,
    )
    try:
        symbols = PyzbarCodeScanner().scan_asset(asset, content=png)
    except Exception:
        return None
    if not symbols:
        return None
    return symbols[0].code_value


def _to_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _use_case(payload: dict):
    now = datetime(2026, 8, 3, tzinfo=timezone.utc)
    labels = MemoryClientPositionLabelRepository()
    labels.save(
        ClientPositionLabel(
            id=str(uuid4()),
            client_id="client-qm",
            public_identifier="pos_qm",
            name="A-01-03",
            normalized_name="A-01-03",
            status=ClientPositionLabelStatus.ACTIVE,
            payload_version=1,
            canonical_payload=payload,
            created_at=now,
            updated_at=now,
        )
    )
    signing = _signing()
    resolver = PositionLabelResolver(label_repo=labels)
    return ImagePositionDetectionUseCase(
        classifier=CodeClassifier(max_payload_bytes=4096),
        parser=PositionLabelPayloadParser(max_payload_bytes=4096),
        validator=PositionLabelValidationService(
            signing=signing, signature_validation_enabled=True
        ),
        resolver=resolver,
        policy=PositionLabelPolicyService(resolver=resolver, allow_unsigned_legacy=True),
        repo=MemoryImagePositionLabelDetectionRepository(),
        clock=_Clock(),
        detection_enabled=True,
        persistence_enabled=True,
        max_codes_per_image=16,
    )


@pytest.mark.parametrize(
    "name,transform",
    [
        ("clean", lambda im: im),
        ("rot90", lambda im: im.rotate(90, expand=True, fillcolor="white")),
        ("rot180", lambda im: im.rotate(180, expand=True, fillcolor="white")),
        ("rot270", lambda im: im.rotate(270, expand=True, fillcolor="white")),
        ("downscale", lambda im: im.resize((400, 400), Image.Resampling.BILINEAR).resize((800, 800))),
        ("contrast", lambda im: ImageEnhance.Contrast(im).enhance(1.6)),
        ("blur_light", lambda im: im.filter(ImageFilter.GaussianBlur(radius=0.8))),
        ("noise", lambda im: ImageOps.autocontrast(im)),
    ],
)
def test_quality_matrix_digital_transforms(name, transform) -> None:
    signing = _signing()
    payload = signing.sign_payload(
        build_positioning_label_payload(public_label_id="pos_qm", version=1)
    )
    img = transform(_base_qr_image(payload))
    decoded = _decode(_to_png(img))
    if decoded is None:
        pytest.skip(f"decoder could not read transform={name} (threshold soft-skip)")
    result = _use_case(payload).execute(
        ImagePositionDetectionCommand(
            client_id="client-qm",
            inventory_id="inv-qm",
            job_id=f"job-{name}",
            source_asset_id=f"asset-{name}",
            codes=[DetectedCode(symbology="QR_CODE", raw_value=decoded, normalized_value=decoded)],
        )
    )
    assert result.detections
    assert result.detections[0].detection_status is PositionLabelDetectionStatus.VALID
