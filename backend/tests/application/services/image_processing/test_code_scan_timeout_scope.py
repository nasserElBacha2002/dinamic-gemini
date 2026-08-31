"""CODE_SCAN decode-budget scoping: source load must not consume variants budget.

Regression coverage for slow storage + fast decode (incident class: asset-wide
clock started before read_image_bytes).
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.ports.code_scanner import CodeScanDetectionCandidate
from src.application.services.image_processing.code_detection_consolidator import (
    CodeDetectionConsolidator,
)
from src.application.services.image_processing.code_scan_processing_strategy import (
    CodeScanConfig,
    CodeScanProcessingStrategy,
)
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


class FakeMonotonic:
    def __init__(self, start: float = 1000.0) -> None:
        self.t = float(start)

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += float(seconds)


class ClockAwareReader:
    def __init__(self, content: bytes, clock: FakeMonotonic, load_seconds: float) -> None:
        self._content = content
        self._clock = clock
        self._load_seconds = load_seconds

    def read_image_bytes(self, asset) -> bytes:
        self._clock.advance(self._load_seconds)
        return self._content


class ClockAwareScanner:
    engine_name = "fake"

    def __init__(
        self,
        candidates: list[CodeScanDetectionCandidate],
        clock: FakeMonotonic,
        decode_seconds: float = 0.0,
    ) -> None:
        self._candidates = candidates
        self._clock = clock
        self._decode_seconds = decode_seconds
        self.calls = 0

    def scan_asset(self, asset, content=None):
        self.calls += 1
        self._clock.advance(self._decode_seconds)
        return list(self._candidates)


class PerCallDelayScanner:
    """Returns the same candidate list each call; advances clock by per-call delays."""

    engine_name = "fake-per-call"

    def __init__(
        self,
        candidates_by_call: list[list[CodeScanDetectionCandidate]],
        clock: FakeMonotonic,
        decode_seconds_by_call: list[float],
    ) -> None:
        self._candidates_by_call = candidates_by_call
        self._clock = clock
        self._delays = decode_seconds_by_call
        self.calls = 0

    def scan_asset(self, asset, content=None):
        idx = min(self.calls, len(self._delays) - 1)
        delay = self._delays[idx]
        cands = self._candidates_by_call[min(self.calls, len(self._candidates_by_call) - 1)]
        self.calls += 1
        self._clock.advance(delay)
        return list(cands)


class CapturePublisher:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def publish(self, **kwargs) -> None:
        self.events.append(kwargs)

    def by_type(self, event_type: str) -> list[dict]:
        return [e for e in self.events if e.get("event_type") == event_type]


def _candidate(value: str = "ABC|5") -> CodeScanDetectionCandidate:
    return CodeScanDetectionCandidate(
        code_type=CodeType.QR,
        code_value=value,
        detection_status=CodeScanDetectionStatus.DETECTED,
        metadata_json={"pyzbar_type": "QRCODE"},
    )


def _asset() -> SourceAsset:
    return SourceAsset(
        id="asset1",
        aisle_id="a1",
        type=SourceAssetType.PHOTO,
        original_filename="asset1.jpg",
        storage_path="/asset1.jpg",
        mime_type="image/jpeg",
        uploaded_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _context() -> ImageProcessingContext:
    return ImageProcessingContext(
        job_id="job1",
        asset_id="asset1",
        aisle_id="a1",
        inventory_id="inv1",
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


def _strategy(
    *,
    scanner,
    reader,
    clock: FakeMonotonic,
    events: CapturePublisher | None = None,
    timeout_seconds: int = 5,
    enable_rotations: bool = False,
) -> CodeScanProcessingStrategy:
    return CodeScanProcessingStrategy(
        scanner=scanner,
        content_reader=reader,
        parser=EncodedLabelPayloadParser(quantity_max=99999999),
        consolidator=CodeDetectionConsolidator(),
        config=CodeScanConfig(
            quantity_max=99999999,
            timeout_seconds=timeout_seconds,
            enable_rotations=enable_rotations,
        ),
        event_publisher=events,
        monotonic_fn=clock,
    )


def _stub_fast_image(strategy: CodeScanProcessingStrategy) -> None:
    strategy._prepared_scan_bytes = lambda content, *, angle: content  # type: ignore[method-assign]
    strategy._image_dimensions = lambda content: {  # type: ignore[method-assign]
        "original_width": 1,
        "original_height": 1,
        "processed_width": 1,
        "processed_height": 1,
        "scale_ratio": 1.0,
    }


def test_slow_source_load_must_not_consume_variants_budget() -> None:
    """Slow source load must not consume variants budget (acceptance A / regression)."""
    clock = FakeMonotonic()
    events = CapturePublisher()
    scanner = ClockAwareScanner([_candidate("ABC|5")], clock, decode_seconds=0.1)
    reader = ClockAwareReader(b"bytes", clock, load_seconds=19.0)
    strategy = _strategy(
        scanner=scanner, reader=reader, clock=clock, events=events, timeout_seconds=5
    )
    _stub_fast_image(strategy)

    result = strategy.process(_context(), _asset())
    assert result.status is ImageResultStatus.RESOLVED_INTERNAL
    assert result.error_code is None
    assert scanner.calls >= 1
    assert events.by_type("code_scan.decode_failed") == []
    loaded = events.by_type("asset.source_loaded")[0]
    assert loaded["metadata"]["source_load_ms"] >= 19000


def test_first_timeout_check_sees_near_zero_after_slow_load() -> None:
    clock = FakeMonotonic()
    scanner = ClockAwareScanner([], clock, decode_seconds=0.0)
    reader = ClockAwareReader(b"bytes", clock, load_seconds=20.0)
    strategy = _strategy(scanner=scanner, reader=reader, clock=clock, timeout_seconds=5)
    _stub_fast_image(strategy)

    seen: list[float] = []
    original = strategy._check_timeout

    def _wrap(decode_budget_started_at: float, **kwargs):
        seen.append(clock() - decode_budget_started_at)
        return original(decode_budget_started_at, **kwargs)

    strategy._check_timeout = _wrap  # type: ignore[method-assign]
    strategy.process(_context(), _asset())
    assert seen, "expected at least one timeout check"
    assert seen[0] < 0.5


def test_base_decoder_exceeds_budget_rotations_disabled() -> None:
    """Base decoder overrun must timeout even when rotations are disabled."""
    clock = FakeMonotonic()
    events = CapturePublisher()
    scanner = ClockAwareScanner([], clock, decode_seconds=6.0)
    reader = ClockAwareReader(b"bytes", clock, load_seconds=0.1)
    strategy = _strategy(
        scanner=scanner,
        reader=reader,
        clock=clock,
        events=events,
        timeout_seconds=5,
        enable_rotations=False,
    )
    _stub_fast_image(strategy)

    result = strategy.process(_context(), _asset())
    assert result.status is ImageResultStatus.FAILED_TECHNICAL
    assert result.error_code == "CODE_SCAN_TIMEOUT"
    assert result.evidence is not None
    assert result.evidence["timeout_phase"] == "decode"
    assert result.evidence["configured_budget_ms"] == 5000
    assert result.evidence["remaining_budget_ms"] == 0
    failed = events.by_type("code_scan.decode_failed")[0]
    assert failed["metadata"]["timeout_phase"] == "decode"


def test_base_decoder_timeout_after_candidate_is_partial() -> None:
    clock = FakeMonotonic()
    scanner = ClockAwareScanner([_candidate("SKU_A|1000")], clock, decode_seconds=6.0)
    reader = ClockAwareReader(b"bytes", clock, load_seconds=0.05)
    strategy = _strategy(
        scanner=scanner,
        reader=reader,
        clock=clock,
        timeout_seconds=5,
        enable_rotations=False,
    )
    _stub_fast_image(strategy)

    result = strategy.process(_context(), _asset())
    assert result.status is ImageResultStatus.RESOLVED_INTERNAL
    assert "CODE_SCAN_PARTIAL_TIMEOUT" in (result.warnings or [])
    assert result.evidence is not None
    assert result.evidence.get("scan_complete") is False
    assert result.internal_code == "SKU_A"


def test_slow_prepare_exceeds_decode_budget() -> None:
    clock = FakeMonotonic()
    events = CapturePublisher()
    scanner = ClockAwareScanner([_candidate()], clock, decode_seconds=0.0)
    reader = ClockAwareReader(b"bytes", clock, load_seconds=0.05)
    strategy = _strategy(
        scanner=scanner, reader=reader, clock=clock, events=events, timeout_seconds=5
    )
    strategy._image_dimensions = lambda content: {  # type: ignore[method-assign]
        "original_width": 1,
        "original_height": 1,
        "processed_width": 1,
        "processed_height": 1,
        "scale_ratio": 1.0,
    }

    def _slow_prepare(content: bytes, *, angle: int) -> bytes:
        clock.advance(6.0)
        return content

    strategy._prepared_scan_bytes = _slow_prepare  # type: ignore[method-assign]

    result = strategy.process(_context(), _asset())
    assert result.status is ImageResultStatus.FAILED_TECHNICAL
    assert result.error_code == "CODE_SCAN_TIMEOUT"
    assert result.evidence is not None
    assert result.evidence["timeout_phase"] == "decode"
    assert scanner.calls == 0  # timed out after prepare, before decoder


def test_rotation_prepare_exceeds_budget_before_decoder() -> None:
    clock = FakeMonotonic()
    events = CapturePublisher()
    scanner = ClockAwareScanner([], clock, decode_seconds=4.0)
    reader = ClockAwareReader(b"bytes", clock, load_seconds=0.05)
    strategy = _strategy(
        scanner=scanner,
        reader=reader,
        clock=clock,
        events=events,
        timeout_seconds=5,
        enable_rotations=True,
    )
    strategy._image_dimensions = lambda content: {  # type: ignore[method-assign]
        "original_width": 1,
        "original_height": 1,
        "processed_width": 1,
        "processed_height": 1,
        "scale_ratio": 1.0,
    }

    def _prep(content: bytes, *, angle: int) -> bytes:
        if angle == 0:
            return content
        clock.advance(3.0)  # remaining after base decode (~4s) is ~1s
        return content

    strategy._prepared_scan_bytes = _prep  # type: ignore[method-assign]

    result = strategy.process(_context(), _asset())
    assert result.status is ImageResultStatus.FAILED_TECHNICAL
    assert result.error_code == "CODE_SCAN_TIMEOUT"
    assert scanner.calls == 1  # base only; rotation decoder never started


def test_final_rotation_decoder_exceeds_budget() -> None:
    clock = FakeMonotonic()
    events = CapturePublisher()
    scanner = PerCallDelayScanner(
        candidates_by_call=[[], [], [], []],
        clock=clock,
        decode_seconds_by_call=[0.1, 0.1, 0.1, 6.0],
    )
    reader = ClockAwareReader(b"bytes", clock, load_seconds=0.05)
    strategy = _strategy(
        scanner=scanner,
        reader=reader,
        clock=clock,
        events=events,
        timeout_seconds=5,
        enable_rotations=True,
    )
    _stub_fast_image(strategy)

    result = strategy.process(_context(), _asset())
    assert result.status is ImageResultStatus.FAILED_TECHNICAL
    assert result.error_code == "CODE_SCAN_TIMEOUT"
    assert scanner.calls == 4


def test_final_rotation_timeout_preserves_prior_candidates() -> None:
    clock = FakeMonotonic()
    scanner = PerCallDelayScanner(
        candidates_by_call=[
            [_candidate("SKU_A|1000")],
            [],
            [],
            [],
        ],
        clock=clock,
        decode_seconds_by_call=[0.1, 0.1, 0.1, 6.0],
    )
    reader = ClockAwareReader(b"bytes", clock, load_seconds=0.05)
    strategy = _strategy(
        scanner=scanner,
        reader=reader,
        clock=clock,
        timeout_seconds=5,
        enable_rotations=True,
    )
    _stub_fast_image(strategy)

    result = strategy.process(_context(), _asset())
    assert result.status is ImageResultStatus.RESOLVED_INTERNAL
    assert "CODE_SCAN_PARTIAL_TIMEOUT" in (result.warnings or [])
    assert result.internal_code == "SKU_A"


def test_fast_path_no_symbols_is_unrecognized() -> None:
    clock = FakeMonotonic()
    events = CapturePublisher()
    scanner = ClockAwareScanner([], clock, decode_seconds=0.05)
    reader = ClockAwareReader(b"bytes", clock, load_seconds=0.05)
    strategy = _strategy(
        scanner=scanner, reader=reader, clock=clock, events=events, timeout_seconds=5
    )
    _stub_fast_image(strategy)

    result = strategy.process(_context(), _asset())
    assert result.status is ImageResultStatus.UNRECOGNIZED
    assert result.error_code == "NO_CODE_SYMBOL_FOUND"
    completed = events.by_type("code_scan.decode_completed")[0]
    assert completed["error_code"] == "NO_CODE_SYMBOL_FOUND"
    assert "source_load_ms" in completed["metadata"]
    assert "prepare_ms" in completed["metadata"]


def test_observability_events_include_phase_timings_on_success() -> None:
    clock = FakeMonotonic()
    events = CapturePublisher()
    scanner = ClockAwareScanner([_candidate("SKU|2")], clock, decode_seconds=0.2)
    reader = ClockAwareReader(b"bytes", clock, load_seconds=1.5)
    strategy = _strategy(
        scanner=scanner, reader=reader, clock=clock, events=events, timeout_seconds=5
    )
    _stub_fast_image(strategy)

    result = strategy.process(_context(), _asset())
    assert result.status is ImageResultStatus.RESOLVED_INTERNAL
    types = [e["event_type"] for e in events.events]
    assert "code_scan.source_load_started" in types
    assert "asset.source_loaded" in types
    assert "code_scan.decode_started" in types
    assert "code_scan.prepare_started" in types
    assert "code_scan.prepare_completed" in types
    assert "code_scan.decoder_variant_started" in types
    assert "code_scan.decode_completed" in types
    # decode_started must appear after source_loaded
    assert types.index("asset.source_loaded") < types.index("code_scan.decode_started")
    loaded = events.by_type("asset.source_loaded")[0]
    assert loaded["metadata"]["byte_length"] == 5
    assert loaded["metadata"]["source_load_ms"] >= 1500


def test_source_load_failed_emits_event() -> None:
    clock = FakeMonotonic()
    events = CapturePublisher()
    scanner = ClockAwareScanner([], clock)

    class _FailReader:
        def read_image_bytes(self, asset) -> bytes:
            clock.advance(0.2)
            raise FileNotFoundError("missing")

    strategy = _strategy(
        scanner=scanner, reader=_FailReader(), clock=clock, events=events, timeout_seconds=5
    )
    result = strategy.process(_context(), _asset())
    assert result.status is ImageResultStatus.FAILED_TECHNICAL
    assert result.error_code == "SOURCE_ASSET_NOT_FOUND"
    failed = events.by_type("asset.source_load_failed")[0]
    assert failed["metadata"]["error_type"] == "FileNotFoundError"
    assert failed["metadata"]["source_load_ms"] >= 200
