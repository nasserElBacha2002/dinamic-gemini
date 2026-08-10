"""Scanner variant / partial-timeout / multi-symbol coverage tests (fake scanner)."""

from __future__ import annotations

import io
import time
from datetime import datetime, timezone

from PIL import Image

from src.application.ports.code_scanner import CodeScanDetectionCandidate
from src.application.services.image_processing.code_detection_consolidator import (
    CodeDetectionConsolidator,
)
from src.application.services.image_processing.code_scan_processing_strategy import (
    CodeScanConfig,
    CodeScanProcessingStrategy,
    CodeScanTimeoutError,
)
from src.application.services.image_processing.code_scan_session import CodeScanStopReason
from src.application.services.image_processing.encoded_label_payload_parser import (
    EncodedLabelPayloadParser,
)
from src.domain.aisle_identification.modes import (
    AisleIdentificationExecutionStrategy,
    AisleIdentificationMode,
)
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.code_scans.entities import CodeScanDetectionStatus, CodeType
from src.domain.image_processing.contracts import (
    ExecutionScope,
    ImageProcessingContext,
    ImageResultStatus,
)
from src.domain.product_labels.format import build_product_label_payload


NOW = datetime(2026, 8, 10, tzinfo=timezone.utc)


class _AngleAwareScanner:
    """Returns different symbols depending on rotation PNG content / call order."""

    engine_name = "fake-angle"

    def __init__(self, by_call: list[list[CodeScanDetectionCandidate]]) -> None:
        self._by_call = list(by_call)
        self.calls = 0

    def scan_asset(self, asset, content=None):
        idx = min(self.calls, len(self._by_call) - 1)
        self.calls += 1
        return list(self._by_call[idx])


class _TimeoutAfterFirstScanner(_AngleAwareScanner):
    def scan_asset(self, asset, content=None):
        if self.calls >= 1:
            raise CodeScanTimeoutError("budget exhausted")
        return super().scan_asset(asset, content)


class _Reader:
    def __init__(self, content: bytes) -> None:
        self._content = content

    def read_image_bytes(self, asset) -> bytes:
        return self._content


def _cand(value: str) -> CodeScanDetectionCandidate:
    return CodeScanDetectionCandidate(
        code_type=CodeType.QR,
        code_value=value,
        detection_status=CodeScanDetectionStatus.DETECTED,
        metadata_json={"pyzbar_type": "QRCODE"},
    )


def _png_bytes(size: tuple[int, int] = (200, 200)) -> bytes:
    img = Image.new("RGB", size, color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _asset() -> SourceAsset:
    return SourceAsset(
        id="a1",
        aisle_id="aisle",
        type=SourceAssetType.PHOTO,
        original_filename="multi.png",
        storage_path="/multi.png",
        mime_type="image/png",
        uploaded_at=NOW,
    )


def _context() -> ImageProcessingContext:
    return ImageProcessingContext(
        job_id="j1",
        asset_id="a1",
        aisle_id="aisle",
        inventory_id="inv",
        client_id=None,
        identification_mode=AisleIdentificationMode.CODE_SCAN,
        execution_strategy=AisleIdentificationExecutionStrategy.CODE_SCAN,
        configuration_snapshot_version=1,
        provider_name=None,
        model_name=None,
        prompt_key=None,
        prompt_version=None,
        attempt_number=1,
        execution_scope=ExecutionScope.SINGLE_ASSET,
    )


def _strategy(scanner, content: bytes, **cfg) -> CodeScanProcessingStrategy:
    defaults = {"enable_rotations": True}
    defaults.update(cfg)
    return CodeScanProcessingStrategy(
        scanner=scanner,
        content_reader=_Reader(content),
        parser=EncodedLabelPayloadParser(quantity_max=99999999),
        consolidator=CodeDetectionConsolidator(),
        config=CodeScanConfig(quantity_max=99999999, **defaults),
    )


def test_merge_a_at_0_b_at_90() -> None:
    a = build_product_label_payload(label_id="A1B2C3D4E5", internal_code="SKU_A", quantity=1)
    b = build_product_label_payload(label_id="FGHJKMNPQR", internal_code="SKU_B", quantity=2)
    scanner = _AngleAwareScanner([[_cand(a)], [_cand(a), _cand(b)], [], []])
    strategy = _strategy(scanner, _png_bytes(), timeout_seconds=30)
    session = strategy._scan_with_variants(_asset(), _png_bytes(), started=time.monotonic())
    values = {c.code_value for c in session.candidates}
    assert a in values and b in values
    assert session.scan_complete is True
    assert session.stop_reason is CodeScanStopReason.COMPLETE


def test_timeout_partial_preserves_a_and_marks_incomplete() -> None:
    # Legacy PIPE so registry/client context is not required for RESOLVED_INTERNAL.
    a = "SKU_A|1000"
    scanner = _AngleAwareScanner([[_cand(a)], [_cand(a)]])
    content = _png_bytes()
    strategy = _strategy(scanner, content, timeout_seconds=30)
    calls = {"n": 0}
    original = strategy._check_timeout

    def _check(started: float) -> None:
        calls["n"] += 1
        if calls["n"] > 1:
            raise CodeScanTimeoutError("forced")
        original(started)

    strategy._check_timeout = _check  # type: ignore[method-assign]
    session = strategy._scan_with_variants(_asset(), content, started=time.monotonic())
    assert len(session.candidates) == 1
    assert session.candidates[0].code_value == a
    assert session.scan_complete is False
    assert session.stop_reason is CodeScanStopReason.TIMEOUT
    assert session.partial_timeout is True

    calls["n"] = 0
    result = strategy.process(_context(), _asset())
    assert result.status is ImageResultStatus.RESOLVED_INTERNAL
    assert "CODE_SCAN_PARTIAL_TIMEOUT" in (result.warnings or [])
    assert result.evidence is not None
    assert result.evidence.get("scan_complete") is False
    assert result.internal_code == "SKU_A"


def test_max_candidates_budget_covers_seven_symbols() -> None:
    from src.domain.product_labels.format import LABEL_ID_ALPHABET

    payloads = []
    for i in range(7):
        lid = "".join(LABEL_ID_ALPHABET[(i + j) % len(LABEL_ID_ALPHABET)] for j in range(10))
        payloads.append(
            build_product_label_payload(label_id=lid, internal_code=f"SKU{i}", quantity=i + 1)
        )
    scanner = _AngleAwareScanner([[_cand(p) for p in payloads]])
    strategy = _strategy(
        scanner, _png_bytes(), enable_rotations=False, max_candidates_per_asset=24
    )
    session = strategy._scan_with_variants(_asset(), _png_bytes(), started=time.monotonic())
    assert len(session.candidates) == 7
    assert session.scan_complete is True
