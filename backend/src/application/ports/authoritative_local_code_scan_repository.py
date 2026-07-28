"""Port for authoritative local CODE_SCAN results."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from src.domain.authoritative_local_code_scan.entities import AuthoritativeLocalCodeScanResult


class AuthoritativeUniqueViolationError(Exception):
    def __init__(self, constraint: str = "unique") -> None:
        super().__init__(constraint)
        self.constraint = constraint


class AuthoritativeVersionConflictError(Exception):
    """CAS / concurrent versioning conflict during create_authoritative_version."""


class AuthoritativeLocalCodeScanRepository(Protocol):
    def get_by_id(self, result_id: str) -> AuthoritativeLocalCodeScanResult | None: ...

    def get_current_for_asset(
        self, asset_id: str
    ) -> AuthoritativeLocalCodeScanResult | None: ...

    def list_current_for_aisle(
        self, *, inventory_id: str, aisle_id: str
    ) -> Sequence[AuthoritativeLocalCodeScanResult]: ...

    def list_current_for_asset_ids(
        self, *, asset_ids: Sequence[str]
    ) -> Sequence[AuthoritativeLocalCodeScanResult]: ...

    def max_version_for_asset(self, asset_id: str) -> int: ...

    def create_authoritative_version(
        self,
        *,
        new_result: AuthoritativeLocalCodeScanResult,
        expected_current_id: str | None,
        expected_row_version: int | None,
    ) -> AuthoritativeLocalCodeScanResult:
        """Atomically supersede current (if any) and insert new current.

        On conflict / CAS failure: raise AuthoritativeVersionConflictError;
        previous current must remain current (full rollback).
        """
        ...

    def mark_applied_if_version(
        self,
        *,
        result_id: str,
        job_id: str,
        applied_at: datetime,
        expected_row_version: int,
    ) -> AuthoritativeLocalCodeScanResult | None:
        """CAS mark applied. Returns updated row or None on version mismatch."""
        ...
