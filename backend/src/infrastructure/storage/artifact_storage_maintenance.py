"""
Admin-only artifact storage maintenance (inventory-scoped allowlist + protected prefixes).

Never deletes entire ``v3_uploads`` or configured remote bucket prefix roots.
Supplier/client-supplier reference images under ``client_suppliers/`` are always protected.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

CONFIRM_DELETE_TOKEN = "DELETE_INVENTORY_ARTIFACTS"
_MIN_REMOTE_PREFIX_LEN = 1

# Relative storage keys (no configured bucket prefix such as ``v3/``).
_DEFAULT_CAPTURE_STAGING_PREFIX = "capture/staging"
_INVENTORY_OPERATIONAL_PREFIXES: tuple[str, ...] = (
    "uploads/",
    "jobs/",
)

PROTECTED_RELATIVE_PREFIXES: tuple[str, ...] = (
    "client_suppliers/",
    "supplier_reference_images/",
)

PROTECTED_RELATIVE_SUBSTRINGS: tuple[str, ...] = (
    "/reference_images/",
)

PROTECTED_PREFIXES_REPORT: tuple[str, ...] = (
    "client_suppliers/",
    "client_suppliers/**/reference_images/",
    "supplier_reference_images/",
)

ObjectDisposition = Literal["eligible", "skip_protected", "skip_not_allowed"]


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
    objects_skipped_protected: int = 0
    objects_skipped_not_allowed: int = 0
    bytes_found: int = 0
    bytes_deleted: int = 0
    skipped: bool = False
    skip_reason: str | None = None
    errors: list[str] = field(default_factory=list)
    protected_prefixes: list[str] = field(default_factory=list)
    allowed_prefixes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class LocalCleanupRoot:
    path: Path
    inventory_scoped: bool = True


@dataclass
class LocalCleanupSection:
    output_dir: str
    safe_roots: list[str] = field(default_factory=list)
    allowed_roots: list[str] = field(default_factory=list)
    files_found: int = 0
    files_deleted: int = 0
    files_skipped_protected: int = 0
    files_skipped_not_allowed: int = 0
    bytes_found: int = 0
    bytes_deleted: int = 0
    skipped: bool = False
    skip_reason: str | None = None
    errors: list[str] = field(default_factory=list)
    protected_roots: list[str] = field(default_factory=list)


@dataclass
class StorageCleanupResult:
    ok: bool
    mode: str
    target: str
    remote: RemoteCleanupSection
    local: LocalCleanupSection


def _normalize_prefix(prefix: str) -> str:
    return (prefix or "").strip().strip("/")


def _normalize_relative_key(key: str) -> str:
    normalized = (key or "").strip().replace("\\", "/").lstrip("/")
    if normalized.startswith("v3/"):
        normalized = normalized[3:]
    return normalized


def inventory_operational_relative_prefixes(*, staging_prefix: str) -> tuple[str, ...]:
    staging = _normalize_prefix(staging_prefix) or _DEFAULT_CAPTURE_STAGING_PREFIX
    staging_key = f"{staging}/"
    return _INVENTORY_OPERATIONAL_PREFIXES + (staging_key,)


def is_protected_relative_key(relative_key: str) -> bool:
    key = _normalize_relative_key(relative_key)
    if not key:
        return False
    for protected in PROTECTED_RELATIVE_PREFIXES:
        if key.startswith(protected) or key == protected.rstrip("/"):
            return True
    for fragment in PROTECTED_RELATIVE_SUBSTRINGS:
        if fragment in f"/{key}/":
            return True
    return False


def is_allowlisted_relative_key(relative_key: str, *, staging_prefix: str) -> bool:
    key = _normalize_relative_key(relative_key)
    if not key:
        return False
    for allowed in inventory_operational_relative_prefixes(staging_prefix=staging_prefix):
        if key.startswith(allowed) or key == allowed.rstrip("/"):
            return True
    return False


def classify_relative_storage_key(
    relative_key: str,
    *,
    staging_prefix: str,
) -> ObjectDisposition:
    key = _normalize_relative_key(relative_key)
    if is_protected_relative_key(key):
        return "skip_protected"
    if is_allowlisted_relative_key(key, staging_prefix=staging_prefix):
        return "eligible"
    return "skip_not_allowed"


def classify_remote_object_key(
    physical_key: str,
    *,
    bucket_prefix: str,
    staging_prefix: str,
) -> ObjectDisposition:
    key = (physical_key or "").strip().replace("\\", "/")
    bp = _normalize_prefix(bucket_prefix)
    relative = key
    if bp and (relative == bp or relative.startswith(f"{bp}/")):
        relative = relative[len(bp) :].lstrip("/")
    elif bp == "" and relative.startswith("v3/"):
        relative = relative[3:]
    return classify_relative_storage_key(relative, staging_prefix=staging_prefix)


def _remote_prefix_guard(prefix: str) -> str:
    normalized = _normalize_prefix(prefix)
    if len(normalized) < _MIN_REMOTE_PREFIX_LEN:
        raise ValueError("Remote cleanup requires a non-empty object prefix")
    return f"{normalized}/"


def compose_physical_list_prefix(*, bucket_prefix: str, relative_prefix: str) -> str:
    bp = _normalize_prefix(bucket_prefix)
    rel = (relative_prefix or "").strip().strip("/")
    if not rel:
        raise ValueError("Refusing remote list with empty relative allowlist prefix")
    if bp:
        return f"{bp}/{rel}/"
    return f"{rel}/"


def list_gcs_objects(*, storage_client: Any, bucket_name: str, prefix: str) -> list[ObjectSummary]:
    physical_prefix = (prefix or "").strip()
    if not physical_prefix:
        raise ValueError("Refusing GCS list with empty prefix")
    if not physical_prefix.endswith("/"):
        physical_prefix = f"{physical_prefix}/"
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
    physical_prefix = prefix if prefix.endswith("/") else f"{prefix.rstrip('/')}/"
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


def build_local_cleanup_roots(
    *,
    output_dir: str,
    staging_prefix: str,
    include_pipeline_temp: bool,
) -> tuple[list[LocalCleanupRoot], Path | None]:
    base = Path(output_dir).resolve()
    if _is_unsafe_root(base):
        raise ValueError(f"Refusing local cleanup: unsafe output_dir={output_dir!r}")
    v3_uploads = (base / "v3_uploads").resolve()
    if _is_unsafe_root(v3_uploads):
        raise ValueError(f"Refusing local cleanup: unsafe v3_uploads root under {output_dir!r}")

    roots: list[LocalCleanupRoot] = []
    for rel in inventory_operational_relative_prefixes(staging_prefix=staging_prefix):
        candidate = (v3_uploads / rel.rstrip("/")).resolve()
        try:
            candidate.relative_to(v3_uploads)
        except ValueError:
            continue
        if not _is_unsafe_root(candidate):
            roots.append(LocalCleanupRoot(path=candidate, inventory_scoped=True))

    if include_pipeline_temp and base.is_dir():
        for child in base.iterdir():
            if not child.is_dir():
                continue
            run_dir = (child / "run").resolve()
            try:
                run_dir.relative_to(base)
            except ValueError:
                continue
            if run_dir.is_dir() and not _is_unsafe_root(run_dir):
                roots.append(LocalCleanupRoot(path=run_dir, inventory_scoped=False))

    return roots, v3_uploads


def build_local_safe_roots(
    *,
    output_dir: str,
    include_pipeline_temp: bool,
    staging_prefix: str = _DEFAULT_CAPTURE_STAGING_PREFIX,
) -> list[Path]:
    """Backward-compatible helper returning scan roots only."""
    roots, _ = build_local_cleanup_roots(
        output_dir=output_dir,
        staging_prefix=staging_prefix,
        include_pipeline_temp=include_pipeline_temp,
    )
    return [r.path for r in roots]


def _path_inside_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _relative_key_under_v3_uploads(file_path: Path, v3_uploads: Path) -> str | None:
    try:
        rel = file_path.resolve().relative_to(v3_uploads.resolve())
    except ValueError:
        return None
    return str(rel).replace("\\", "/")


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
            if candidate.is_symlink():
                continue
            if _path_inside_root(candidate, root):
                files.append(candidate)
    return files


def cleanup_local_roots(
    *,
    roots: list[LocalCleanupRoot],
    v3_uploads_root: Path | None,
    staging_prefix: str,
    dry_run: bool,
) -> tuple[int, int, int, int, int, int, list[str]]:
    files_found = 0
    bytes_found = 0
    files_deleted = 0
    bytes_deleted = 0
    files_skipped_protected = 0
    files_skipped_not_allowed = 0
    errors: list[str] = []
    for root_spec in roots:
        root = root_spec.path
        for file_path in scan_local_root(root):
            if file_path.is_symlink():
                files_skipped_not_allowed += 1
                continue
            if root_spec.inventory_scoped:
                if v3_uploads_root is None:
                    files_skipped_not_allowed += 1
                    continue
                rel_key = _relative_key_under_v3_uploads(file_path, v3_uploads_root)
                if rel_key is None:
                    files_skipped_not_allowed += 1
                    continue
                disposition = classify_relative_storage_key(rel_key, staging_prefix=staging_prefix)
                if disposition == "skip_protected":
                    files_skipped_protected += 1
                    continue
                if disposition == "skip_not_allowed":
                    files_skipped_not_allowed += 1
                    continue
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
        for root_spec in roots:
            _remove_empty_dirs(root_spec.path)
    return (
        files_found,
        bytes_found,
        files_deleted,
        bytes_deleted,
        files_skipped_protected,
        files_skipped_not_allowed,
        errors,
    )


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


def _partition_remote_objects(
    objects: list[ObjectSummary],
    *,
    bucket_prefix: str,
    staging_prefix: str,
) -> tuple[list[ObjectSummary], int, int]:
    eligible: list[ObjectSummary] = []
    skipped_protected = 0
    skipped_not_allowed = 0
    for obj in objects:
        disposition = classify_remote_object_key(
            obj.key,
            bucket_prefix=bucket_prefix,
            staging_prefix=staging_prefix,
        )
        if disposition == "eligible":
            eligible.append(obj)
        elif disposition == "skip_protected":
            skipped_protected += 1
        else:
            skipped_not_allowed += 1
    return eligible, skipped_protected, skipped_not_allowed


def run_remote_cleanup(
    *,
    provider: str,
    artifact_store: Any,
    prefix: str,
    bucket: str,
    dry_run: bool,
    staging_prefix: str,
) -> RemoteCleanupSection:
    prov = (provider or "").strip().lower()
    bucket_prefix = _normalize_prefix(prefix)
    allowed = list(inventory_operational_relative_prefixes(staging_prefix=staging_prefix))
    section = RemoteCleanupSection(
        provider=prov,
        bucket=bucket or None,
        prefix=bucket_prefix or None,
        protected_prefixes=list(PROTECTED_PREFIXES_REPORT),
        allowed_prefixes=allowed,
    )
    if prov == "local":
        section.skipped = True
        section.skip_reason = "artifact_storage_provider=local (no remote bucket)"
        return section
    if prov not in ("s3", "gcs"):
        section.skipped = True
        section.skip_reason = f"unsupported remote provider {prov!r}"
        return section
    if len(bucket_prefix) < _MIN_REMOTE_PREFIX_LEN:
        section.skipped = True
        section.skip_reason = "Remote cleanup requires a non-empty bucket object prefix"
        return section
    try:
        client = getattr(artifact_store, "_client", None)
        if client is None:
            raise RuntimeError(f"{prov.upper()} artifact store client unavailable")
        all_objects: list[ObjectSummary] = []
        for rel_prefix in allowed:
            list_prefix = compose_physical_list_prefix(
                bucket_prefix=bucket_prefix,
                relative_prefix=rel_prefix,
            )
            if prov == "gcs":
                all_objects.extend(
                    list_gcs_objects(
                        storage_client=client,
                        bucket_name=bucket,
                        prefix=list_prefix,
                    )
                )
            else:
                all_objects.extend(
                    list_s3_objects(
                        s3_client=client,
                        bucket_name=bucket,
                        prefix=list_prefix,
                    )
                )
        eligible, skipped_protected, skipped_not_allowed = _partition_remote_objects(
            all_objects,
            bucket_prefix=bucket_prefix,
            staging_prefix=staging_prefix,
        )
        if prov == "gcs":
            deleted, bytes_del, errors = delete_gcs_objects(
                storage_client=client,
                bucket_name=bucket,
                objects=eligible,
                dry_run=dry_run,
            )
        else:
            deleted, bytes_del, errors = delete_s3_objects(
                s3_client=client,
                bucket_name=bucket,
                objects=eligible,
                dry_run=dry_run,
            )
        section.objects_found = len(eligible)
        section.bytes_found = sum(o.size_bytes for o in eligible)
        section.objects_deleted = deleted
        section.bytes_deleted = bytes_del
        section.objects_skipped_protected = skipped_protected
        section.objects_skipped_not_allowed = skipped_not_allowed
        section.errors = errors
        logger.info(
            "storage_cleanup remote provider=%s bucket=%s prefix=%s dry_run=%s "
            "objects_found=%s skipped_protected=%s",
            prov,
            bucket,
            bucket_prefix,
            dry_run,
            section.objects_found,
            skipped_protected,
        )
    except Exception as exc:
        section.errors.append(str(exc))
        logger.exception(
            "storage_cleanup remote_failed provider=%s bucket=%s prefix=%s",
            prov,
            bucket,
            bucket_prefix,
        )
    return section
