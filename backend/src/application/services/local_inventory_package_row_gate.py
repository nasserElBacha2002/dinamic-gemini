"""Fail-closed gate: ZIP packages must include resolved inventory product rows."""

from __future__ import annotations

from collections.abc import Iterable

from src.domain.local_csv_import.entities import LocalCsvImportRow
from src.domain.local_inventory_package.errors import LocalInventoryPackageImportError

_POSITION_MARKER_SOURCES = frozenset({"LOCAL_POSITION_LABEL"})
_UNRESOLVED_SOURCES = frozenset({"LOCAL_PENDING"})


def assert_package_csv_rows_ready(rows: Iterable[LocalCsvImportRow]) -> None:
    """Reject packages that would stage photos with zero usable inventory results.

    Mirrors mobile ``assertLocalCsvRowsExportReady``:
    - no ``LOCAL_PENDING`` rows among accepted rows
    - at least one non-label row with ``internal_code``
    - packages whose CSV rows are all REJECTED / empty of products also fail
    """
    accepted = [r for r in rows if r.status != "REJECTED"]
    pending = [
        r
        for r in accepted
        if (r.detection_source or "").strip().upper() in _UNRESOLVED_SOURCES
    ]
    if pending:
        raise LocalInventoryPackageImportError(
            "PACKAGE_UNRESOLVED_ROWS",
            f"{len(pending)} CSV row(s) are LOCAL_PENDING (unresolved). "
            "Re-export the aisle after local scan/confirm.",
        )
    products = [
        r
        for r in accepted
        if (r.detection_source or "").strip().upper() not in _POSITION_MARKER_SOURCES
        and (r.internal_code or "").strip()
    ]
    if not products:
        raise LocalInventoryPackageImportError(
            "PACKAGE_NO_PRODUCTIVE_ROWS",
            "Package has no inventory product rows with an internal_code "
            "(unresolved, position-label-only, or rejected detections).",
        )
