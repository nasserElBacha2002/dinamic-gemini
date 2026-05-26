"""
Admin-only artifact storage maintenance (prefix-scoped remote + safe local roots).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CONFIRM_DELETE_TOKEN = "DELETE_ARTIFACTS"
_MIN_REMOTE_PREFIX_LEN = 1


@dataclass(frozen=True)
class ObjectSummary:
    key: str
    size_bytes: int


@dataclass
class RemoteCleanupSection:
    provider: str
    bucket: str | None = None
    prefix: str | None = None
    objects_found: int = 0
    objects_deleted: int = 0
    bytes_found: int = 0
    bytes_deleted: int = 0
    skipped: bool = False
    skip_reason: str | None = None
    errors: list[str] = field(default_factory=list)


@dataclass
class LocalCleanupSection:
    output_dir: str
    safe_roots: list[str] = field(default_factory=list)
    files_found: int = 0
    files_deleted: int = 0
    bytes_found: int = 0
    bytes_deleted: int = 0
    skipped: bool = False
    skip_reason: str | None = None
    errors: list[str] = field(default_factory=list)


@dataclass
class StorageCleanupResult:
    ok: bool
    mode: str
    target: str
    remote: RemoteCleanupSection
    local: LocalCleanupSection


def _normalize_prefix(prefix: str) -> str:
    p = (prefix or "").strip().strip("/")
    return p


def _remote_prefix_guard(prefix: str) -> str:
    normalized = _normalize_prefix(prefix)
    if len(normalized) < _MIN_REMOTE_PREFIX_LEN:
        raise ValueError("Remote cleanup requires a non-empty object prefix")
    return f"{normalized}/"


def list_gcs_objects(*, storage_client: Any, bucket_name: str, prefix: str) -> list[ObjectSummary]:
    physical_prefix = _remote_prefix_guard(prefix)
    bucket = storage_client.bucket(bucket_name)
    summaries: list[ObjectSummary] = []
    for blob in bucket.list_blobs(prefix=physical_prefix):
        name = (getattr(blob, "name", None) or "").strip()
        if not name or name.endswith("/"):
            continue
        size = int(getattr(blob, "size", None) or 0)
        summaries.append(ObjectSummary(key=name, size_bytes=size))
    return summaries


def delete_gcs_objects(
    *,
    storage_client: Any,
    bucket_name: str,
    objects: list[ObjectSummary],
    dry_run: bool,
) -> tuple[int, int, list[str]]:
    if dry_run or not objects:
        return 0, 0, []
    bucket = storage_client.bucket(bucket_name)
    deleted = 0
    bytes_deleted = 0
    errors: list[str] = []
    for obj in objects:
        try:
            bucket.blob(obj.key).delete()
            deleted += 1
            bytes_deleted += obj.size_bytes
        except Exception as exc:
            errors.append(f"gcs delete failed key={obj.key!r}: {exc}")
            logger.warning("gcs_cleanup_delete_failed key=%s", obj.key)
    return deleted, bytes_deleted, errors


def list_s3_objects(*, s3_client: Any, bucket_name: str, prefix: str) -> list[ObjectSummary]:
    physical_prefix = _remote_prefix_guard(prefix)
    summaries: list[ObjectSummary] = []
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket_name, Prefix=physical_prefix):
        for item in page.get("Contents") or []:
            key = (item.get("Key") or "").strip()
            if not key or key.endswith("/"):
                continue
            summaries.append(
                ObjectSummary(key=key, size_bytes=int(item.get("Size") or 0)),
            )
    return summaries


def delete_s3_objects(
    *,
    s3_client: Any,
    bucket_name: str,
    objects: list[ObjectSummary],
    dry_run: bool,
) -> tuple[int, int, list[str]]:
    if dry_run or not objects:
        return 0, 0, []
    deleted = 0
    bytes_deleted = 0
    errors: list[str] = []
    for obj in objects:
        try:
            s3_client.delete_object(Bucket=bucket_name, Key=obj.key)
            deleted += 1
            bytes_deleted += obj.size_bytes
        except Exception as exc:
            errors.append(f"s3 delete failed key={obj.key!r}: {exc}")
            logger.warning("s3_cleanup_delete_failed key=%s", obj.key)
    return deleted, bytes_deleted, errors


def _is_unsafe_root(root: Path) -> bool:
    resolved = root.resolve()
    if resolved == Path("/").resolve():
        return True
    home = Path.home().resolve()
    if resolved == home:
        return True
    if resolved == Path.cwd().resolve().anchor and str(resolved) in ("/", "\\"):
        return True
    parts = resolved.parts
    if len(parts) <= 1:
        return True
    return False


def build_local_safe_roots(
    *,
    output_dir: str,
    include_pipeline_temp: bool,
) -> list[Path]:
    base = Path(output_dir).resolve()
    if _is_unsafe_root(base):
        raise ValueError(f"Refusing local cleanup: unsafe output_dir={output_dir!r}")
    roots: list[Path] = []
    v3_uploads = (base / "v3_uploads").resolve()
    if not _is_unsafe_root(v3_uploads):
        roots.append(v3_uploads)
    if include_pipeline_temp:
        if base.is_dir():
            for child in base.iterdir():
                if not child.is_dir():
                    continue
                run_dir = (child / "run").resolve()
                try:
                    run_dir.relative_to(base)
                except ValueError:
                    continue
                if run_dir.is_dir() and not _is_unsafe_root(run_dir):
                    roots.append(run_dir)
    return roots


def _path_inside_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def scan_local_root(root: Path) -> list[Path]:
    if not root.exists():
        return []
    files: list[Path] = []
    for dirpath, _dirnames, filenames in os.walk(root, followlinks=False):
        base = Path(dirpath)
        if not _path_inside_root(base, root):
            continue
        for name in filenames:
            candidate = (base / name).resolve()
            if _path_inside_root(candidate, root):
                files.append(candidate)
    return files


def cleanup_local_roots(
    *,
    roots: list[Path],
    dry_run: bool,
) -> tuple[int, int, int, int, list[str]]:
    files_found = 0
    bytes_found = 0
    files_deleted = 0
    bytes_deleted = 0
    errors: list[str] = []
    for root in roots:
        for file_path in scan_local_root(root):
            try:
                size = int(file_path.stat().st_size)
            except OSError as exc:
                errors.append(f"stat failed path={file_path}: {exc}")
                continue
            files_found += 1
            bytes_found += size
            if dry_run:
                continue
            try:
                file_path.unlink(missing_ok=True)
                files_deleted += 1
                bytes_deleted += size
            except OSError as exc:
                errors.append(f"delete failed path={file_path}: {exc}")
                logger.warning("local_cleanup_delete_failed path=%s", file_path)
    if not dry_run:
        for root in roots:
            _remove_empty_dirs(root)
    return files_found, bytes_found, files_deleted, bytes_deleted, errors


def _remove_empty_dirs(root: Path) -> None:
    if not root.is_dir():
        return
    for dirpath, dirnames, filenames in os.walk(root, topdown=False, followlinks=False):
        current = Path(dirpath)
        if filenames:
            continue
        for name in dirnames:
            child = current / name
            try:
                if child.is_dir() and not any(child.iterdir()):
                    child.rmdir()
            except OSError:
                pass
        try:
            if current != root and current.is_dir() and not any(current.iterdir()):
                current.rmdir()
        except OSError:
            pass


def run_remote_cleanup(
    *,
    provider: str,
    artifact_store: Any,
    prefix: str,
    bucket: str,
    dry_run: bool,
) -> RemoteCleanupSection:
    prov = (provider or "").strip().lower()
    section = RemoteCleanupSection(provider=prov, bucket=bucket or None, prefix=_normalize_prefix(prefix))
    if prov == "local":
        section.skipped = True
        section.skip_reason = "artifact_storage_provider=local (no remote bucket)"
        return section
    if prov not in ("s3", "gcs"):
        section.skipped = True
        section.skip_reason = f"unsupported remote provider {prov!r}"
        return section
    try:
        physical_prefix = _remote_prefix_guard(prefix)
    except ValueError as exc:
        section.skipped = True
        section.skip_reason = str(exc)
        return section
    section.prefix = physical_prefix.rstrip("/")
    try:
        if prov == "gcs":
            client = getattr(artifact_store, "_client", None)
            if client is None:
                raise RuntimeError("GCS artifact store client unavailable")
            objects = list_gcs_objects(
                storage_client=client, bucket_name=bucket, prefix=prefix
            )
            deleted, bytes_del, errors = delete_gcs_objects(
                storage_client=client,
                bucket_name=bucket,
                objects=objects,
                dry_run=dry_run,
            )
        else:
            client = getattr(artifact_store, "_client", None)
            if client is None:
                raise RuntimeError("S3 artifact store client unavailable")
            objects = list_s3_objects(s3_client=client, bucket_name=bucket, prefix=prefix)
            deleted, bytes_del, errors = delete_s3_objects(
                s3_client=client,
                bucket_name=bucket,
                objects=objects,
                dry_run=dry_run,
            )
        section.objects_found = len(objects)
        section.bytes_found = sum(o.size_bytes for o in objects)
        section.objects_deleted = deleted
        section.bytes_deleted = bytes_del
        section.errors = errors
        logger.info(
            "storage_cleanup remote provider=%s bucket=%s prefix=%s dry_run=%s objects_found=%s",
            prov,
            bucket,
            section.prefix,
            dry_run,
            section.objects_found,
        )
    except Exception as exc:
        section.errors.append(str(exc))
        logger.exception(
            "storage_cleanup remote_failed provider=%s bucket=%s prefix=%s",
            prov,
            bucket,
            section.prefix,
        )
    return section
