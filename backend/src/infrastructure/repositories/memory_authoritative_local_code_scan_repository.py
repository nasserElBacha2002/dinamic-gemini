"""In-memory authoritative local CODE_SCAN repository (unit tests)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from src.application.ports.authoritative_local_code_scan_repository import (
    AuthoritativeUniqueViolationError,
)
from src.domain.authoritative_local_code_scan.entities import AuthoritativeLocalCodeScanResult


class MemoryAuthoritativeLocalCodeScanRepository:
    def __init__(self) -> None:
        self._by_id: dict[str, AuthoritativeLocalCodeScanResult] = {}

    def get_by_id(self, result_id: str) -> AuthoritativeLocalCodeScanResult | None:
        return self._by_id.get((result_id or "").strip())

    def get_current_for_asset(self, asset_id: str) -> AuthoritativeLocalCodeScanResult | None:
        aid = (asset_id or "").strip()
        currents = [r for r in self._by_id.values() if r.asset_id == aid and r.is_current]
        if not currents:
            return None
        currents.sort(key=lambda r: r.result_version, reverse=True)
        return currents[0]

    def list_current_for_aisle(
        self, *, inventory_id: str, aisle_id: str
    ) -> Sequence[AuthoritativeLocalCodeScanResult]:
        rows = [
            r
            for r in self._by_id.values()
            if r.inventory_id == inventory_id and r.aisle_id == aisle_id and r.is_current
        ]
        rows.sort(key=lambda r: (r.asset_id, r.result_version))
        return rows

    def list_current_for_asset_ids(
        self, *, asset_ids: Sequence[str]
    ) -> Sequence[AuthoritativeLocalCodeScanResult]:
        wanted = {a.strip() for a in asset_ids if a and a.strip()}
        if not wanted:
            return []
        rows = [
            r for r in self._by_id.values() if r.asset_id in wanted and r.is_current
        ]
        rows.sort(key=lambda r: r.asset_id)
        return rows

    def max_version_for_asset(self, asset_id: str) -> int:
        aid = (asset_id or "").strip()
        versions = [r.result_version for r in self._by_id.values() if r.asset_id == aid]
        return max(versions) if versions else 0

    def insert(self, row: AuthoritativeLocalCodeScanResult) -> AuthoritativeLocalCodeScanResult:
        if row.id in self._by_id:
            raise AuthoritativeUniqueViolationError("id")
        for existing in self._by_id.values():
            if existing.asset_id == row.asset_id and existing.result_version == row.result_version:
                raise AuthoritativeUniqueViolationError("asset_version")
            if row.is_current and existing.asset_id == row.asset_id and existing.is_current:
                raise AuthoritativeUniqueViolationError("asset_current")
        self._by_id[row.id] = row
        return row

    def mark_superseded(
        self, *, result_id: str, expected_row_version: int, updated_at: datetime
    ) -> AuthoritativeLocalCodeScanResult | None:
        row = self._by_id.get(result_id)
        if row is None or int(row.row_version) != int(expected_row_version):
            return None
        updated = AuthoritativeLocalCodeScanResult(
            **{
                **row.__dict__,
                "is_current": False,
                "row_version": int(row.row_version) + 1,
                "updated_at": updated_at,
            }
        )
        self._by_id[result_id] = updated
        return updated

    def mark_applied(
        self,
        *,
        result_id: str,
        job_id: str,
        applied_at: datetime,
        expected_row_version: int,
    ) -> AuthoritativeLocalCodeScanResult | None:
        row = self._by_id.get(result_id)
        if row is None or int(row.row_version) != int(expected_row_version):
            return None
        updated = AuthoritativeLocalCodeScanResult(
            **{
                **row.__dict__,
                "applied_job_id": job_id,
                "applied_at": applied_at,
                "row_version": int(row.row_version) + 1,
                "updated_at": applied_at,
            }
        )
        self._by_id[result_id] = updated
        return updated
