"""Deterministic batching + fingerprint for GLOBAL_BATCH external fallback."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class GlobalFallbackBatchSlice:
    """One deterministic batch of ordered assets (max size = hybrid frame cap)."""

    batch_index: int
    batch_count: int
    ordered_asset_ids: tuple[str, ...]
    fingerprint: str


def stable_ordered_asset_ids(asset_ids: Sequence[str]) -> tuple[str, ...]:
    """Stable order: lexicographic by asset id (deterministic across workers)."""
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
    payload = {
        "job_id": str(job_id),
        "execution_id": str(execution_id or job_id),
        "attempt": int(attempt),
        "fallback_mode": str(fallback_mode),
        "provider": str(provider or "").strip().lower(),
        "model": str(model or "").strip(),
        "schema_version": str(schema_version),
        "configuration_fingerprint": str(configuration_fingerprint or ""),
        "prompt_fingerprint": str(prompt_fingerprint or ""),
        "batch_index": int(batch_index),
        "ordered_asset_ids": list(ordered_asset_ids),
        "prepared_image_hashes": list(prepared_image_hashes or []),
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
    prepared_image_hashes_by_asset: dict[str, str] | None = None,
) -> list[GlobalFallbackBatchSlice]:
    """Build ordered batch slices with fingerprints."""
    ordered = stable_ordered_asset_ids(asset_ids)
    chunks = chunk_asset_ids(ordered, max_per_batch=max_per_batch)
    batch_count = len(chunks)
    hashes = prepared_image_hashes_by_asset or {}
    slices: list[GlobalFallbackBatchSlice] = []
    for idx, chunk in enumerate(chunks):
        prep_hashes = tuple(hashes.get(aid, "") for aid in chunk)
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
