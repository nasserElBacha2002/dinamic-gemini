"""Admin storage cleanup API schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CleanupTarget = Literal["remote", "local", "both"]
CleanupMode = Literal["dry_run", "delete"]


class AdminStorageCleanupRequest(BaseModel):
    target: CleanupTarget = "both"
    mode: CleanupMode = "dry_run"
    confirm: str | None = Field(
        default=None,
        description="Required DELETE_INVENTORY_ARTIFACTS when mode=delete.",
    )
    include_legacy_local: bool = True
    include_pipeline_temp: bool = False


class RemoteCleanupSectionResponse(BaseModel):
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
    errors: list[str] = Field(default_factory=list)
    protected_prefixes: list[str] = Field(default_factory=list)
    allowed_prefixes: list[str] = Field(default_factory=list)


class LocalCleanupSectionResponse(BaseModel):
    output_dir: str
    safe_roots: list[str] = Field(default_factory=list)
    allowed_roots: list[str] = Field(default_factory=list)
    files_found: int = 0
    files_deleted: int = 0
    files_skipped_protected: int = 0
    files_skipped_not_allowed: int = 0
    bytes_found: int = 0
    bytes_deleted: int = 0
    skipped: bool = False
    skip_reason: str | None = None
    errors: list[str] = Field(default_factory=list)
    protected_roots: list[str] = Field(default_factory=list)


class AdminStorageCleanupResponse(BaseModel):
    ok: bool
    mode: CleanupMode
    target: CleanupTarget
    remote: RemoteCleanupSectionResponse
    local: LocalCleanupSectionResponse
