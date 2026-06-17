"""
Phase 4.3 — Canonical execution image manifest for photo-based V3 runs.

Single immutable runtime contract describing the exact images participating in one
provider execution. Drives prompt composition, provider payload ordering, and
traceability validation projections.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


MANIFEST_VERSION = 1
COMPOSITION_KEY_EXECUTION_IMAGE_MANIFEST = "execution_image_manifest"

# Canonical provider-return field for evidence (stable source asset ID, not manifest_entry_id).
EVIDENCE_RETURN_IDENTIFIER_FIELD = "source_image_id"


class ExecutionImageManifestError(ValueError):
    """Raised when manifest invariants fail or the manifest cannot authorize execution."""


class ExecutionImageRole(str, Enum):
    PRIMARY_EVIDENCE = "primary_evidence"
    REFERENCE_IMAGE = "reference_image"


class ImageExclusionReason(str, Enum):
    FRAME_CAP = "frame_cap"
    PROVIDER_LIMIT = "provider_limit"
    DECODE_FAILED = "decode_failed"
    INVALID_FORMAT = "invalid_format"
    DUPLICATE = "duplicate"
    MISSING_STORAGE_OBJECT = "missing_storage_object"
    FILTERED = "filtered"


@dataclass(frozen=True)
class ExecutionImageEntry:
    """One active image in the final provider execution set."""

    manifest_entry_id: str
    source_asset_id: str
    source_image_id: str
    role: ExecutionImageRole
    payload_ordinal: int
    storage_reference: str
    original_filename: str | None = None
    content_hash: str | None = None
    mime_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_entry_id": self.manifest_entry_id,
            "source_asset_id": self.source_asset_id,
            "source_image_id": self.source_image_id,
            "role": self.role.value,
            "payload_ordinal": self.payload_ordinal,
            "storage_reference": self.storage_reference,
            "original_filename": self.original_filename,
            "content_hash": self.content_hash,
            "mime_type": self.mime_type,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ExecutionImageEntry:
        role_raw = str(raw.get("role") or "").strip()
        role = ExecutionImageRole(role_raw)
        return cls(
            manifest_entry_id=str(raw["manifest_entry_id"]).strip(),
            source_asset_id=str(raw["source_asset_id"]).strip(),
            source_image_id=str(raw["source_image_id"]).strip(),
            role=role,
            payload_ordinal=int(raw["payload_ordinal"]),
            storage_reference=str(raw.get("storage_reference") or "").strip(),
            original_filename=(
                str(raw["original_filename"]).strip()
                if raw.get("original_filename") not in (None, "")
                else None
            ),
            content_hash=(
                str(raw["content_hash"]).strip()
                if raw.get("content_hash") not in (None, "")
                else None
            ),
            mime_type=(
                str(raw["mime_type"]).strip() if raw.get("mime_type") not in (None, "") else None
            ),
        )


@dataclass(frozen=True)
class ExcludedExecutionImage:
    """Candidate image removed before execution (operational metadata only)."""

    source_asset_id: str
    source_image_id: str
    reason: ImageExclusionReason
    original_filename: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_asset_id": self.source_asset_id,
            "source_image_id": self.source_image_id,
            "reason": self.reason.value,
            "original_filename": self.original_filename,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ExcludedExecutionImage:
        return cls(
            source_asset_id=str(raw["source_asset_id"]).strip(),
            source_image_id=str(raw["source_image_id"]).strip(),
            reason=ImageExclusionReason(str(raw["reason"]).strip()),
            original_filename=(
                str(raw["original_filename"]).strip()
                if raw.get("original_filename") not in (None, "")
                else None
            ),
        )


@dataclass(frozen=True)
class ExecutionImageManifest:
    """Immutable canonical manifest for one photo execution."""

    job_id: str
    entries: tuple[ExecutionImageEntry, ...]
    excluded_entries: tuple[ExcludedExecutionImage, ...]
    version: int = MANIFEST_VERSION

    def ordered_entries(self) -> tuple[ExecutionImageEntry, ...]:
        return tuple(sorted(self.entries, key=lambda e: e.payload_ordinal))

    def primary_entries(self) -> tuple[ExecutionImageEntry, ...]:
        return tuple(e for e in self.ordered_entries() if e.role == ExecutionImageRole.PRIMARY_EVIDENCE)

    def reference_entries(self) -> tuple[ExecutionImageEntry, ...]:
        return tuple(e for e in self.ordered_entries() if e.role == ExecutionImageRole.REFERENCE_IMAGE)

    def primary_source_image_ids(self) -> tuple[str, ...]:
        return tuple(e.source_image_id for e in self.primary_entries())

    def reference_source_image_ids(self) -> tuple[str, ...]:
        return tuple(e.source_image_id for e in self.reference_entries())

    def primary_manifest_entry_ids(self) -> tuple[str, ...]:
        return tuple(e.manifest_entry_id for e in self.primary_entries())

    def excluded_source_image_ids(self) -> frozenset[str]:
        return frozenset(e.source_image_id for e in self.excluded_entries)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "version": self.version,
            "entries": [e.to_dict() for e in self.ordered_entries()],
            "excluded_entries": [e.to_dict() for e in self.excluded_entries],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ExecutionImageManifest:
        if not isinstance(raw, dict):
            raise ExecutionImageManifestError("execution_image_manifest must be a dict")
        version_raw = raw.get("version")
        if version_raw is None:
            raise ExecutionImageManifestError("execution_image_manifest version is required")
        version = int(version_raw)
        if version < 1 or version > MANIFEST_VERSION:
            raise ExecutionImageManifestError(
                f"unsupported execution_image_manifest version: {version} (max={MANIFEST_VERSION})"
            )
        entries_raw = raw.get("entries")
        if not isinstance(entries_raw, list):
            raise ExecutionImageManifestError("execution_image_manifest entries must be a list")
        excluded_raw = raw.get("excluded_entries")
        if excluded_raw is not None and not isinstance(excluded_raw, list):
            raise ExecutionImageManifestError("execution_image_manifest excluded_entries must be a list")
        manifest = cls(
            job_id=str(raw.get("job_id") or "").strip(),
            entries=tuple(
                ExecutionImageEntry.from_dict(e) for e in entries_raw if isinstance(e, dict)
            ),
            excluded_entries=tuple(
                ExcludedExecutionImage.from_dict(e)
                for e in (excluded_raw or [])
                if isinstance(e, dict)
            ),
            version=version,
        )
        validate_execution_image_manifest(manifest)
        return manifest


def validate_execution_image_manifest(manifest: ExecutionImageManifest) -> None:
    """Validate manifest invariants; raise ``ExecutionImageManifestError`` on failure."""
    if not manifest.job_id:
        raise ExecutionImageManifestError("manifest job_id is required")

    if not manifest.entries:
        raise ExecutionImageManifestError("manifest must contain at least one active entry")

    primary = manifest.primary_entries()
    if not primary:
        raise ExecutionImageManifestError(
            "manifest must contain at least one PRIMARY_EVIDENCE entry"
        )

    ordered = manifest.ordered_entries()
    entry_ids: set[str] = set()
    source_ids: set[str] = set()
    ordinals: list[int] = []
    blocking_excluded_ids = frozenset(
        e.source_image_id
        for e in manifest.excluded_entries
        if e.reason != ImageExclusionReason.DUPLICATE
    )

    for entry in ordered:
        if not entry.manifest_entry_id:
            raise ExecutionImageManifestError("manifest_entry_id is required")
        if entry.manifest_entry_id in entry_ids:
            raise ExecutionImageManifestError(
                f"duplicate manifest_entry_id: {entry.manifest_entry_id}"
            )
        entry_ids.add(entry.manifest_entry_id)

        if not entry.source_image_id:
            raise ExecutionImageManifestError("source_image_id is required for active entries")
        if not entry.source_asset_id:
            raise ExecutionImageManifestError("source_asset_id is required for active entries")
        if entry.source_image_id in source_ids:
            raise ExecutionImageManifestError(
                f"duplicate active source_image_id: {entry.source_image_id}"
            )
        source_ids.add(entry.source_image_id)

        if entry.source_image_id in blocking_excluded_ids:
            raise ExecutionImageManifestError(
                f"excluded source_image_id appears in active entries: {entry.source_image_id}"
            )

        ordinals.append(entry.payload_ordinal)

        if entry.role == ExecutionImageRole.PRIMARY_EVIDENCE:
            if entry.manifest_entry_id.upper().startswith("REF_"):
                raise ExecutionImageManifestError(
                    f"primary entry cannot use reference manifest_entry_id: {entry.manifest_entry_id}"
                )
        elif entry.role == ExecutionImageRole.REFERENCE_IMAGE:
            if entry.manifest_entry_id.upper().startswith("IMG_"):
                raise ExecutionImageManifestError(
                    f"reference entry cannot use primary manifest_entry_id: {entry.manifest_entry_id}"
                )

    if len(set(ordinals)) != len(ordinals):
        raise ExecutionImageManifestError("duplicate payload_ordinal in manifest entries")

    expected = list(range(1, len(ordered) + 1))
    if sorted(ordinals) != expected:
        raise ExecutionImageManifestError(
            f"payload_ordinal must be contiguous 1..{len(ordered)}; got {sorted(ordinals)}"
        )

    for i, entry in enumerate(ordered):
        if entry.payload_ordinal != i + 1:
            raise ExecutionImageManifestError("entry order must match payload_ordinal")


def manifest_composition_projection(manifest: ExecutionImageManifest) -> dict[str, Any]:
    """Derived compatibility fields for prompt composition and traceability."""
    primary_ids = list(manifest.primary_source_image_ids())
    ref_ids = list(manifest.reference_source_image_ids())
    prompt_listed = list(manifest.primary_manifest_entry_ids()) + list(
        e.manifest_entry_id for e in manifest.reference_entries()
    )
    return {
        COMPOSITION_KEY_EXECUTION_IMAGE_MANIFEST: manifest.to_dict(),
        "frames_sent_ids": primary_ids,
        "prompt_listed_image_ids": prompt_listed,
        "reference_image_ids": ref_ids,
        "manifest_entry_ids_ordered": [e.manifest_entry_id for e in manifest.ordered_entries()],
    }


def composition_has_execution_image_manifest(composition: dict[str, Any] | None) -> bool:
    """True when composition carries a serialized manifest (valid or corrupt)."""
    if not composition:
        return False
    return COMPOSITION_KEY_EXECUTION_IMAGE_MANIFEST in composition


def extract_manifest_from_composition(
    composition: dict[str, Any] | None,
) -> ExecutionImageManifest | None:
    """Parse manifest when present and valid; None when key absent."""
    if not composition:
        return None
    raw = composition.get(COMPOSITION_KEY_EXECUTION_IMAGE_MANIFEST)
    if raw is None:
        return None
    return ExecutionImageManifest.from_dict(raw)


def require_manifest_from_composition(
    composition: dict[str, Any] | None,
) -> ExecutionImageManifest | None:
    """
    Parse manifest when key is present; raise on corrupt serialized manifest.

    Returns None only when the manifest key is absent (legacy compositions).
    """
    if not composition:
        return None
    raw = composition.get(COMPOSITION_KEY_EXECUTION_IMAGE_MANIFEST)
    if raw is None:
        return None
    return ExecutionImageManifest.from_dict(raw)
