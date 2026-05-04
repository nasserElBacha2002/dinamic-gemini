"""
Phase 6: consistent mapping from SQL columns to domain storage fields.

``storage_path`` remains the legacy relative path under ``v3_uploads`` (and similar layouts).
``storage_key`` is the canonical logical object key for ArtifactStore (must not duplicate
the configured S3 bucket prefix; see ``artifact_store`` module docstring).
"""

from __future__ import annotations


def resolved_storage_key_for_row(
    *,
    storage_provider: str | None,
    storage_key_raw: str | None,
    storage_path: str,
) -> str | None:
    """Resolve ``storage_key`` for domain entities loaded from SQL.

    When ``storage_provider`` is set, only ``storage_key_raw`` is used. ``storage_path`` must
    never fill in a missing key: incomplete provider metadata must surface as an empty key,
    not a silent legacy path (which would mask broken migrations).

    When no provider is set (legacy rows), an explicit ``storage_key`` column still wins;
    otherwise ``storage_path`` is used as the local filesystem key.
    """
    prov = (storage_provider or "").strip()
    key = (storage_key_raw or "").strip()
    path = (storage_path or "").strip()
    if prov:
        return key or None
    if key:
        return key
    return path or None
