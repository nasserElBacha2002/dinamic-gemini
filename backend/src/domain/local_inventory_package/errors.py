"""Errors for local inventory ZIP package import."""

from __future__ import annotations

PACKAGE_IMPORT_DISABLED = "LOCAL_INVENTORY_PACKAGE_DISABLED"
PACKAGE_NOT_FOUND = "LOCAL_INVENTORY_PACKAGE_NOT_FOUND"
PACKAGE_EXPORT_CONFLICT = "LOCAL_INVENTORY_PACKAGE_EXPORT_CONFLICT"
PACKAGE_INVENTORY_MISMATCH = "LOCAL_INVENTORY_PACKAGE_INVENTORY_MISMATCH"
PACKAGE_UNRESOLVED_ROWS = "PACKAGE_UNRESOLVED_ROWS"
PACKAGE_NO_PRODUCTIVE_ROWS = "PACKAGE_NO_PRODUCTIVE_ROWS"


class LocalInventoryPackageImportError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class LocalInventoryPackageDisabledError(LocalInventoryPackageImportError):
    def __init__(self) -> None:
        super().__init__(
            PACKAGE_IMPORT_DISABLED,
            "Local inventory package import is not enabled",
        )
