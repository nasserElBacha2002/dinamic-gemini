"""Domain errors for local CSV import."""

from __future__ import annotations

LOCAL_CSV_IMPORT_DISABLED = "LOCAL_CSV_IMPORT_DISABLED"
LOCAL_CSV_IMPORT_NOT_FOUND = "LOCAL_CSV_IMPORT_NOT_FOUND"
LOCAL_CSV_EXPORT_NOT_PREVIEWED = "LOCAL_CSV_EXPORT_NOT_PREVIEWED"
LOCAL_CSV_EXPORT_CONFLICT = "LOCAL_CSV_EXPORT_CONFLICT"
LOCAL_CSV_INVENTORY_MISMATCH = "LOCAL_CSV_INVENTORY_MISMATCH"
LOCAL_CSV_SECONDARY_CONFLICT = "LOCAL_CSV_SECONDARY_CONFLICT"
CONFLICT_POLICIES = frozenset({"SKIP", "REJECT"})


class LocalCsvImportError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code


class LocalCsvImportDisabledError(LocalCsvImportError):
    def __init__(self) -> None:
        super().__init__(LOCAL_CSV_IMPORT_DISABLED, "Local CSV import is not enabled")
