"""Tests for RunAisleCodeScanUseCase (Phase 2: content reader + scanner fakes)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

import pytest

from src.application.errors import (
    CodeScanMaxAssetsExceededError,
    NoSourceAssetsForCodeScanError,
)
from src.application.ports.code_scan_repository import CodeScanRepository
from src.application.ports.code_scanner import CodeScanDetectionCandidate, CodeScannerPort
from src.application.ports.contracts import AisleAssetRollup
from src.application.ports.repositories import AisleRepository, SourceAssetRepository
from src.application.ports.source_asset_content_reader import SourceAssetContentReader
from src.application.use_cases.code_scans.run_aisle_code_scan import (
    RunAisleCodeScanCommand,
    RunAisleCodeScanUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.code_scans.entities import (
    CodeScanDetection,
    CodeScanDetectionStatus,
    CodeScanRunStatus,
    CodeType,
)
from src.infrastructure.repositories.memory_code_scan_repository import MemoryCodeScanRepository


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class StubAisleRepo(AisleRepository):
    def __init__(self, aisle: Aisle) -> None:
        self._aisle = aisle

    def save(self, aisle: Aisle) -> None:
        self._aisle = aisle

    def get_by_id(self, aisle_id: str) -> Aisle | None:
        return self._aisle if self._aisle.id == aisle_id else None

    def list_by_inventory(self, inventory_id: str) -> Sequence[Aisle]:
        return [self._aisle] if self._aisle.inventory_id == inventory_id else []

    def get_by_inventory_and_code(self, inventory_id: str, code: str) -> Aisle | None:
        return None


class StubAssetRepo(SourceAssetRepository):
    def __init__(self, assets: Sequence[SourceAsset]) -> None:
        self._assets = {a.id: a for a in assets}

    def save(self, asset: SourceAsset) -> None:
        self._assets[asset.id] = asset

    def get_by_id(self, asset_id: str) -> SourceAsset | None:
        return self._assets.get(asset_id)

    def delete_by_id(self, asset_id: str) -> bool:
        return self._assets.pop(asset_id, None) is not None

    def list_by_aisle(self, aisle_id: str) -> Sequence[SourceAsset]:
        return [a for a in self._assets.values() if a.aisle_id == aisle_id]

    def get_by_capture_session_item_id(self, capture_session_item_id: str) -> SourceAsset | None:
        return None

    def get_by_upload_idempotency_key(
        self, aisle_id: str, upload_batch_id: str, upload_client_file_id: str
    ) -> SourceAsset | None:
        return None

    def summarize_assets_for_aisles(self, aisle_ids: Sequence[str]) -> dict[str, AisleAssetRollup]:
        return {}


class FakeCodeScanner:
    def __init__(
        self,
        *,
        by_asset: dict[str, list[CodeScanDetectionCandidate]] | None = None,
        fail_asset_ids: set[str] | None = None,
        engine: str = "fake",
    ) -> None:
        self._by_asset = by_asset or {}
        self._fail_asset_ids = fail_asset_ids or set()
        self._engine = engine
        self.last_content_by_asset: dict[str, bytes] = {}

    @property
    def engine_name(self) -> str:
        return self._engine

    def scan_asset(
        self, asset: SourceAsset, content: bytes | None = None
    ) -> list[CodeScanDetectionCandidate]:
        if asset.id in self._fail_asset_ids:
            raise RuntimeError("scan failed")
        if content is not None:
            self.last_content_by_asset[asset.id] = content
        return list(self._by_asset.get(asset.id, []))


class FakeContentReader(SourceAssetContentReader):
    def __init__(
        self,
        *,
        by_asset: dict[str, bytes] | None = None,
        fail_asset_ids: set[str] | None = None,
        default_bytes: bytes = b"\xff\xd8\xff\xd9",
    ) -> None:
        self._by_asset = by_asset or {}
        self._fail_asset_ids = fail_asset_ids or set()
        self._default = default_bytes

    def read_image_bytes(self, asset: SourceAsset) -> bytes:
        if asset.id in self._fail_asset_ids:
            raise FileNotFoundError(f"missing {asset.id}")
        return self._by_asset.get(asset.id, self._default)


def _aisle() -> Aisle:
    now = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
    return Aisle(
        id="aisle-1",
        inventory_id="inv-1",
        code="A1",
        status=AisleStatus.ASSETS_UPLOADED,
        created_at=now,
        updated_at=now,
    )


def _photo(
    asset_id: str,
    *,
    asset_type: SourceAssetType = SourceAssetType.PHOTO,
    mime_type: str = "image/jpeg",
    filename: str | None = None,
    storage_key: str | None = None,
) -> SourceAsset:
    now = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
    fname = filename or f"{asset_id}.jpg"
    return SourceAsset(
        id=asset_id,
        aisle_id="aisle-1",
        type=asset_type,
        original_filename=fname,
        storage_path=f"uploads/aisles/aisle-1/raw/{fname}",
        storage_key=storage_key or f"uploads/aisles/aisle-1/raw/{fname}",
        mime_type=mime_type,
        uploaded_at=now,
    )


def _use_case(
    *,
    assets: Sequence[SourceAsset],
    scanner: CodeScannerPort,
    content_reader: SourceAssetContentReader | None = None,
    code_scan_repo: CodeScanRepository | None = None,
    match_detections_use_case=None,
) -> RunAisleCodeScanUseCase:
    now = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
    return RunAisleCodeScanUseCase(
        aisle_repo=StubAisleRepo(_aisle()),
        asset_repo=StubAssetRepo(assets),
        code_scan_repo=code_scan_repo or MemoryCodeScanRepository(),
        scanner=scanner,
        content_reader=content_reader or FakeContentReader(),
        clock=FixedClock(now),
        match_detections_use_case=match_detections_use_case,
    )


def test_run_raises_when_no_assets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODE_SCAN_ENABLED", "true")
    from src.config import reload_settings

    reload_settings()
    uc = _use_case(assets=[], scanner=FakeCodeScanner())
    with pytest.raises(NoSourceAssetsForCodeScanError):
        uc.execute(RunAisleCodeScanCommand(inventory_id="inv-1", aisle_id="aisle-1"))


def test_run_completes_with_no_detections(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODE_SCAN_ENABLED", "true")
    from src.config import reload_settings

    reload_settings()
    result = _use_case(
        assets=[_photo("a1")],
        scanner=FakeCodeScanner(),
    ).execute(RunAisleCodeScanCommand(inventory_id="inv-1", aisle_id="aisle-1"))
    assert result.status == CodeScanRunStatus.COMPLETED
    assert result.total_codes_found == 0
    assert result.processed_assets == 1


def test_run_persists_fake_detections(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODE_SCAN_ENABLED", "true")
    from src.config import reload_settings

    reload_settings()
    repo = MemoryCodeScanRepository()
    scanner = FakeCodeScanner(
        by_asset={
            "a1": [
                CodeScanDetectionCandidate(code_type=CodeType.BARCODE, code_value=" 3075807 "),
                CodeScanDetectionCandidate(code_type=CodeType.BARCODE, code_value="3075807"),
            ],
            "a2": [CodeScanDetectionCandidate(code_type=CodeType.QR, code_value="QR-1")],
        },
    )
    result = _use_case(
        assets=[_photo("a1"), _photo("a2")],
        scanner=scanner,
        code_scan_repo=repo,
    ).execute(RunAisleCodeScanCommand(inventory_id="inv-1", aisle_id="aisle-1"))
    assert result.status == CodeScanRunStatus.COMPLETED
    assert result.total_codes_found == 2
    assert result.total_qr_found == 1
    assert result.total_barcodes_found == 1
    perf = (result.metadata_json or {}).get("performance") or {}
    assert perf.get("duration_ms", -1) >= 0
    assert perf.get("assets_per_second", -1) >= 0
    detections = repo.list_detections_for_run(result.run_id)
    assert len(detections) == 3
    dup = [d for d in detections if d.detection_status == CodeScanDetectionStatus.DUPLICATE]
    assert len(dup) == 1


def test_rerun_marks_previous_run_not_latest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODE_SCAN_ENABLED", "true")
    from src.config import reload_settings

    reload_settings()
    repo = MemoryCodeScanRepository()
    uc = _use_case(assets=[_photo("a1")], scanner=FakeCodeScanner(), code_scan_repo=repo)
    first = uc.execute(RunAisleCodeScanCommand(inventory_id="inv-1", aisle_id="aisle-1"))
    second = uc.execute(RunAisleCodeScanCommand(inventory_id="inv-1", aisle_id="aisle-1"))
    run1 = repo.get_latest_run_by_aisle(inventory_id="inv-1", aisle_id="aisle-1")
    assert run1 is not None
    assert run1.id == second.run_id
    assert run1.is_latest is True
    old = repo._runs[first.run_id]
    assert old.is_latest is False


def test_skipped_video_produces_warnings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODE_SCAN_ENABLED", "true")
    from src.config import reload_settings

    reload_settings()
    result = _use_case(
        assets=[_photo("v1", asset_type=SourceAssetType.VIDEO)],
        scanner=FakeCodeScanner(),
    ).execute(RunAisleCodeScanCommand(inventory_id="inv-1", aisle_id="aisle-1"))
    assert result.status == CodeScanRunStatus.COMPLETED_WITH_WARNINGS
    assert result.failed_assets == 1
    assert any("unsupported" in w.lower() for w in result.warnings)


def test_per_asset_scan_failure_completed_with_warnings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODE_SCAN_ENABLED", "true")
    from src.config import reload_settings

    reload_settings()
    result = _use_case(
        assets=[_photo("a1"), _photo("a2")],
        scanner=FakeCodeScanner(fail_asset_ids={"a2"}),
    ).execute(RunAisleCodeScanCommand(inventory_id="inv-1", aisle_id="aisle-1"))
    assert result.status == CodeScanRunStatus.COMPLETED_WITH_WARNINGS
    assert result.failed_assets == 1
    assert result.processed_assets == 1


def test_unexpected_repository_failure_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODE_SCAN_ENABLED", "true")
    from src.config import reload_settings

    reload_settings()

    class BrokenRepo(MemoryCodeScanRepository):
        def save_detections(self, detections: Sequence[CodeScanDetection]) -> None:
            raise RuntimeError("db down")

    uc = _use_case(
        assets=[_photo("a1")],
        scanner=FakeCodeScanner(
            by_asset={
                "a1": [CodeScanDetectionCandidate(code_type=CodeType.BARCODE, code_value="X")],
            },
        ),
        code_scan_repo=BrokenRepo(),
    )
    with pytest.raises(RuntimeError, match="db down"):
        uc.execute(RunAisleCodeScanCommand(inventory_id="inv-1", aisle_id="aisle-1"))


def test_run_persists_created_by(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODE_SCAN_ENABLED", "true")
    from src.config import reload_settings

    reload_settings()
    repo = MemoryCodeScanRepository()
    _use_case(
        assets=[_photo("a1")],
        scanner=FakeCodeScanner(),
        code_scan_repo=repo,
    ).execute(
        RunAisleCodeScanCommand(
            inventory_id="inv-1", aisle_id="aisle-1", created_by="admin-42"
        )
    )
    latest = repo.get_latest_run_by_aisle(inventory_id="inv-1", aisle_id="aisle-1")
    assert latest is not None
    assert latest.created_by == "admin-42"


def test_run_metadata_warnings_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODE_SCAN_ENABLED", "true")
    from src.config import reload_settings

    reload_settings()
    repo = MemoryCodeScanRepository()
    _use_case(
        assets=[_photo("v1", asset_type=SourceAssetType.VIDEO)],
        scanner=FakeCodeScanner(),
        code_scan_repo=repo,
    ).execute(RunAisleCodeScanCommand(inventory_id="inv-1", aisle_id="aisle-1"))
    latest = repo.get_latest_run_by_aisle(inventory_id="inv-1", aisle_id="aisle-1")
    assert latest is not None
    assert latest.metadata_json is not None
    assert isinstance(latest.metadata_json.get("warnings"), list)
    assert isinstance(latest.metadata_json.get("skipped_assets"), list)
    assert isinstance(latest.metadata_json.get("scanner_errors"), list)


def test_max_assets_exceeded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODE_SCAN_ENABLED", "true")
    monkeypatch.setenv("CODE_SCAN_MAX_ASSETS_PER_RUN", "1")
    from src.config import reload_settings

    reload_settings()
    uc = _use_case(
        assets=[_photo("a1"), _photo("a2")],
        scanner=FakeCodeScanner(),
    )
    with pytest.raises(CodeScanMaxAssetsExceededError):
        uc.execute(RunAisleCodeScanCommand(inventory_id="inv-1", aisle_id="aisle-1"))


def test_use_case_does_not_touch_position_layer() -> None:
    """Sanity: use case constructor has no position/product dependencies."""
    uc = RunAisleCodeScanUseCase(
        aisle_repo=StubAisleRepo(_aisle()),
        asset_repo=StubAssetRepo([]),
        code_scan_repo=MemoryCodeScanRepository(),
        scanner=FakeCodeScanner(),
        content_reader=FakeContentReader(),
        clock=FixedClock(datetime.now(timezone.utc)),
    )
    assert "position" not in repr(uc.__dict__).lower()


def test_content_is_read_and_passed_to_scanner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODE_SCAN_ENABLED", "true")
    from src.config import reload_settings

    reload_settings()
    payload = b"image-bytes-123"
    scanner = FakeCodeScanner(engine="pyzbar")
    _use_case(
        assets=[_photo("a1")],
        scanner=scanner,
        content_reader=FakeContentReader(by_asset={"a1": payload}),
    ).execute(RunAisleCodeScanCommand(inventory_id="inv-1", aisle_id="aisle-1"))
    assert scanner.last_content_by_asset["a1"] == payload


def test_storage_read_failure_completed_with_warnings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODE_SCAN_ENABLED", "true")
    from src.config import reload_settings

    reload_settings()
    repo = MemoryCodeScanRepository()
    result = _use_case(
        assets=[_photo("a1"), _photo("a2")],
        scanner=FakeCodeScanner(),
        content_reader=FakeContentReader(fail_asset_ids={"a2"}),
        code_scan_repo=repo,
    ).execute(RunAisleCodeScanCommand(inventory_id="inv-1", aisle_id="aisle-1"))
    assert result.status == CodeScanRunStatus.COMPLETED_WITH_WARNINGS
    assert result.failed_assets == 1
    latest = repo.get_latest_run_by_aisle(inventory_id="inv-1", aisle_id="aisle-1")
    assert latest is not None
    assert latest.metadata_json is not None
    assert latest.metadata_json.get("unreadable_assets")


def test_oversized_payload_skipped_with_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODE_SCAN_ENABLED", "true")
    monkeypatch.setenv("CODE_SCAN_MAX_DECODED_PAYLOAD_LENGTH", "4")
    from src.config import reload_settings

    reload_settings()
    long_val = "X" * 20
    result = _use_case(
        assets=[_photo("a1")],
        scanner=FakeCodeScanner(
            by_asset={"a1": [CodeScanDetectionCandidate(code_type=CodeType.QR, code_value=long_val)]},
            engine="pyzbar",
        ),
    ).execute(RunAisleCodeScanCommand(inventory_id="inv-1", aisle_id="aisle-1"))
    assert result.total_codes_found == 0
    assert any("max length" in w.lower() for w in result.warnings)


def test_unreadable_image_completed_with_warnings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODE_SCAN_ENABLED", "true")
    from src.config import reload_settings
    from src.infrastructure.code_scanning.image_decode import UnreadableImageError

    reload_settings()

    class UnreadableScanner:
        @property
        def engine_name(self) -> str:
            return "pyzbar"

        def scan_asset(self, asset, content=None):
            raise UnreadableImageError("corrupt")

    repo = MemoryCodeScanRepository()
    result = _use_case(
        assets=[_photo("a1")],
        scanner=UnreadableScanner(),
        code_scan_repo=repo,
    ).execute(RunAisleCodeScanCommand(inventory_id="inv-1", aisle_id="aisle-1"))
    assert result.status == CodeScanRunStatus.COMPLETED_WITH_WARNINGS
    latest = repo.get_latest_run_by_aisle(inventory_id="inv-1", aisle_id="aisle-1")
    assert latest is not None
    unreadable = latest.metadata_json.get("unreadable_assets") or []
    assert any(e.get("reason") == "unreadable_image" for e in unreadable)


def test_persists_scanner_engine_pyzbar(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODE_SCAN_ENABLED", "true")
    from src.config import reload_settings

    reload_settings()
    repo = MemoryCodeScanRepository()
    _use_case(
        assets=[_photo("a1")],
        scanner=FakeCodeScanner(
            by_asset={"a1": [CodeScanDetectionCandidate(code_type=CodeType.QR, code_value="Q1")]},
            engine="pyzbar",
        ),
        code_scan_repo=repo,
    ).execute(RunAisleCodeScanCommand(inventory_id="inv-1", aisle_id="aisle-1"))
    dets = repo.list_detections_for_run(
        repo.get_latest_run_by_aisle(inventory_id="inv-1", aisle_id="aisle-1").id
    )
    assert dets[0].scanner_engine == "pyzbar"


def test_matching_failure_does_not_fail_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.application.use_cases.code_scans.match_aisle_code_scan_detections import (
        MATCHING_WARNING_MESSAGE,
        MatchAisleCodeScanDetectionsCommand,
    )

    monkeypatch.setenv("CODE_SCAN_ENABLED", "true")
    from src.config import reload_settings

    reload_settings()

    class FailingMatcher:
        def execute(self, cmd: MatchAisleCodeScanDetectionsCommand):
            raise RuntimeError("matcher down")

    repo = MemoryCodeScanRepository()
    result = _use_case(
        assets=[_photo("a1")],
        scanner=FakeCodeScanner(
            by_asset={"a1": [CodeScanDetectionCandidate(code_type=CodeType.BARCODE, code_value="X")]},
        ),
        match_detections_use_case=FailingMatcher(),
        code_scan_repo=repo,
    ).execute(
        RunAisleCodeScanCommand(
            inventory_id="inv-1", aisle_id="aisle-1", job_id="job-ctx-1"
        )
    )
    assert result.status == CodeScanRunStatus.COMPLETED_WITH_WARNINGS
    assert MATCHING_WARNING_MESSAGE in result.warnings
    assert result.metadata_json is not None
    assert result.metadata_json.get("matching", {}).get("status") == "failed"
    latest = repo.get_latest_run_by_aisle(inventory_id="inv-1", aisle_id="aisle-1")
    assert latest is not None
    assert latest.metadata_json.get("matching", {}).get("status") == "failed"
