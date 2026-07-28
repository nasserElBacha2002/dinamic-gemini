"""Fail-closed AuthoritativeSessionReadiness (no hybrid remote fallback)."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.services.authoritative_session_readiness import AuthoritativeSessionReadiness
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.authoritative_local_code_scan.entities import AuthoritativeLocalCodeScanResult
from src.infrastructure.repositories.memory_authoritative_local_code_scan_repository import (
    MemoryAuthoritativeLocalCodeScanRepository,
)


class _Assets:
    def __init__(self, assets: list[SourceAsset]) -> None:
        self._assets = assets

    def list_by_aisle(self, aisle_id: str):
        return [a for a in self._assets if a.aisle_id == aisle_id]


def _asset(aid: str) -> SourceAsset:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return SourceAsset(
        id=aid,
        aisle_id="a1",
        type=SourceAssetType.PHOTO,
        original_filename=f"{aid}.jpg",
        storage_path=f"/tmp/{aid}.jpg",
        mime_type="image/jpeg",
        uploaded_at=now,
    )


def _row(rid: str, asset_id: str) -> AuthoritativeLocalCodeScanResult:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return AuthoritativeLocalCodeScanResult(
        id=rid,
        asset_id=asset_id,
        inventory_id="i1",
        aisle_id="a1",
        client_file_id=f"cf-{asset_id}",
        result_version=1,
        supersedes_result_id=None,
        is_current=True,
        internal_code="SKU",
        quantity=1,
        quantity_status="PRESENT",
        source="LOCAL_CODE_SCAN",
        detected_internal_code="SKU",
        detected_quantity=1,
        detected_symbology="EAN_13",
        parser_version="1",
        detector_version="1",
        prepared_asset_sha256="sha",
        content_hash=f"h-{rid}",
        confirmed_by="u1",
        client_confirmed_at=now,
        server_confirmed_at=now,
        server_received_at=now,
        confirmed_at=now,
        applied_job_id=None,
        applied_at=None,
        row_version=1,
        schema_version="1",
        created_at=now,
        updated_at=now,
    )


def test_session_readiness_blocks_missing_confirms():
    auth = MemoryAuthoritativeLocalCodeScanRepository()
    auth.create_authoritative_version(
        new_result=_row("r1", "p1"),
        expected_current_id=None,
        expected_row_version=None,
    )
    svc = AuthoritativeSessionReadiness(
        asset_repo=_Assets([_asset("p1"), _asset("p2")]),
        authoritative_repo=auth,
        enabled=True,
    )
    result = svc.evaluate(inventory_id="i1", aisle_id="a1")
    assert result.ready is False
    assert result.can_apply is False
    assert "PENDING_CONFIRMATION" in result.reasons
    assert result.missing_asset_ids == ("p2",)


def test_session_readiness_ready_when_all_confirmed():
    auth = MemoryAuthoritativeLocalCodeScanRepository()
    for aid in ("p1", "p2"):
        auth.create_authoritative_version(
            new_result=_row(f"r-{aid}", aid),
            expected_current_id=None,
            expected_row_version=None,
        )
    svc = AuthoritativeSessionReadiness(
        asset_repo=_Assets([_asset("p1"), _asset("p2")]),
        authoritative_repo=auth,
        enabled=True,
    )
    result = svc.evaluate(inventory_id="i1", aisle_id="a1")
    assert result.ready is True
    assert result.can_apply is True
    assert result.can_finalize is False
