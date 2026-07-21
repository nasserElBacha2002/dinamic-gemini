"""Deterministic batching + fingerprint for GLOBAL_BATCH external fallback."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class GlobalFallbackBatchSlice:
    """One deterministic batch of ordered assets (max size = hybrid frame cap)."""

    batch_index: int
    batch_count: int
    ordered_asset_ids: tuple[str, ...]
    fingerprint: str


@dataclass(frozen=True)
class AssetOrderKey:
    asset_id: str
    sequence: int | None = None
    uploaded_at: datetime | None = None


def stable_ordered_asset_ids(
    asset_ids: Sequence[str],
    *,
    order_keys: Sequence[AssetOrderKey] | None = None,
) -> tuple[str, ...]:
    """Stable domain order: capture/upload sequence, then uploaded_at, then asset_id.

    Lexicographic UUID sort is only the last-resort tie-break when no keys provided.
    """
    if order_keys:
        by_id = {k.asset_id: k for k in order_keys if k.asset_id}
        ids = [str(a).strip() for a in asset_ids if str(a).strip()]

        def sort_key(aid: str) -> tuple[Any, ...]:
            k = by_id.get(aid)
            if k is None:
                return (10**12, datetime.max.replace(tzinfo=None), aid)
            seq = k.sequence if k.sequence is not None else 10**12
            ts = k.uploaded_at or datetime.max.replace(tzinfo=None)
            # naive/aware mix: use timestamp ordinal when possible
            try:
                ts_key = ts.timestamp()
            except Exception:
                ts_key = 0.0
            return (seq, ts_key, aid)

        return tuple(sorted(ids, key=sort_key))
    return tuple(sorted(str(a).strip() for a in asset_ids if str(a).strip()))


def chunk_asset_ids(
    ordered_asset_ids: Sequence[str],
    *,
    max_per_batch: int,
) -> list[tuple[str, ...]]:
    """Split into batches of at most ``max_per_batch``. Never creates empty batches."""
    if max_per_batch < 1:
        raise ValueError("max_per_batch must be >= 1")
    ids = [str(a).strip() for a in ordered_asset_ids if str(a).strip()]
    if not ids:
        return []
    return [
        tuple(ids[i : i + max_per_batch]) for i in range(0, len(ids), max_per_batch)
    ]


def compute_batch_fingerprint(
    *,
    job_id: str,
    execution_id: str | None,
    attempt: int,
    fallback_mode: str,
    provider: str,
    model: str | None,
    schema_version: str,
    configuration_fingerprint: str,
    prompt_fingerprint: str,
    batch_index: int,
    ordered_asset_ids: Sequence[str],
    prepared_image_hashes: Sequence[str] | None = None,
) -> str:
    """Stable SHA-256 hex fingerprint for batch idempotency."""
    hashes = list(prepared_image_hashes or [])
    if not hashes or any(not h for h in hashes):
        raise ValueError(
            "PREPARED_IMAGE_HASHES_REQUIRED: fingerprint must include non-empty prepared hashes"
        )
    if not configuration_fingerprint:
        raise ValueError("CONFIGURATION_FINGERPRINT_REQUIRED")
    if not prompt_fingerprint:
        raise ValueError("PROMPT_FINGERPRINT_REQUIRED")
    payload = {
        "job_id": str(job_id),
        "execution_id": str(execution_id or job_id),
        "attempt": int(attempt),
        "fallback_mode": str(fallback_mode),
        "provider": str(provider or "").strip().lower(),
        "model": str(model or "").strip(),
        "schema_version": str(schema_version),
        "configuration_fingerprint": str(configuration_fingerprint),
        "prompt_fingerprint": str(prompt_fingerprint),
        "batch_index": int(batch_index),
        "ordered_asset_ids": list(ordered_asset_ids),
        "prepared_image_hashes": hashes,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_batch_slices(
    asset_ids: Sequence[str],
    *,
    max_per_batch: int,
    job_id: str,
    execution_id: str | None,
    attempt: int,
    fallback_mode: str,
    provider: str,
    model: str | None,
    schema_version: str,
    configuration_fingerprint: str,
    prompt_fingerprint: str,
    prepared_image_hashes_by_asset: dict[str, str],
    order_keys: Sequence[AssetOrderKey] | None = None,
) -> list[GlobalFallbackBatchSlice]:
    """Build ordered batch slices with fingerprints (prepared hashes required)."""
    ordered = stable_ordered_asset_ids(asset_ids, order_keys=order_keys)
    chunks = chunk_asset_ids(ordered, max_per_batch=max_per_batch)
    batch_count = len(chunks)
    slices: list[GlobalFallbackBatchSlice] = []
    for idx, chunk in enumerate(chunks):
        prep_hashes = tuple(prepared_image_hashes_by_asset[aid] for aid in chunk)
        fp = compute_batch_fingerprint(
            job_id=job_id,
            execution_id=execution_id,
            attempt=attempt,
            fallback_mode=fallback_mode,
            provider=provider,
            model=model,
            schema_version=schema_version,
            configuration_fingerprint=configuration_fingerprint,
            prompt_fingerprint=prompt_fingerprint,
            batch_index=idx,
            ordered_asset_ids=chunk,
            prepared_image_hashes=prep_hashes,
        )
        slices.append(
            GlobalFallbackBatchSlice(
                batch_index=idx,
                batch_count=batch_count,
                ordered_asset_ids=chunk,
                fingerprint=fp,
            )
        )
    return slices
