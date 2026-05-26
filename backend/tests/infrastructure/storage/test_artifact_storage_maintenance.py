from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.storage.artifact_storage_maintenance import (
    CONFIRM_DELETE_TOKEN,
    build_local_cleanup_roots,
    build_local_safe_roots,
    classify_relative_storage_key,
    classify_remote_object_key,
    cleanup_local_roots,
    delete_gcs_objects,
    is_protected_relative_key,
    list_gcs_objects,
    run_remote_cleanup,
)

_REGRESSION_SUPPLIER_REF = (
    "client_suppliers/f7f2b112-ad3e-48d0-aa03-aa95dceff896/"
    "reference_images/065b9151-ed44-4377-94ba-41e79894a0b3.jpg"
)


class _FakeBlob:
    def __init__(self, name: str, size: int) -> None:
        self.name = name
        self.size = size
        self.deleted = False

    def delete(self) -> None:
        self.deleted = True


class _FakeBucket:
    def __init__(self, blobs: dict[str, _FakeBlob]) -> None:
        self._blobs = blobs

    def list_blobs(self, *, prefix: str):
        for name, blob in self._blobs.items():
            if name.startswith(prefix):
                yield blob

    def blob(self, name: str) -> _FakeBlob:
        return self._blobs[name]


class _FakeGcsClient:
    def __init__(self, blobs: dict[str, _FakeBlob]) -> None:
        self._blobs = blobs

    def bucket(self, name: str) -> _FakeBucket:
        return _FakeBucket(self._blobs)


class _FakeGcsStore:
    def __init__(self, client: _FakeGcsClient) -> None:
        self._client = client
        self.bucket = "bucket-a"


def test_confirm_delete_token_is_inventory_scoped() -> None:
    assert CONFIRM_DELETE_TOKEN == "DELETE_INVENTORY_ARTIFACTS"


def test_regression_supplier_reference_path_is_protected() -> None:
    assert is_protected_relative_key(_REGRESSION_SUPPLIER_REF)
    assert (
        classify_relative_storage_key(_REGRESSION_SUPPLIER_REF, staging_prefix="capture/staging")
        == "skip_protected"
    )


def test_list_gcs_objects_only_under_prefix() -> None:
    client = _FakeGcsClient(
        {
            "v3/uploads/a.jpg": _FakeBlob("v3/uploads/a.jpg", 10),
            "v3/uploads/nested/b.jpg": _FakeBlob("v3/uploads/nested/b.jpg", 20),
            "other/c.jpg": _FakeBlob("other/c.jpg", 5),
        }
    )
    objs = list_gcs_objects(storage_client=client, bucket_name="bucket-a", prefix="v3/uploads/")
    keys = {o.key for o in objs}
    assert keys == {"v3/uploads/a.jpg", "v3/uploads/nested/b.jpg"}


def test_delete_gcs_objects_dry_run_does_not_delete() -> None:
    blobs = {"v3/uploads/a.jpg": _FakeBlob("v3/uploads/a.jpg", 10)}
    client = _FakeGcsClient(blobs)
    objs = list_gcs_objects(storage_client=client, bucket_name="bucket-a", prefix="v3/uploads/")
    deleted, _, _ = delete_gcs_objects(
        storage_client=client, bucket_name="bucket-a", objects=objs, dry_run=True
    )
    assert deleted == 0
    assert blobs["v3/uploads/a.jpg"].deleted is False


def test_run_remote_cleanup_refuses_empty_prefix() -> None:
    store = _FakeGcsStore(_FakeGcsClient({}))
    section = run_remote_cleanup(
        provider="gcs",
        artifact_store=store,
        prefix="",
        bucket="bucket-a",
        dry_run=True,
        staging_prefix="capture/staging",
    )
    assert section.skipped is True
    assert "prefix" in (section.skip_reason or "").lower()


def test_run_remote_cleanup_deletes_inventory_prefix_only() -> None:
    blobs = {
        "v3/uploads/aisles/x.jpg": _FakeBlob("v3/uploads/aisles/x.jpg", 10),
        f"v3/{_REGRESSION_SUPPLIER_REF}": _FakeBlob(f"v3/{_REGRESSION_SUPPLIER_REF}", 99),
        "v3/client_suppliers/other.jpg": _FakeBlob("v3/client_suppliers/other.jpg", 5),
    }
    store = _FakeGcsStore(_FakeGcsClient(blobs))
    section = run_remote_cleanup(
        provider="gcs",
        artifact_store=store,
        prefix="v3",
        bucket="bucket-a",
        dry_run=False,
        staging_prefix="capture/staging",
    )
    assert section.objects_found == 1
    assert section.objects_deleted == 1
    assert section.objects_skipped_protected >= 0
    assert blobs["v3/uploads/aisles/x.jpg"].deleted is True
    assert blobs[f"v3/{_REGRESSION_SUPPLIER_REF}"].deleted is False
    assert blobs["v3/client_suppliers/other.jpg"].deleted is False


def test_classify_remote_supplier_reference_as_protected() -> None:
    assert (
        classify_remote_object_key(
            f"v3/{_REGRESSION_SUPPLIER_REF}",
            bucket_prefix="v3",
            staging_prefix="capture/staging",
        )
        == "skip_protected"
    )


def test_local_cleanup_deletes_inventory_files_not_supplier_refs(tmp_path: Path) -> None:
    output = tmp_path / "output"
    uploads_root = output / "v3_uploads"
    inventory_file = uploads_root / "uploads" / "aisles" / "x.jpg"
    inventory_file.parent.mkdir(parents=True)
    inventory_file.write_bytes(b"abc")
    supplier_ref = uploads_root / Path(_REGRESSION_SUPPLIER_REF)
    supplier_ref.parent.mkdir(parents=True)
    supplier_ref.write_bytes(b"keep")
    (output / "other.txt").write_bytes(b"zzz")

    roots, v3_uploads = build_local_cleanup_roots(
        output_dir=str(output),
        staging_prefix="capture/staging",
        include_pipeline_temp=False,
    )
    ff, bf, fd, bd, skip_prot, skip_na, errors = cleanup_local_roots(
        roots=roots,
        v3_uploads_root=v3_uploads,
        staging_prefix="capture/staging",
        dry_run=False,
    )
    assert errors == []
    assert ff == 1
    assert fd == 1
    assert skip_prot >= 0
    assert not inventory_file.exists()
    assert supplier_ref.exists()
    assert (output / "other.txt").exists()


def test_local_cleanup_does_not_delete_under_client_suppliers_root(tmp_path: Path) -> None:
    output = tmp_path / "output"
    uploads_root = output / "v3_uploads"
    protected = uploads_root / "client_suppliers" / "abc" / "notes.txt"
    protected.parent.mkdir(parents=True)
    protected.write_bytes(b"notes")

    roots, v3_uploads = build_local_cleanup_roots(
        output_dir=str(output),
        staging_prefix="capture/staging",
        include_pipeline_temp=False,
    )
    _, _, fd, _, skip_prot, _, errors = cleanup_local_roots(
        roots=roots,
        v3_uploads_root=v3_uploads,
        staging_prefix="capture/staging",
        dry_run=False,
    )
    assert errors == []
    assert fd == 0
    assert protected.exists()
    assert skip_prot == 0


def test_local_dry_run_finds_inventory_scoped_files(tmp_path: Path) -> None:
    output = tmp_path / "output"
    inventory_file = output / "v3_uploads" / "jobs" / "job-1" / "run" / "log.jsonl"
    inventory_file.parent.mkdir(parents=True)
    inventory_file.write_bytes(b"{}")

    roots, v3_uploads = build_local_cleanup_roots(
        output_dir=str(output),
        staging_prefix="capture/staging",
        include_pipeline_temp=False,
    )
    ff, _, fd, _, _, _, _ = cleanup_local_roots(
        roots=roots,
        v3_uploads_root=v3_uploads,
        staging_prefix="capture/staging",
        dry_run=True,
    )
    assert ff == 1
    assert fd == 0
    assert inventory_file.exists()


def test_build_local_safe_roots_returns_allowlist_subdirs_only(tmp_path: Path) -> None:
    output = tmp_path / "output"
    (output / "v3_uploads" / "uploads").mkdir(parents=True)
    roots = build_local_safe_roots(output_dir=str(output), include_pipeline_temp=False)
    assert all("uploads" in str(r) or "jobs" in str(r) or "capture" in str(r) for r in roots)
    assert not any(str(r).endswith("v3_uploads") for r in roots)


def test_build_local_safe_roots_rejects_unsafe_output_dir() -> None:
    with pytest.raises(ValueError, match="unsafe"):
        build_local_safe_roots(output_dir="/", include_pipeline_temp=False)
