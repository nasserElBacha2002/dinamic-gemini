"""Admin-only destructive storage cleanup (remote prefix + safe local roots)."""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any, Literal

from src.config import AppSettings
from src.infrastructure.storage.artifact_storage_maintenance import (
    CONFIRM_DELETE_TOKEN,
    LocalCleanupSection,
    RemoteCleanupSection,
    StorageCleanupResult,
    build_local_safe_roots,
    cleanup_local_roots,
    run_remote_cleanup,
)

logger = logging.getLogger(__name__)

CleanupTarget = Literal["remote", "local", "both"]
CleanupMode = Literal["dry_run", "delete"]


class AdminStorageCleanupError(ValueError):
    """Invalid cleanup request."""


class AdminStorageCleanupUseCase:
    def __init__(self, *, settings: AppSettings, artifact_store: Any) -> None:
        self._settings = settings
        self._artifact_store = artifact_store

    def execute(
        self,
        *,
        target: CleanupTarget = "both",
        mode: CleanupMode = "dry_run",
        confirm: str | None = None,
        include_legacy_local: bool = True,
        include_pipeline_temp: bool = False,
    ) -> StorageCleanupResult:
        if mode == "delete" and (confirm or "").strip() != CONFIRM_DELETE_TOKEN:
            raise AdminStorageCleanupError(
                f"confirm must be {CONFIRM_DELETE_TOKEN!r} when mode=delete"
            )
        dry_run = mode != "delete"
        remote = RemoteCleanupSection(provider="local", skipped=True, skip_reason="not requested")
        local = LocalCleanupSection(output_dir=(self._settings.output_dir or "output").strip())

        if target in ("remote", "both"):
            provider = (self._settings.artifact_storage_provider or "local").strip().lower()
            bucket = ""
            prefix = ""
            if provider == "s3":
                bucket = (self._settings.artifact_s3_bucket or "").strip()
                prefix = (self._settings.artifact_s3_prefix or "").strip()
            elif provider == "gcs":
                bucket = (self._settings.artifact_gcs_bucket or "").strip()
                prefix = (self._settings.artifact_gcs_prefix or "").strip()
            remote = run_remote_cleanup(
                provider=provider,
                artifact_store=self._artifact_store,
                prefix=prefix,
                bucket=bucket,
                dry_run=dry_run,
            )

        if target in ("local", "both"):
            output_dir = (self._settings.output_dir or "output").strip()
            local.output_dir = output_dir
            if not include_legacy_local:
                local.skipped = True
                local.skip_reason = "include_legacy_local=false"
            else:
                try:
                    roots = build_local_safe_roots(
                        output_dir=output_dir,
                        include_pipeline_temp=include_pipeline_temp,
                    )
                except ValueError as exc:
                    local.skipped = True
                    local.skip_reason = str(exc)
                    roots = []
                local.safe_roots = [str(r) for r in roots]
                if roots:
                    ff, bf, fd, bd, errors = cleanup_local_roots(roots=roots, dry_run=dry_run)
                    local.files_found = ff
                    local.bytes_found = bf
                    local.files_deleted = fd
                    local.bytes_deleted = bd
                    local.errors = errors
                    logger.info(
                        "storage_cleanup local dry_run=%s roots=%s files_found=%s",
                        dry_run,
                        local.safe_roots,
                        ff,
                    )
                elif not local.skip_reason:
                    local.skipped = True
                    local.skip_reason = "no safe local roots configured"

        ok = not (remote.errors or local.errors)
        return StorageCleanupResult(
            ok=ok,
            mode=mode,
            target=target,
            remote=remote,
            local=local,
        )

    @staticmethod
    def result_to_dict(result: StorageCleanupResult) -> dict[str, Any]:
        return {
            "ok": result.ok,
            "mode": result.mode,
            "target": result.target,
            "remote": asdict(result.remote),
            "local": asdict(result.local),
        }
