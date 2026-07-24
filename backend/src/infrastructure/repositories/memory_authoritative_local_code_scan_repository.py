"""In-memory authoritative local CODE_SCAN repository (unit tests)."""

from __future__ import annotations

import threading
from collections.abc import Sequence
from datetime import datetime

from src.application.ports.authoritative_local_code_scan_repository import (
    AuthoritativeUniqueViolationError,
    AuthoritativeVersionConflictError,
)
from src.domain.authoritative_local_code_scan.entities import AuthoritativeLocalCodeScanResult


class MemoryAuthoritativeLocalCodeScanRepository:
    def __init__(self) -> None:
        self._by_id: dict[str, AuthoritativeLocalCodeScanResult] = {}
        self._lock = threading.Lock()

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
        rows = [r for r in self._by_id.values() if r.asset_id in wanted and r.is_current]
        rows.sort(key=lambda r: r.asset_id)
        return rows

    def max_version_for_asset(self, asset_id: str) -> int:
        aid = (asset_id or "").strip()
        versions = [r.result_version for r in self._by_id.values() if r.asset_id == aid]
        return max(versions) if versions else 0

    def create_authoritative_version(
        self,
        *,
        new_result: AuthoritativeLocalCodeScanResult,
        expected_current_id: str | None,
        expected_row_version: int | None,
    ) -> AuthoritativeLocalCodeScanResult:
        with self._lock:
            if new_result.id in self._by_id:
                raise AuthoritativeUniqueViolationError("id")

            current = self.get_current_for_asset(new_result.asset_id)
            if expected_current_id is None:
                if current is not None:
                    raise AuthoritativeVersionConflictError("expected_no_current")
            else:
                if current is None or current.id != expected_current_id:
                    raise AuthoritativeVersionConflictError("current_mismatch")
                if expected_row_version is None or int(current.row_version) != int(
                    expected_row_version
                ):
                    raise AuthoritativeVersionConflictError("row_version_mismatch")
                # Supersede current inside the same lock (atomic w.r.t. other writers).
                superseded = AuthoritativeLocalCodeScanResult(
                    **{
                        **current.__dict__,
                        "is_current": False,
                        "row_version": int(current.row_version) + 1,
                        "updated_at": new_result.updated_at,
                    }
                )
                self._by_id[current.id] = superseded

            next_version = self.max_version_for_asset(new_result.asset_id) + 1
            if new_result.supersedes_result_id != (expected_current_id):
                # Force consistency with lock-time current.
                pass
            row = AuthoritativeLocalCodeScanResult(
                **{
                    **new_result.__dict__,
                    "result_version": next_version,
                    "supersedes_result_id": expected_current_id,
                    "is_current": True,
                }
            )
            for existing in self._by_id.values():
                if existing.asset_id == row.asset_id and existing.result_version == row.result_version:
                    raise AuthoritativeUniqueViolationError("asset_version")
                if row.is_current and existing.asset_id == row.asset_id and existing.is_current:
                    raise AuthoritativeUniqueViolationError("asset_current")
            self._by_id[row.id] = row
            return row

    def mark_applied_if_version(
        self,
        *,
        result_id: str,
        job_id: str,
        applied_at: datetime,
        expected_row_version: int,
    ) -> AuthoritativeLocalCodeScanResult | None:
        with self._lock:
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
