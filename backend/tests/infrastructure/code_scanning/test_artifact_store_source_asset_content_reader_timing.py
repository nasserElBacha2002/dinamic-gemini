"""Unit tests for storage fetch timing / slow-warning observability."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.infrastructure.code_scanning.artifact_store_source_asset_content_reader import (
    ArtifactStoreSourceAssetContentReader,
)
from src.infrastructure.storage.artifact_store import ArtifactDownload


class _FakeStore:
    storage_provider = "gcs"
    bucket = "dinamic-photos"

    def __init__(self, *, body: bytes = b"abc", fail: bool = False):
        self._body = body
        self._fail = fail
        self.get_object_calls = 0

    def get_object(self, key: str) -> ArtifactDownload:
        self.get_object_calls += 1
        if self._fail:
            raise RuntimeError("boom")
        return ArtifactDownload(
            content=self._body,
            content_type="image/jpeg",
            file_size_bytes=len(self._body),
            etag="e1",
        )


class _Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def _asset(**kwargs):
    base = {
        "id": "asset-1",
        "aisle_id": "aisle-1",
        "storage_key": "v3/path/img.jpg",
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_fast_fetch_records_diagnostics_without_slow_flag(caplog: pytest.LogCaptureFixture) -> None:
    clock = _Clock()
    store = _FakeStore(body=b"fast-bytes")

    def timed_get(key: str) -> ArtifactDownload:
        clock.advance(0.12)
        return ArtifactDownload(
            content=b"fast-bytes",
            content_type="image/jpeg",
            file_size_bytes=10,
            etag="e",
        )

    store.get_object = timed_get  # type: ignore[method-assign]
    reader = ArtifactStoreSourceAssetContentReader(
        store,  # type: ignore[arg-type]
        slow_warning_ms=10_000,
        monotonic_fn=clock,
    )

    with caplog.at_level("INFO"):
        content = reader.read_image_bytes(_asset())

    assert content == b"fast-bytes"
    diag = reader.last_fetch_diagnostics
    assert diag is not None
    assert diag["success"] is True
    assert diag["storage_backend"] == "GCS"
    assert diag["bucket"] == "dinamic-photos"
    assert diag["byte_length"] == 10
    assert diag["duration_ms"] >= 120
    assert diag["slow"] is False
    assert "asset.storage_fetch_slow" not in caplog.text
    assert "asset.storage_fetch_completed" in caplog.text


def test_slow_fetch_emits_warning_without_changing_bytes(caplog: pytest.LogCaptureFixture) -> None:
    clock = _Clock()
    store = _FakeStore(body=b"slow-bytes-xx")

    def timed_get(key: str) -> ArtifactDownload:
        clock.advance(12.5)
        return ArtifactDownload(
            content=b"slow-bytes-xx",
            content_type="image/jpeg",
            file_size_bytes=13,
            etag="e",
        )

    store.get_object = timed_get  # type: ignore[method-assign]
    reader = ArtifactStoreSourceAssetContentReader(
        store,  # type: ignore[arg-type]
        slow_warning_ms=10_000,
        monotonic_fn=clock,
    )

    with caplog.at_level("WARNING"):
        content = reader.read_image_bytes(_asset())

    assert content == b"slow-bytes-xx"
    diag = reader.last_fetch_diagnostics
    assert diag is not None
    assert diag["slow"] is True
    assert diag["duration_ms"] >= 12500
    assert "asset.storage_fetch_slow" in caplog.text


def test_fetch_exception_records_failed_diagnostics(caplog: pytest.LogCaptureFixture) -> None:
    clock = _Clock()
    store = _FakeStore(fail=True)

    def timed_fail(key: str):
        clock.advance(1.0)
        raise RuntimeError("network")

    store.get_object = timed_fail  # type: ignore[method-assign]
    reader = ArtifactStoreSourceAssetContentReader(
        store,  # type: ignore[arg-type]
        slow_warning_ms=10_000,
        monotonic_fn=clock,
    )

    with caplog.at_level("WARNING"), pytest.raises(FileNotFoundError):
        reader.read_image_bytes(_asset())

    diag = reader.last_fetch_diagnostics
    assert diag is not None
    assert diag["success"] is False
    assert diag["duration_ms"] == 1000
    assert diag["error_type"] == "RuntimeError"
    assert "asset.storage_fetch_failed" in caplog.text


def test_single_get_object_call_no_extra_head() -> None:
    clock = _Clock()
    store = _FakeStore(body=b"x")
    reader = ArtifactStoreSourceAssetContentReader(
        store,  # type: ignore[arg-type]
        monotonic_fn=clock,
    )
    reader.read_image_bytes(_asset())
    assert store.get_object_calls == 1
