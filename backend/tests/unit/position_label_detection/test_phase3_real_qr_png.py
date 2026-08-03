"""Phase 3 — real QR PNG decode → classify → validate → resolve (no product binding)."""

from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

pytest.importorskip("pyzbar")
qrcode = pytest.importorskip("qrcode")

from src.application.services.position_label_detection.code_classifier import (  # noqa: E402
    CodeClassifier,
)
from src.application.services.position_label_detection.payload_parser import (  # noqa: E402
    PositionLabelPayloadParser,
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
        return datetime(2026, 7, 31, 15, 0, tzinfo=timezone.utc)


def _signing() -> PositioningLabelSigningService:
    return PositioningLabelSigningService(
        PositioningLabelSigningConfig(secret="test-secret-16chars", key_version=1, required=True)
    )


def _qr_png_bytes(payload: str) -> bytes:
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _decode_first_qr(png: bytes) -> str:
    try:
        from src.infrastructure.code_scanning.pyzbar_code_scanner import PyzbarCodeScanner
    except Exception:  # pragma: no cover
        pytest.skip("pyzbar/libzbar not available")
    from src.domain.assets.entities import SourceAsset, SourceAssetType

    now = datetime(2026, 7, 31, tzinfo=timezone.utc)
    scanner = PyzbarCodeScanner()
    asset = SourceAsset(
        id="decode-tmp",
        aisle_id="a1",
        type=SourceAssetType.PHOTO,
        original_filename="tmp.png",
        storage_path="/tmp.png",
        mime_type="image/png",
        uploaded_at=now,
    )
    symbols = scanner.scan_asset(asset, content=png)
    assert symbols, "expected at least one QR symbol"
    return symbols[0].code_value


def test_real_png_position_label_roundtrip() -> None:
    signing = _signing()
    payload = signing.sign_payload(
        build_positioning_label_payload(public_label_id="pos_png_1", version=1)
    )
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    decoded = _decode_first_qr(_qr_png_bytes(raw))
    assert "DINAMIC_POSITION" in decoded

    now = datetime(2026, 7, 31, tzinfo=timezone.utc)
    labels = MemoryClientPositionLabelRepository()
    labels.save(
        ClientPositionLabel(
            id=str(uuid4()),
            client_id="client-png",
            public_identifier="pos_png_1",
            name="A-01-03",
            normalized_name="A-01-03",
            status=ClientPositionLabelStatus.ACTIVE,
            payload_version=1,
            canonical_payload=payload,
            created_at=now,
            updated_at=now,
        )
    )
    detections = MemoryImagePositionLabelDetectionRepository()
    use_case = ImagePositionDetectionUseCase(
        classifier=CodeClassifier(max_payload_bytes=4096),
        parser=PositionLabelPayloadParser(max_payload_bytes=4096),
        validator=PositionLabelValidationService(
            signing=signing, signature_validation_enabled=True
        ),
        resolver=PositionLabelResolver(label_repo=labels),
        repo=detections,
        clock=_Clock(),
        detection_enabled=True,
        persistence_enabled=True,
        max_codes_per_image=16,
    )
    result = use_case.execute(
        ImagePositionDetectionCommand(
            client_id="client-png",
            inventory_id="inv-png",
            job_id="job-png",
            source_asset_id="asset-png",
            codes=[
                DetectedCode(
                    symbology="QR_CODE",
                    raw_value=decoded,
                    normalized_value=decoded.strip(),
                )
            ],
            sequence_number=4,
        )
    )
    assert len(result.detections) == 1
    row = result.detections[0]
    assert row.detection_status is PositionLabelDetectionStatus.VALID
    assert row.position_name_snapshot == "A-01-03"
    assert row.sequence_number == 4
    # Replay must be idempotent.
    again = use_case.execute(
        ImagePositionDetectionCommand(
            client_id="client-png",
            inventory_id="inv-png",
            job_id="job-png",
            source_asset_id="asset-png",
            codes=[
                DetectedCode(
                    symbology="QR_CODE",
                    raw_value=decoded,
                    normalized_value=decoded.strip(),
                )
            ],
            sequence_number=4,
        )
    )
    assert again.detections[0].id == row.id
    assert len(detections.list_by_job("job-png")) == 1


def test_real_png_position_plus_item_product_not_bound() -> None:
    signing = _signing()
    payload = signing.sign_payload(
        build_positioning_label_payload(public_label_id="pos_png_2", version=1)
    )
    pos_raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    pos_decoded = _decode_first_qr(_qr_png_bytes(pos_raw))
    item_decoded = _decode_first_qr(_qr_png_bytes("ITEM99|3"))

    now = datetime(2026, 7, 31, tzinfo=timezone.utc)
    labels = MemoryClientPositionLabelRepository()
    labels.save(
        ClientPositionLabel(
            id=str(uuid4()),
            client_id="client-png",
            public_identifier="pos_png_2",
            name="B-02",
            normalized_name="B-02",
            status=ClientPositionLabelStatus.ACTIVE,
            payload_version=1,
            canonical_payload=payload,
            created_at=now,
            updated_at=now,
        )
    )
    use_case = ImagePositionDetectionUseCase(
        classifier=CodeClassifier(max_payload_bytes=4096),
        parser=PositionLabelPayloadParser(max_payload_bytes=4096),
        validator=PositionLabelValidationService(
            signing=signing, signature_validation_enabled=True
        ),
        resolver=PositionLabelResolver(label_repo=labels),
        repo=MemoryImagePositionLabelDetectionRepository(),
        clock=_Clock(),
        detection_enabled=True,
        persistence_enabled=True,
        max_codes_per_image=16,
    )
    result = use_case.execute(
        ImagePositionDetectionCommand(
            client_id="client-png",
            inventory_id="inv-png",
            job_id="job-png-2",
            source_asset_id="asset-png-2",
            codes=[
                DetectedCode(symbology="QR_CODE", raw_value=pos_decoded, normalized_value=""),
                DetectedCode(symbology="QR_CODE", raw_value=item_decoded, normalized_value=""),
            ],
        )
    )
    assert result.detections[0].detection_status is PositionLabelDetectionStatus.VALID
    assert len(result.item_codes) == 1
    # Phase 3: no product↔position association fields on detection.
    assert "bound_product" not in (result.detections[0].metadata_json or {})
