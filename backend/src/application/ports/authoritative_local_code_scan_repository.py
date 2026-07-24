"""Port for authoritative local CODE_SCAN results."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from src.domain.authoritative_local_code_scan.entities import AuthoritativeLocalCodeScanResult


class AuthoritativeUniqueViolationError(Exception):
    def __init__(self, constraint: str = "unique") -> None:
        super().__init__(constraint)
        self.constraint = constraint


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

    def insert(self, row: AuthoritativeLocalCodeScanResult) -> AuthoritativeLocalCodeScanResult: ...

    def mark_superseded(
        self, *, result_id: str, expected_row_version: int, updated_at
    ) -> AuthoritativeLocalCodeScanResult | None: ...

    def mark_applied(
        self,
        *,
        result_id: str,
        job_id: str,
        applied_at,
        expected_row_version: int,
    ) -> AuthoritativeLocalCodeScanResult | None: ...
