"""Unit coverage for durable local CSV import recovery."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

from src.application.services.local_csv_import_recovery import (
    LocalCsvImportRecoveryConfig,
    LocalCsvImportRecoveryService,
)
from src.application.use_cases.inventories.manage_local_csv_import import ConfirmLocalCsvImport
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.local_csv_import.entities import LocalCsvImport
from src.domain.local_csv_import.statuses import (
    LOCAL_CSV_IMPORT_STATUS_CONFIRMED,
    LOCAL_CSV_IMPORT_STATUS_MATERIALIZATION_FAILED,
    LOCAL_CSV_IMPORT_STATUS_MATERIALIZING,
    LOCAL_CSV_IMPORT_STATUS_REQUIRES_REVIEW,
)
from src.infrastructure.repositories.local_csv_inventory_result_writer import (
    MemoryLocalCsvInventoryResultWriter,
)
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_local_csv_import_repository import (
    MemoryLocalCsvImportRepository,
)
NOW = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)


class FixedClock:
    def now(self) -> datetime:
        return NOW


def _import(
    *,
    status: str,
    attempts: int = 1,
    lease_expired: bool = True,
) -> LocalCsvImport:
    lease = NOW - timedelta(minutes=5) if lease_expired else NOW + timedelta(minutes=5)
    return LocalCsvImport(
        id="import-1",
        export_id="export-1",
        schema_version="1",
        inventory_id="inventory-1",
        device_id="device-1",
        exported_at=NOW,
        status=status,
        content_hash="hash",
        total_rows=0,
        valid_rows=0,
        rejected_rows=0,
        duplicate_rows=0,
        created_at=NOW,
        updated_at=NOW,
        materialization_attempts=attempts,
        materialization_owner="old-owner",
        materialization_lease_expires_at=lease,
        fencing_version=1,
    )


def test_recovery_exhausts_to_requires_review() -> None:
    inventory_repo = MemoryInventoryRepository()
    inventory_repo.save(
        Inventory(
            id="inventory-1",
            name="Inv",
            status=InventoryStatus.DRAFT,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    import_repo = MemoryLocalCsvImportRepository()
    import_repo.save(
        _import(
            status=LOCAL_CSV_IMPORT_STATUS_MATERIALIZATION_FAILED,
            attempts=5,
            lease_expired=True,
        )
    )
    clock = FixedClock()
    confirm = ConfirmLocalCsvImport(
        import_repo=import_repo,
        result_writer=MemoryLocalCsvInventoryResultWriter(
            get_import_status=lambda i: (
                None if (r := import_repo.get_by_id(i)) is None else r.status
            )
        ),
        clock=clock,
        enabled=True,
        inventory_repo=inventory_repo,
    )
    service = LocalCsvImportRecoveryService(
        import_repo=import_repo,
        confirm=confirm,
        clock=clock,
        config=LocalCsvImportRecoveryConfig(max_attempts=5),
    )
    recovered = service.run_once(now=NOW)
    assert recovered == 0
    record = import_repo.get_by_id("import-1")
    assert record is not None
    assert record.status == LOCAL_CSV_IMPORT_STATUS_REQUIRES_REVIEW


def test_recovery_skips_active_lease() -> None:
    inventory_repo = MemoryInventoryRepository()
    inventory_repo.save(
        Inventory(
            id="inventory-1",
            name="Inv",
            status=InventoryStatus.DRAFT,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    import_repo = MemoryLocalCsvImportRepository()
    import_repo.save(
        _import(status=LOCAL_CSV_IMPORT_STATUS_MATERIALIZING, lease_expired=False)
    )
    clock = FixedClock()
    confirm = ConfirmLocalCsvImport(
        import_repo=import_repo,
        result_writer=MemoryLocalCsvInventoryResultWriter(),
        clock=clock,
        enabled=True,
        inventory_repo=inventory_repo,
    )
    service = LocalCsvImportRecoveryService(
        import_repo=import_repo,
        confirm=confirm,
        clock=clock,
    )
    assert service.run_once(now=NOW) == 0
    record = import_repo.get_by_id("import-1")
    assert record is not None
    assert record.status == LOCAL_CSV_IMPORT_STATUS_MATERIALIZING


def test_recovery_two_workers_one_wins_expired_lease() -> None:
    """Two recovery owners race one MATERIALIZING expired-lease import.

    Claim/reclaim is serialized by the repo lock: exactly one owner wins the
    lease; the second gets LOCAL_CSV_MATERIALIZATION_IN_PROGRESS. The winner
    then completes via Confirm (same path recovery uses).
    """
    from src.domain.local_csv_import.error_codes import (
        LOCAL_CSV_MATERIALIZATION_IN_PROGRESS,
    )
    from src.domain.local_csv_import.errors import LocalCsvImportError

    inventory_repo = MemoryInventoryRepository()
    inventory_repo.save(
        Inventory(
            id="inventory-1",
            name="Inv",
            status=InventoryStatus.DRAFT,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    import_repo = MemoryLocalCsvImportRepository()
    import_repo.save(
        _import(status=LOCAL_CSV_IMPORT_STATUS_MATERIALIZING, attempts=1, lease_expired=True)
    )
    clock = FixedClock()
    writer = MemoryLocalCsvInventoryResultWriter(
        get_import_status=lambda i: (
            None if (r := import_repo.get_by_id(i)) is None else r.status
        )
    )

    barrier = threading.Barrier(2)
    outcomes: list[tuple] = []
    lock = threading.Lock()

    def _apply(*_args, **_kwargs):
        return ()

    def race_claim(owner: str) -> None:
        barrier.wait(timeout=5)
        try:
            claimed, duplicate = import_repo.claim_import_for_materialization(
                inventory_id="inventory-1",
                export_id="export-1",
                conflict_policy="SKIP",
                confirmed_by_user_id=owner,
                apply_productive=_apply,
                clock_now=clock.now,
                owner=owner,
                lease_sec=120,
            )
            with lock:
                outcomes.append(
                    (
                        "claimed",
                        owner,
                        claimed.materialization_owner,
                        int(claimed.fencing_version),
                        duplicate,
                    )
                )
        except LocalCsvImportError as exc:
            with lock:
                outcomes.append(("err", owner, exc.code))

    threads = [
        threading.Thread(target=race_claim, args=("recovery-owner-a",)),
        threading.Thread(target=race_claim, args=("recovery-owner-b",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    assert len(outcomes) == 2
    winners = [o for o in outcomes if o[0] == "claimed"]
    losers = [o for o in outcomes if o[0] == "err"]
    assert len(winners) == 1
    assert len(losers) == 1
    assert losers[0][2] == LOCAL_CSV_MATERIALIZATION_IN_PROGRESS
    winner_owner = winners[0][1]
    assert winners[0][2] == winner_owner

    # Loser recovery worker: active lease → IN_PROGRESS catch → recovered 0
    loser_confirm = ConfirmLocalCsvImport(
        import_repo=import_repo,
        result_writer=writer,
        clock=clock,
        enabled=True,
        inventory_repo=inventory_repo,
    )
    loser_service = LocalCsvImportRecoveryService(
        import_repo=import_repo,
        confirm=loser_confirm,
        clock=clock,
        config=LocalCsvImportRecoveryConfig(max_attempts=5, lease_sec=120),
    )
    assert loser_service.run_once(now=NOW) == 0
    mid = import_repo.get_by_id("import-1")
    assert mid is not None
    assert mid.status == LOCAL_CSV_IMPORT_STATUS_MATERIALIZING
    assert mid.materialization_owner == winner_owner

    # Winner completes confirm (recovery reuse path).
    winner_confirm = ConfirmLocalCsvImport(
        import_repo=import_repo,
        result_writer=writer,
        clock=clock,
        enabled=True,
        inventory_repo=inventory_repo,
    )
    # Lease still active for winner — expire it so confirm can reclaim/finalize.
    from dataclasses import replace

    import_repo.save(
        replace(
            mid,
            materialization_lease_expires_at=NOW - timedelta(seconds=1),
        )
    )
    confirmed, duplicate = winner_confirm.execute(
        inventory_id="inventory-1",
        export_id="export-1",
        owner=winner_owner,
    )
    assert duplicate is False
    assert confirmed.status == LOCAL_CSV_IMPORT_STATUS_CONFIRMED
    final = import_repo.get_by_id("import-1")
    assert final is not None
    assert final.status == LOCAL_CSV_IMPORT_STATUS_CONFIRMED
