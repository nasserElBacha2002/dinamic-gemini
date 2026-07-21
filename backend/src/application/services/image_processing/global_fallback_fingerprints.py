"""Fingerprints for GLOBAL_BATCH idempotency (config, prompt, content identity)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any


def canonical_json_sha256(payload: Any) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def configuration_fingerprint_from_snapshot(identification_execution: Mapping[str, Any] | None) -> str:
    """SHA-256 of the immutable identification_execution snapshot (not version alone)."""
    if not isinstance(identification_execution, dict):
        raise ValueError("CONFIGURATION_FINGERPRINT_REQUIRED: identification_execution missing")
    return canonical_json_sha256(identification_execution)


def prompt_fingerprint_from_parts(
    *,
    prompt_key: str,
    schema_version: str,
    composition_version: str | None,
    base_prompt_sha256: str | None,
    supplier_content_sha256: str | None,
    client_rules: Mapping[str, Any] | None,
    effective_prompt_text: str | None = None,
) -> str:
    """Prefer hash of effective prompt text when available; else compose identity parts."""
    if effective_prompt_text and effective_prompt_text.strip():
        return hashlib.sha256(effective_prompt_text.encode("utf-8")).hexdigest()
    return canonical_json_sha256(
        {
            "prompt_key": prompt_key,
            "schema_version": schema_version,
            "composition_version": composition_version or "",
            "base_prompt_sha256": base_prompt_sha256 or "",
            "supplier_content_sha256": supplier_content_sha256 or "",
            "client_rules": client_rules or {},
        }
    )


def asset_content_identity_hash(
    *,
    asset_id: str,
    storage_key: str | None,
    etag: str | None,
    file_size_bytes: int | None,
    mime_type: str | None,
) -> str:
    """Stable content identity before bytes are prepared (etag/size/key)."""
    return canonical_json_sha256(
        {
            "asset_id": asset_id,
            "storage_key": storage_key or "",
            "etag": etag or "",
            "file_size_bytes": file_size_bytes,
            "mime_type": mime_type or "",
        }
    )


def prepared_hashes_for_ordered_assets(
    ordered_asset_ids: Sequence[str],
    hashes_by_asset: Mapping[str, str],
) -> list[str]:
    missing = [aid for aid in ordered_asset_ids if not hashes_by_asset.get(aid)]
    if missing:
        raise ValueError(
            f"PREPARED_IMAGE_HASHES_REQUIRED: missing hashes for assets {missing[:5]}"
        )
    return [hashes_by_asset[aid] for aid in ordered_asset_ids]
