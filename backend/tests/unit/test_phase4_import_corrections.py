"""Phase 4 corrections — lease, canonical rejects, published visibility."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

import pytest

from src.application.services.import_canonical_materialization_policy import (
    raise_for_canonical_failures,
)
from src.application.services.import_canonical_position_materializer import (
    ImportCanonicalMaterializationSummary,
)
from src.application.use_cases.inventories.manage_local_csv_import import ConfirmLocalCsvImport
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.local_csv_import.error_codes import LOCAL_CSV_CANONICAL_MATERIALIZATION_REJECTED
from src.domain.local_csv_import.errors import LocalCsvImportError
from src.domain.local_csv_import.lease import build_lease_claim, lease_is_active
from src.domain.local_csv_import.statuses import (
    LOCAL_CSV_IMPORT_STATUS_CONFIRMED,
    LOCAL_CSV_IMPORT_STATUS_MATERIALIZING,
)
from src.domain.position_materialization.entities import PositionMaterializationStatus
from src.infrastructure.repositories.local_csv_inventory_result_writer import (
    MemoryLocalCsvInventoryResultWriter,
)
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_local_csv_import_repository import (
    MemoryLocalCsvImportRepository,
)
from tests.unit.test_local_csv_import import FixedClock, _csv_bytes
from tests.unit.test_phase4_import_hardening import NOW


def test_active_lease_blocks_second_owner() -> None:
    import_repo = MemoryLocalCsvImportRepository()
    inventory_repo = MemoryInventoryRepository()
    inventory_repo.save(
        Inventory(
            id="inventory-1",
            name="I",
            status=InventoryStatus.DRAFT,
            created_at=NOW,
            updated_at=NOW,
            client_id="c1",
        )
    )
    aisle_repo = MemoryAisleRepository()
    aisle_repo.save(
        Aisle(
            id="aisle-1",
            inventory_id="inventory-1",
            code="A",
            status=AisleStatus.CREATED,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    from src.application.use_cases.inventories.manage_local_csv_import import (
        PreviewLocalCsvImport,
    )

    preview = PreviewLocalCsvImport(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        import_repo=import_repo,
        clock=FixedClock(),
        enabled=True,
    )
    staged = preview.execute(inventory_id="inventory-1", content=_csv_bytes())
    writer = MemoryLocalCsvInventoryResultWriter(
        get_import_status=lambda i: (import_repo.get_by_id(i) or staged).status
    )
    confirm = ConfirmLocalCsvImport(
        import_repo=import_repo,
        result_writer=writer,
        clock=FixedClock(),
        enabled=True,
        inventory_repo=inventory_repo,
        position_materializer=MagicMock(materialize=MagicMock(return_value=1)),
        materialization_lease_sec=600,
    )
    claimed, _ = confirm.execute(
        inventory_id="inventory-1",
        export_id=staged.export_id,
        confirmed_by_user_id="user-a",
        owner="owner-a",
    )
    assert claimed.status == LOCAL_CSV_IMPORT_STATUS_CONFIRMED

    # Re-preview path not needed — force a MATERIALIZING row for lease conflict.
    materializing = import_repo.get_by_id(claimed.id)
    assert materializing is not None
    from dataclasses import replace

    stuck = replace(
        materializing,
        status=LOCAL_CSV_IMPORT_STATUS_MATERIALIZING,
        materialization_owner="owner-a",
        materialization_lease_expires_at=NOW + timedelta(minutes=10),
        confirmed_at=None,
        fencing_version=materializing.fencing_version + 1,
    )
    import_repo.save(stuck)
    with pytest.raises(LocalCsvImportError) as exc:
        confirm.execute(
            inventory_id="inventory-1",
            export_id=staged.export_id,
            confirmed_by_user_id="user-b",
            owner="owner-b",
        )
    assert exc.value.code == "LOCAL_CSV_MATERIALIZATION_IN_PROGRESS"


def test_canonical_permanent_reject_blocks_confirmed() -> None:
    summary = ImportCanonicalMaterializationSummary(
        attempted=1,
        created_or_reused=0,
        skipped=0,
        failed=1,
        last_status=PositionMaterializationStatus.REJECTED_VALIDATION.value,
        last_error_code="INVALID_MATERIALIZATION_REQUEST",
        last_detail="bad",
    )
    with pytest.raises(LocalCsvImportError) as exc:
        raise_for_canonical_failures(summary)
    assert exc.value.code == LOCAL_CSV_CANONICAL_MATERIALIZATION_REJECTED


def test_build_lease_claim_blocks_active_lease_even_for_same_owner() -> None:
    from src.domain.local_csv_import.entities import LocalCsvImport

    record = LocalCsvImport(
        id="i1",
        export_id="e1",
        schema_version="1.1",
        inventory_id="inv",
        device_id="d",
        exported_at=NOW,
        status=LOCAL_CSV_IMPORT_STATUS_MATERIALIZING,
        content_hash="h",
        total_rows=1,
        valid_rows=1,
        rejected_rows=0,
        duplicate_rows=0,
        created_at=NOW,
        updated_at=NOW,
        materialization_owner="owner-a",
        materialization_lease_expires_at=NOW + timedelta(minutes=5),
        materialization_attempts=1,
        fencing_version=2,
    )
    assert lease_is_active(record, now=NOW)
    with pytest.raises(LocalCsvImportError) as exc:
        build_lease_claim(record, now=NOW, owner="owner-a", lease_sec=120)
    assert exc.value.code == "LOCAL_CSV_MATERIALIZATION_IN_PROGRESS"


def test_unpublished_results_hidden_until_confirmed() -> None:
    from src.domain.local_csv_import.entities import LocalCsvProductiveResult

    statuses = {"imp-1": LOCAL_CSV_IMPORT_STATUS_MATERIALIZING}
    writer = MemoryLocalCsvInventoryResultWriter(
        get_import_status=lambda i: statuses.get(i)
    )
    result = LocalCsvProductiveResult(
        id="p1",
        inventory_id="inventory-1",
        aisle_id="aisle-1",
        import_id="imp-1",
        import_row_id="r1",
        capture_session_id="s",
        capture_photo_id="ph",
        client_file_id="f",
        capture_order=1,
        position_code="A01",
        internal_code="SKU",
        quantity=1,
        quantity_status="ok",
        detection_status="ok",
        detection_source="LOCAL_CODE_SCAN",
        ingestion_source="LOCAL_CSV_IMPORT",
        requires_review=False,
        has_image_evidence=False,
        confirmed_by_user_id="u",
        created_at=NOW,
        updated_at=NOW,
    )
    writer._by_id[result.id] = result
    assert writer.list_for_inventory("inventory-1") == ()
    assert writer.list_for_import("imp-1") == (result,)
    statuses["imp-1"] = LOCAL_CSV_IMPORT_STATUS_CONFIRMED
    assert writer.list_for_inventory("inventory-1") == (result,)
