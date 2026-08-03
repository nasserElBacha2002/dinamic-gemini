"""Shared helpers for logical capture order (Phase 1 positioning foundation)."""

from __future__ import annotations

from collections.abc import Sequence

from src.domain.assets.entities import SourceAsset


def sort_assets_by_logical_sequence(assets: Sequence[SourceAsset]) -> list[SourceAsset]:
    """Order assets for processing / traversal.

    CLIENT_ASSIGNED rows with ``sequence_number`` sort first by
    ``(sequence_number, upload_client_file_id)``.
    Legacy rows (no sequence) follow, ordered by ``uploaded_at`` then id — explicitly
    non-authoritative for new capture sessions.
    """
    sequenced: list[SourceAsset] = []
    legacy: list[SourceAsset] = []
    for asset in assets:
        if asset.sequence_number is not None:
            sequenced.append(asset)
        else:
            legacy.append(asset)
    sequenced.sort(
        key=lambda a: (
            int(a.sequence_number or 0),
            (a.upload_client_file_id or ""),
            a.id,
        )
    )
    legacy.sort(key=lambda a: (a.uploaded_at, a.id))
    return sequenced + legacy


def position_order_for_asset(asset: SourceAsset, *, fallback_index: int) -> int:
    """Derive ``position_order`` from sequence when present (alias, not a second SoT).

    For CLIENT_ASSIGNED assets, ``position_order == sequence_number`` (1-based).
    Legacy assets keep 0-based enumerate index.
    """
    if asset.sequence_number is not None:
        return int(asset.sequence_number)
    return int(fallback_index)


def validate_complete_sequence(
    assets: Sequence[SourceAsset],
    *,
    expected_count: int,
) -> list[str]:
    """Return human-readable validation errors; empty list means OK."""
    errors: list[str] = []
    if expected_count < 1:
        errors.append("expected_asset_count must be >= 1")
        return errors
    sequenced = [a for a in assets if a.sequence_number is not None]
    if len(sequenced) != expected_count:
        errors.append(
            f"persisted sequenced asset count {len(sequenced)} != expected {expected_count}"
        )
    numbers = [int(a.sequence_number or 0) for a in sequenced]
    if numbers:
        if min(numbers) != 1:
            errors.append(f"min(sequence_number)={min(numbers)} expected 1")
        if max(numbers) != expected_count:
            errors.append(
                f"max(sequence_number)={max(numbers)} expected {expected_count}"
            )
        if len(set(numbers)) != len(numbers):
            errors.append("duplicate sequence_number values present")
        if len(set(numbers)) != expected_count:
            errors.append(
                f"distinct sequence_number count {len(set(numbers))} != {expected_count}"
            )
    missing_client = [a.id for a in sequenced if not (a.upload_client_file_id or "").strip()]
    if missing_client:
        errors.append(f"{len(missing_client)} assets missing client_image_id")
    return errors
