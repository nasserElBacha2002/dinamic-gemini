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
from PIL import Image

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


def _strategy(content: bytes, *, event_publisher=None) -> CodeScanProcessingStrategy:
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
        event_publisher=event_publisher,
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


def test_real_two_d1_qr_on_one_canvas_returns_two_products() -> None:
    """Real pyzbar path: one PNG with two D1 QRs → two consolidator/strategy products.

    Registry is not wired here, so product_results may be empty for D1 (issued check),
    but the scanner + consolidator stage must surface both label_ids.
    """
    from src.domain.product_labels.format import build_product_label_payload

    a = build_product_label_payload(
        label_id="A1B2C3D4E5", internal_code="232424090", quantity=1000
    )
    b = build_product_label_payload(
        label_id="FGHJKMNPQR", internal_code="232424025", quantity=1100
    )
    qa = qrcode.make(a).convert("RGB").resize((220, 220))
    qb = qrcode.make(b).convert("RGB").resize((220, 220))
    canvas = Image.new("RGB", (520, 280), color=(255, 255, 255))
    canvas.paste(qa, (20, 30))
    canvas.paste(qb, (280, 30))
    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    content = buf.getvalue()

    strategy = _strategy(content)
    asset = _asset()
    session = strategy._scan_with_variants(
        asset, content, decode_budget_started_at=__import__("time").monotonic()
    )
    raw_values = {c.code_value for c in session.candidates}
    assert a in raw_values
    assert b in raw_values
    assert session.scan_complete is True

    from src.application.services.image_processing.code_detection_consolidator import (
        CodeDetectionConsolidator,
        CodeDetectionInput,
    )
    from src.application.services.image_processing.code_scan_processing_strategy import (
        symbology_for_candidate,
    )
    from src.application.services.image_processing.encoded_label_payload_parser import (
        EncodedLabelPayloadParser,
    )

    parser = EncodedLabelPayloadParser(quantity_max=99999999)
    detections = [
        CodeDetectionInput(
            symbology=symbology_for_candidate(c),
            raw_value=c.code_value or "",
            parsed=parser.parse(c.code_value or ""),
            bounding_box=c.bounding_box_json,
            detection_index=i,
        )
        for i, c in enumerate(session.candidates)
    ]
    consolidated = CodeDetectionConsolidator().consolidate(detections)
    assert len(consolidated.product_results) == 2
    ids = {p.label_id for p in consolidated.product_results}
    assert ids == {"A1B2C3D4E5", "FGHJKMNPQR"}

    strategy = _strategy(_qr_png_bytes("ABC123|5"))
    result = strategy.process(_context(), _asset())
    assert result.status is ImageResultStatus.RESOLVED_INTERNAL
    assert result.internal_code == "ABC123"
    assert int(result.quantity) == 5


def test_real_qr_with_profile_aware_flag_still_uses_consolidator() -> None:
    """OCR profile_aware flag must not divert CODE_SCAN away from consolidator."""
    from src.domain.client_supplier.extraction_profile import (
        default_extraction_configuration,
    )

    strategy = _strategy(_qr_png_bytes("DINAMIC42|7"))
    ctx = _context()
    # ImageProcessingContext is a dataclass — rebuild with profile flags.
    ctx = ImageProcessingContext(
        job_id=ctx.job_id,
        asset_id=ctx.asset_id,
        aisle_id=ctx.aisle_id,
        inventory_id=ctx.inventory_id,
        client_id=ctx.client_id,
        identification_mode=ctx.identification_mode,
        execution_strategy=ctx.execution_strategy,
        configuration_snapshot_version=ctx.configuration_snapshot_version,
        provider_name=ctx.provider_name,
        model_name=ctx.model_name,
        prompt_key=ctx.prompt_key,
        prompt_version=ctx.prompt_version,
        attempt_number=ctx.attempt_number,
        execution_scope=ctx.execution_scope,
        profile_aware_validation_enabled=True,
        supplier_extraction_profile={
            "configuration": default_extraction_configuration().to_public_dict()
        },
    )
    result = strategy.process(ctx, _asset())
    assert result.status is ImageResultStatus.RESOLVED_INTERNAL
    assert result.internal_code == "DINAMIC42"
    assert int(result.quantity) == 7
    assert not (result.evidence or {}).get("profile_validation_executed")


def test_real_qr_emits_per_asset_events() -> None:
    events: list[str] = []

    class _Capture:
        def publish(self, **kwargs):
            events.append(str(kwargs.get("event_type")))

    strategy = _strategy(_qr_png_bytes("EVT|1"), event_publisher=_Capture())
    result = strategy.process(_context(), _asset())
    assert result.status is ImageResultStatus.RESOLVED_INTERNAL
    assert "code_scan.asset_started" in events
    assert "asset.source_loaded" in events
    assert "code_scan.decode_started" in events
    assert "code_scan.decode_completed" in events
    assert "code_scan.symbols_detected" in events
    assert "code_scan.asset_finalized" in events


def test_real_code128_payload_resolves() -> None:
    from pathlib import Path

    fixture = (
        Path(__file__).resolve().parent / "fixtures" / "code128_c128test_3.png"
    )
    if not fixture.is_file():
        pytest.skip("CODE128 fixture missing")
    strategy = _strategy(fixture.read_bytes())
    result = strategy.process(_context(), _asset())
    assert result.status is ImageResultStatus.RESOLVED_INTERNAL
    assert result.internal_code == "C128TEST"
    assert int(result.quantity) == 3


def test_real_invalid_payload_is_unrecognized_or_manual() -> None:
    strategy = _strategy(_qr_png_bytes("|||"))
    result = strategy.process(_context(), _asset())
    assert result.status in (
        ImageResultStatus.UNRECOGNIZED,
        ImageResultStatus.PENDING_MANUAL_REVIEW,
    )


def test_real_corrupt_image_is_technical() -> None:
    strategy = _strategy(b"not-an-image")
    result = strategy.process(_context(), _asset())
    assert result.status is ImageResultStatus.FAILED_TECHNICAL
    assert result.error_code == "CODE_SCAN_SCANNER_ERROR"


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
