"""End-to-end real-decode tests for the CODE_SCAN strategy (Phase 3 corrections).

Generates a real QR label with ``qrcode`` and decodes it through the actual
``PyzbarCodeScanner`` + parser + consolidator, exercising the deterministic
``internal_code|quantity`` contract without any mocks. Skips cleanly when ``qrcode`` or
``pyzbar``/libzbar are unavailable in the runtime (the unit tests with a FakeScanner cover
rotation/consolidation logic independently).
"""

from __future__ import annotations

import io
from datetime import datetime, timezone

import pytest

pytest.importorskip("pyzbar")
qrcode = pytest.importorskip("qrcode")

from src.application.services.image_processing.code_detection_consolidator import (  # noqa: E402
    CodeDetectionConsolidator,
)
from src.application.services.image_processing.code_scan_processing_strategy import (  # noqa: E402
    CodeScanConfig,
    CodeScanProcessingStrategy,
)
from src.application.services.image_processing.encoded_label_payload_parser import (  # noqa: E402
    EncodedLabelPayloadParser,
)
from src.domain.aisle_identification.modes import (  # noqa: E402
    CONFIGURATION_SNAPSHOT_VERSION,
    AisleIdentificationExecutionStrategy,
    AisleIdentificationMode,
)
from src.domain.assets.entities import SourceAsset, SourceAssetType  # noqa: E402
from src.domain.image_processing.contracts import (  # noqa: E402
    ExecutionScope,
    ImageProcessingContext,
    ImageResultStatus,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _qr_png_bytes(payload: str) -> bytes:
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class _FixedContentReader:
    def __init__(self, content: bytes) -> None:
        self._content = content

    def read_image_bytes(self, asset: SourceAsset) -> bytes:
        return self._content


def _strategy(content: bytes) -> CodeScanProcessingStrategy:
    try:
        from src.infrastructure.code_scanning.pyzbar_code_scanner import PyzbarCodeScanner

        scanner = PyzbarCodeScanner()
    except Exception:  # pragma: no cover - libzbar missing at runtime
        pytest.skip("pyzbar/libzbar not available")
    return CodeScanProcessingStrategy(
        scanner=scanner,
        content_reader=_FixedContentReader(content),
        parser=EncodedLabelPayloadParser(quantity_max=99999999, allow_decimal_quantity=False),
        consolidator=CodeDetectionConsolidator(),
        config=CodeScanConfig(quantity_max=99999999),
    )


def _asset() -> SourceAsset:
    return SourceAsset(
        id="s1",
        aisle_id="a1",
        type=SourceAssetType.PHOTO,
        original_filename="s1.png",
        storage_path="/s1.png",
        mime_type="image/png",
        uploaded_at=NOW,
    )


def _context() -> ImageProcessingContext:
    return ImageProcessingContext(
        job_id="job1",
        asset_id="s1",
        aisle_id="a1",
        inventory_id="inv1",
        client_id=None,
        identification_mode=AisleIdentificationMode.CODE_SCAN,
        execution_strategy=AisleIdentificationExecutionStrategy.CODE_SCAN,
        configuration_snapshot_version=CONFIGURATION_SNAPSHOT_VERSION,
        provider_name="code_scan",
        model_name="pyzbar",
        prompt_key=None,
        prompt_version=None,
        attempt_number=1,
        execution_scope=ExecutionScope.SINGLE_ASSET,
    )


def test_real_qr_pipe_payload_resolves_code_and_quantity() -> None:
    strategy = _strategy(_qr_png_bytes("ABC123|5"))
    result = strategy.process(_context(), _asset())
    assert result.status is ImageResultStatus.RESOLVED_INTERNAL
    assert result.internal_code == "ABC123"
    assert int(result.quantity) == 5


def test_real_qr_code_only_is_manual_review() -> None:
    strategy = _strategy(_qr_png_bytes("ABC123"))
    result = strategy.process(_context(), _asset())
    # A recoverable code with no quantity must never default to 1.
    assert result.status is ImageResultStatus.PENDING_MANUAL_REVIEW


def test_blank_image_is_unrecognized() -> None:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color="white").save(buf, format="PNG")
    strategy = _strategy(buf.getvalue())
    result = strategy.process(_context(), _asset())
    assert result.status is ImageResultStatus.UNRECOGNIZED
