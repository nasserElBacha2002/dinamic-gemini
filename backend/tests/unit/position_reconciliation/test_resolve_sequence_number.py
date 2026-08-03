"""Unit tests for sequence resolution used when building OrderedImageFrame."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.application.ports.job_source_asset_repository import JobSourceAssetLink
from src.application.use_cases.position_reconciliation.reconcile_job_positions import (
    ReconcileJobPositionsUseCase,
)


@dataclass
class _Asset:
    sequence_number: int | None = None


def _link(*, sequence_number: int | None = None, position_order: int = 0) -> JobSourceAssetLink:
    return JobSourceAssetLink(
        id="link-1",
        job_id="job-1",
        source_asset_id="asset-1",
        asset_role="primary",
        position_order=position_order,
        checksum=None,
        storage_key=None,
        mime_type=None,
        size_bytes=None,
        width=None,
        height=None,
        stage=None,
        provider_request_id=None,
        created_at=datetime.now(timezone.utc),
        sequence_number=sequence_number,
    )


def test_prefers_asset_sequence_number():
    assert (
        ReconcileJobPositionsUseCase._resolve_sequence_number(
            asset=_Asset(sequence_number=7),
            link=_link(sequence_number=3, position_order=1),
        )
        == 7
    )


def test_falls_back_to_link_sequence_number():
    assert (
        ReconcileJobPositionsUseCase._resolve_sequence_number(
            asset=_Asset(sequence_number=None),
            link=_link(sequence_number=4, position_order=1),
        )
        == 4
    )


def test_falls_back_to_position_order_for_system_uploads():
    assert (
        ReconcileJobPositionsUseCase._resolve_sequence_number(
            asset=_Asset(sequence_number=None),
            link=_link(sequence_number=None, position_order=0),
        )
        == 0
    )
    assert (
        ReconcileJobPositionsUseCase._resolve_sequence_number(
            asset=None,
            link=_link(sequence_number=None, position_order=5),
        )
        == 5
    )
