"""Port for staging local inventory ZIP packages between preview and confirm."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from src.domain.local_csv_import.entities import (
    LocalCsvImport,
    LocalCsvImportRow,
    LocalCsvProductiveResult,
)
from src.domain.local_inventory_package.entities import LocalInventoryPackage


class LocalInventoryPackageRepository(Protocol):
    def get_by_id(self, package_id: str) -> LocalInventoryPackage | None: ...

    def get_by_export_id(
        self, *, inventory_id: str, export_id: str
    ) -> LocalInventoryPackage | None: ...

    def stage_or_get_existing(self, record: LocalInventoryPackage) -> LocalInventoryPackage: ...

    def confirm_package_atomically(
        self,
        *,
        inventory_id: str,
        export_id: str,
        conflict_policy: str,
        confirmed_by_user_id: str | None,
        apply_productive: Callable[
            [LocalCsvImport, tuple[LocalCsvImportRow, ...], str | None, LocalInventoryPackage],
            tuple[LocalCsvProductiveResult, ...],
        ],
        clock_now: Callable[[], datetime],
    ) -> tuple[LocalInventoryPackage, bool]: ...
