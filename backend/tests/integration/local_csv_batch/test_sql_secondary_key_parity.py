"""Parity: candidate-scoped secondary keys == full-scan semantics."""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus
from src.domain.local_csv_import.entities import (
    LocalCsvImport,
    LocalCsvImportRow,
    local_csv_row_secondary_key,
)
from src.domain.local_csv_import.sources import INGESTION_SOURCE_LOCAL_CSV_IMPORT
from src.infrastructure.repositories.local_csv_inventory_result_writer import (
    SqlLocalCsvInventoryResultWriter,
)
from src.infrastructure.repositories.sql_aisle_repository import SqlAisleRepository
from src.infrastructure.repositories.sql_inventory_repository import SqlInventoryRepository
from src.infrastructure.repositories.sql_local_csv_import_repository import (
    SqlLocalCsvImportRepository,
    partition_secondary_key_candidates,
)
from tests.support.sql_integration import sql_server_client_or_skip
from tests.support.sql_migration_fixture import ensure_sql_migrations_applied
from tests.support.sqlserver_test_connection import resolved_sqlserver_connection_string_for_tests

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def sql_client():
    client = sql_server_client_or_skip(resolved_sqlserver_connection_string_for_tests())
    ensure_sql_migrations_applied(client)
    return client


def _seed(client) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    inv_id = f"inv-parity-{uuid.uuid4().hex[:10]}"
    aisle_id = f"aisle-parity-{uuid.uuid4().hex[:10]}"
    SqlInventoryRepository(client).save(
        Inventory(
            id=inv_id,
            name="secondary key parity",
            status=InventoryStatus.DRAFT,
            created_at=now,
            updated_at=now,
            processing_mode=InventoryProcessingMode.TEST,
        )
    )
    SqlAisleRepository(client).save(
        Aisle(
            id=aisle_id,
            inventory_id=inv_id,
            code=f"P-{uuid.uuid4().hex[:6]}",
            status=AisleStatus.CREATED,
            created_at=now,
            updated_at=now,
        )
    )
    return inv_id, aisle_id


def _row(
    *,
    import_id: str,
    inventory_id: str,
    aisle_id: str,
    n: int,
    session: str,
    photo: str,
    label_id: str | None,
    detection_source: str,
) -> LocalCsvImportRow:
    return LocalCsvImportRow(
        id=str(uuid.uuid4()),
        import_id=import_id,
        row_number=n,
        inventory_id=inventory_id,
        aisle_id=aisle_id,
        capture_session_id=session,
        capture_photo_id=photo,
        client_file_id=f"file-{n}",
        capture_order=n,
        captured_at=datetime.now(timezone.utc),
        position_code=f"P-{n}",
        internal_code=f"SKU-{n}",
        quantity=1,
        quantity_status="PRESENT",
        detection_status="DETECTED",
        detection_source=detection_source,
        ingestion_source=INGESTION_SOURCE_LOCAL_CSV_IMPORT,
        requires_review=False,
        error_code=None,
        notes=None,
        status="PREVIEW_VALID",
        label_id=label_id,
    )


def test_secondary_key_prefixes_cover_domain_shapes() -> None:
    """Fail if domain adds a new secondary_key prefix without updating SQL partitioning."""
    label = local_csv_row_secondary_key(
        capture_session_id="s",
        capture_photo_id="p",
        label_id="ABC",
        detection_source="LOCAL_CODE_SCAN",
    )
    photo = local_csv_row_secondary_key(
        capture_session_id="s",
        capture_photo_id="p",
        label_id=None,
        detection_source="LOCAL_CODE_SCAN",
    )
    pos = local_csv_row_secondary_key(
        capture_session_id="s",
        capture_photo_id="p",
        label_id=None,
        detection_source="LOCAL_POSITION_LABEL",
    )
    assert label[1].startswith("label:")
    assert photo[1].startswith("photo:")
    assert pos[1].startswith("pos:")
    partition_secondary_key_candidates({label, photo, pos})


def test_candidate_scoped_matches_full_scan_for_all_key_shapes(sql_client) -> None:
    inv_id, aisle_id = _seed(sql_client)
    csv_repo = SqlLocalCsvImportRepository(sql_client)
    writer = SqlLocalCsvInventoryResultWriter(sql_client)
    now = datetime.now(timezone.utc)
    import_id = str(uuid.uuid4())
    session = f"sess-{uuid.uuid4().hex[:8]}"

    rows = (
        _row(
            import_id=import_id,
            inventory_id=inv_id,
            aisle_id=aisle_id,
            n=1,
            session=session,
            photo="photo-label",
            label_id=f"L{uuid.uuid4().hex[:8].upper()}",
            detection_source="LOCAL_CODE_SCAN",
        ),
        _row(
            import_id=import_id,
            inventory_id=inv_id,
            aisle_id=aisle_id,
            n=2,
            session=session,
            photo="photo-legacy",
            label_id=None,
            detection_source="LOCAL_CODE_SCAN",
        ),
        _row(
            import_id=import_id,
            inventory_id=inv_id,
            aisle_id=aisle_id,
            n=3,
            session=session,
            photo="photo-pos",
            label_id=None,
            detection_source="LOCAL_POSITION_LABEL",
        ),
    )
    record = LocalCsvImport(
        id=import_id,
        export_id=f"exp-{uuid.uuid4().hex[:10]}",
        schema_version="1",
        inventory_id=inv_id,
        device_id="parity",
        exported_at=now,
        status="PREVIEWED",
        content_hash=uuid.uuid4().hex,
        total_rows=3,
        valid_rows=3,
        rejected_rows=0,
        duplicate_rows=0,
        created_at=now,
        updated_at=now,
        rows=rows,
    )
    csv_repo.save(record)
    writer.apply_import(record=record, rows_to_import=rows, confirmed_by_user_id=None)
    confirmed = replace(
        record,
        status="CONFIRMED",
        confirmed_at=now,
        rows=tuple(replace(r, status="IMPORTED") for r in rows),
    )
    csv_repo.save(confirmed)

    # Candidate keys: all three shapes + one miss.
    keys = {r.secondary_key for r in rows}
    keys.add(("other-session", "label:MISSING"))
    keys.add(("other-session", "photo:missing"))
    keys.add(("other-session", "pos:missing"))

    scoped = csv_repo.find_confirmed_secondary_keys(keys)
    full = csv_repo.find_confirmed_secondary_keys_full_scan(keys)
    assert scoped == full
    assert scoped == {r.secondary_key for r in rows}
