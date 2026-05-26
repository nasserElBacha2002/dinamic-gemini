from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.infrastructure.pipeline.input_artifact_resolver import WorkerInputArtifactResolver


class _Ref:
    def __init__(
        self,
        *,
        storage_provider: str | None,
        storage_key: str | None,
        storage_bucket: str | None = None,
        storage_path: str = "",
        filename: str = "ref.jpg",
        mime_type: str = "image/jpeg",
    ) -> None:
        self.id = "ref-1"
        self.storage_provider = storage_provider
        self.storage_key = storage_key
        self.storage_bucket = storage_bucket
        self.storage_path = storage_path
        self.filename = filename
        self.mime_type = mime_type


def test_resolve_visual_reference_local_reads_from_legacy_base_not_remote_store(
    tmp_path: Path,
) -> None:
    legacy_base = tmp_path / "v3_uploads"
    key = "client_suppliers/sup-1/reference_images/ref-1.jpg"
    src_file = legacy_base / key
    src_file.parent.mkdir(parents=True)
    src_file.write_bytes(b"local-bytes")

    remote_store = MagicMock()
    remote_store.bucket = "remote-bucket"
    remote_store.download_to_path.side_effect = RuntimeError("should not call remote store")

    resolver = WorkerInputArtifactResolver(
        remote_store,
        legacy_base=legacy_base,
        legacy_local_read_enabled=True,
    )
    target = tmp_path / "work" / "ref.jpg"
    out = resolver.resolve_visual_reference(
        "ref-1",
        reference_record=_Ref(storage_provider="local", storage_key=key),
        source_path="",
        target_path=target,
    )
    assert out == target
    assert out.read_bytes() == b"local-bytes"
    remote_store.download_to_path.assert_not_called()


def test_resolve_visual_reference_gcs_uses_artifact_store(tmp_path: Path) -> None:
    legacy_base = tmp_path / "v3_uploads"
    legacy_base.mkdir()

    def _fake_download(key: str, target_path: Path, *, bucket: str | None = None) -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(b"gcs-bytes")

    remote_store = MagicMock()
    remote_store.bucket = "my-bucket"
    remote_store.download_to_path.side_effect = _fake_download

    resolver = WorkerInputArtifactResolver(
        remote_store,
        legacy_base=legacy_base,
        legacy_local_read_enabled=True,
    )
    target = tmp_path / "work" / "ref.jpg"
    out = resolver.resolve_visual_reference(
        "ref-1",
        reference_record=_Ref(
            storage_provider="gcs",
            storage_bucket="my-bucket",
            storage_key="client_suppliers/sup-1/reference_images/ref-1.jpg",
        ),
        source_path="",
        target_path=target,
    )
    assert out.read_bytes() == b"gcs-bytes"
    remote_store.download_to_path.assert_called_once()


def test_resolve_visual_reference_local_missing_file_raises_clear_error(tmp_path: Path) -> None:
    legacy_base = tmp_path / "v3_uploads"
    legacy_base.mkdir()
    resolver = WorkerInputArtifactResolver(
        MagicMock(),
        legacy_base=legacy_base,
        legacy_local_read_enabled=True,
    )
    with pytest.raises(RuntimeError, match="local provider file not found"):
        resolver.resolve_visual_reference(
            "ref-1",
            reference_record=_Ref(
                storage_provider="local",
                storage_key="client_suppliers/sup-1/reference_images/missing.jpg",
            ),
            source_path="",
            target_path=tmp_path / "out.jpg",
        )
