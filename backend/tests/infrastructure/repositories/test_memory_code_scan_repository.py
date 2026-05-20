"""Memory CodeScanRepository — atomic latest replacement semantics."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.domain.code_scans.entities import CodeScanRun, CodeScanRunStatus
from src.infrastructure.repositories.memory_code_scan_repository import MemoryCodeScanRepository


def _run(run_id: str, *, is_latest: bool = True) -> CodeScanRun:
    now = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
    return CodeScanRun(
        id=run_id,
        inventory_id="inv-1",
        aisle_id="aisle-1",
        status=CodeScanRunStatus.COMPLETED,
        total_assets=1,
        processed_assets=1,
        failed_assets=0,
        total_codes_found=0,
        total_qr_found=0,
        total_barcodes_found=0,
        started_at=now,
        finished_at=now,
        scanner_engine="noop",
        is_latest=is_latest,
    )


def test_replace_latest_run_preserves_previous_on_insert_failure() -> None:
    repo = MemoryCodeScanRepository()
    first = _run("run-1")
    repo.replace_latest_run(first)
    assert repo.get_latest_run_by_aisle(inventory_id="inv-1", aisle_id="aisle-1") is first

    class BrokenDict(dict):
        def __setitem__(self, key, value):
            if key == "run-2":
                raise RuntimeError("simulated insert failure")
            return super().__setitem__(key, value)

    repo._runs = BrokenDict(repo._runs)  # type: ignore[assignment]
    second = _run("run-2")
    with pytest.raises(RuntimeError, match="simulated insert"):
        repo.replace_latest_run(second)

    latest = repo.get_latest_run_by_aisle(inventory_id="inv-1", aisle_id="aisle-1")
    assert latest is not None
    assert latest.id == "run-1"
    assert latest.is_latest is True
    assert "run-2" not in repo._runs
