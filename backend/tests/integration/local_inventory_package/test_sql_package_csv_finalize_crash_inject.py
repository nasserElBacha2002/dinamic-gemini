"""SQL crash inject: CSV CONFIRMED while package still MATERIALIZING, then repair."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.application.services.aisle_source_asset_materializer import AisleSourceAssetMaterializer
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.services.local_csv_position_materializer import LocalCsvPositionMaterializer
from src.application.services.product_labels.issued_product_label_resolver import (
    IssuedProductLabelResolver,
)
from src.application.use_cases.inventories.manage_local_csv_import import PreviewLocalCsvImport
from src.application.use_cases.inventories.manage_local_inventory_package import (
    ConfirmLocalInventoryPackage,
    PreviewLocalInventoryPackage,
)
from src.database.sqlserver import SqlServerClient
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus
from src.domain.local_csv_import.entities import LocalCsvImport, LocalCsvImportRow
from src.domain.local_inventory_package.entities import LocalInventoryPackage
from src.infrastructure.repositories.local_csv_inventory_result_writer import (
    SqlLocalCsvInventoryResultWriter,
)
from src.infrastructure.repositories.sql_aisle_repository import SqlAisleRepository
from src.infrastructure.repositories.sql_inventory_counted_product_label_repository import (
    SqlInventoryCountedProductLabelRepository,
)
from src.infrastructure.repositories.sql_inventory_repository import SqlInventoryRepository
from src.infrastructure.repositories.sql_issued_product_label_repository import (
    SqlIssuedProductLabelRepository,
)
from src.infrastructure.repositories.sql_local_csv_import_repository import (
    SqlLocalCsvImportRepository,
)
from src.infrastructure.repositories.sql_local_inventory_package_repository import (
    SqlLocalInventoryPackageRepository,
)
from src.infrastructure.repositories.sql_position_repository import SqlPositionRepository
from src.infrastructure.repositories.sql_product_record_repository import SqlProductRecordRepository
from src.infrastructure.repositories.sql_source_asset_repository import SqlSourceAssetRepository
from tests.support.sql_integration import sql_server_client_or_skip
from tests.support.sql_migration_fixture import ensure_sql_migrations_applied
from tests.support.sqlserver_test_connection import resolved_sqlserver_connection_string_for_tests
from tests.unit.test_local_inventory_package import JPEG_BYTES

pytestmark = pytest.mark.integration

HEADERS = (
    "schema_version",
    "export_id",
    "exported_at",
    "device_id",
    "inventory_id",
    "aisle_id",
    "capture_session_id",
    "capture_photo_id",
    "client_file_id",
    "capture_order",
    "captured_at",
    "position_code",
    "internal_code",
    "quantity",
    "quantity_status",
    "detection_status",
    "source",
    "requires_review",
    "error_code",
    "notes",
)


class FixedClock:
    def __init__(self, moment: datetime | None = None) -> None:
        self._moment = moment or datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self._moment


class MemoryArtifactStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_object(self, key: str, file_obj, content_type: str):
        data = file_obj.read()
        self.objects[key] = data
        mime = content_type

        class Stored:
            storage_provider = "local"
            storage_bucket = None
            storage_key = key
            content_type = mime
            file_size_bytes = len(data)
            etag = hashlib.sha256(data).hexdigest()

        return Stored()

    def save_file(self, key: str, file_obj, content_type: str) -> None:
        self.objects[key] = file_obj.read()

    def delete_file(self, key: str) -> None:
        self.objects.pop(key, None)


@pytest.fixture(scope="module")
def sql_client():
    client = sql_server_client_or_skip(resolved_sqlserver_connection_string_for_tests())
    ensure_sql_migrations_applied(client)
    return client


@pytest.fixture(scope="module")
def connection_string(sql_client):
    return sql_client.connection_string


def _csv_bytes(*, inventory_id: str, aisle_id: str, export_id: str) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=HEADERS, lineterminator="\r\n")
    writer.writeheader()
    writer.writerow(
        {
            "schema_version": "1",
            "export_id": export_id,
            "exported_at": "2026-08-04T10:00:00Z",
            "device_id": "device-1",
            "inventory_id": inventory_id,
            "aisle_id": aisle_id,
            "capture_session_id": "session-1",
            "capture_photo_id": "photo-1",
            "client_file_id": "file-1",
            "capture_order": "1",
            "captured_at": "2026-08-04T09:59:00Z",
            "position_code": "A-01",
            "internal_code": "SKU-1",
            "quantity": "7",
            "quantity_status": "PRESENT",
            "detection_status": "DETECTED",
            "source": "LOCAL_CODE_SCAN",
            "requires_review": "false",
            "error_code": "",
            "notes": "ok",
        }
    )
    return output.getvalue().encode()


def _build_zip(*, inventory_id: str, aisle_id: str, export_id: str) -> bytes:
    csv_bytes = _csv_bytes(
        inventory_id=inventory_id, aisle_id=aisle_id, export_id=export_id
    )
    file_name = "0001_photo-1.jpg"
    sha = hashlib.sha256(JPEG_BYTES).hexdigest()
    manifest = {
        "package_kind": "DINAMIC_LOCAL_AISLE_EXPORT",
        "package_version": 2,
        "status": "COMPLETE",
        "export_id": export_id,
        "inventory_id": inventory_id,
        "aisle_id": aisle_id,
        "capture_session_id": "session-1",
        "freeze_id": "freeze-1",
        "row_count": 1,
        "expected_photo_count": 1,
        "included_photo_count": 1,
        "csv_checksum_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "checksum_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "package_checksum_sha256": "abc",
        "photos": [
            {
                "capture_photo_id": "photo-1",
                "client_file_id": "file-1",
                "sequence_number": 1,
                "file_name": file_name,
                "mime_type": "image/jpeg",
                "size_bytes": len(JPEG_BYTES),
                "sha256": sha,
                "width": 1,
                "height": 1,
                "asset_variant": "ORIGINAL",
            }
        ],
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("results.csv", csv_bytes)
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr(f"photos/{file_name}", JPEG_BYTES)
    return buf.getvalue()


def _seed_inventory_and_aisle(client: SqlServerClient) -> tuple[str, str]:
    inv_repo = SqlInventoryRepository(client)
    aisle_repo = SqlAisleRepository(client)
    now = datetime.now(timezone.utc)
    inv_id = f"inv-crash-{uuid.uuid4().hex[:10]}"
    aisle_id = f"aisle-crash-{uuid.uuid4().hex[:10]}"
    inv_repo.save(
        Inventory(
            id=inv_id,
            name="Package CSV crash inject",
            status=InventoryStatus.DRAFT,
            created_at=now,
            updated_at=now,
            processing_mode=InventoryProcessingMode.TEST,
        )
    )
    aisle_repo.save(
        Aisle(
            id=aisle_id,
            inventory_id=inv_id,
            code=f"C-{uuid.uuid4().hex[:6]}",
            status=AisleStatus.CREATED,
            created_at=now,
            updated_at=now,
        )
    )
    return inv_id, aisle_id


def _build_stack(client: SqlServerClient, *, staging_root: Path) -> dict[str, object]:
    clock = FixedClock()
    csv_repo = SqlLocalCsvImportRepository(client)
    package_repo = SqlLocalInventoryPackageRepository(client, csv_import_repo=csv_repo)
    writer = SqlLocalCsvInventoryResultWriter(client)
    inv_repo = SqlInventoryRepository(client)
    aisle_repo = SqlAisleRepository(client)
    asset_repo = SqlSourceAssetRepository(client)
    storage = MemoryArtifactStorage()
    materializer = AisleSourceAssetMaterializer(
        aisle_repo=aisle_repo,
        asset_repo=asset_repo,
        artifact_storage=storage,  # type: ignore[arg-type]
        status_reconciler=InventoryStatusReconciler(
            inventory_repo=inv_repo,
            aisle_repo=aisle_repo,
            clock=clock,
        ),
    )
    position_materializer = LocalCsvPositionMaterializer(
        position_repo=SqlPositionRepository(client),
        product_record_repo=SqlProductRecordRepository(client),
        counted_product_label_repo=SqlInventoryCountedProductLabelRepository(client),
        issued_label_resolver=IssuedProductLabelResolver(
            issued_repo=SqlIssuedProductLabelRepository(client)
        ),
        inventory_repo=inv_repo,
    )
    csv_preview = PreviewLocalCsvImport(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        import_repo=csv_repo,
        clock=clock,
        enabled=True,
    )
    preview = PreviewLocalInventoryPackage(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        csv_import_repo=csv_repo,
        package_repo=package_repo,
        csv_preview=csv_preview,
        clock=clock,
        enabled=True,
        staging_root=staging_root,
    )
    confirm = ConfirmLocalInventoryPackage(
        package_repo=package_repo,
        result_writer=writer,
        materializer=materializer,
        aisle_repo=aisle_repo,
        inventory_repo=inv_repo,
        clock=clock,
        enabled=True,
        position_materializer=position_materializer,
    )
    return {
        "preview": preview,
        "confirm": confirm,
        "package_repo": package_repo,
        "csv_repo": csv_repo,
        "writer": writer,
    }


def _fresh_read_statuses(
    connection_string: str,
    *,
    inventory_id: str,
    export_id: str,
) -> tuple[str | None, str | None, int]:
    verify = SqlServerClient(connection_string)
    with verify.cursor() as cur:
        cur.execute(
            "SELECT status FROM local_inventory_packages "
            "WHERE inventory_id = ? AND export_id = ?",
            (inventory_id, export_id),
        )
        pkg_row = cur.fetchone()
        cur.execute(
            "SELECT status FROM local_csv_imports WHERE inventory_id = ? AND export_id = ?",
            (inventory_id, export_id),
        )
        csv_row = cur.fetchone()
        cur.execute(
            "SELECT COUNT(*) FROM local_csv_productive_results WHERE inventory_id = ?",
            (inventory_id,),
        )
        productive_row = cur.fetchone()
    return (
        str(pkg_row.status) if pkg_row else None,
        str(csv_row.status) if csv_row else None,
        int(productive_row[0]) if productive_row else 0,
    )


def _package_csv_inconsistent(
    client: SqlServerClient, *, inventory_id: str, export_id: str
) -> bool:
    """Mirror preflight PACKAGE_CSV_INCONSISTENT predicate for one export."""
    with client.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM dbo.local_inventory_packages p
            INNER JOIN dbo.local_csv_imports i ON i.id = p.csv_import_id
            WHERE p.inventory_id = ? AND p.export_id = ?
              AND (
                    (p.status = N'CONFIRMED' AND i.status <> N'CONFIRMED')
                 OR (i.status = N'CONFIRMED' AND p.status <> N'CONFIRMED')
              )
            """,
            (inventory_id, export_id),
        )
        return cur.fetchone() is not None


def test_crash_after_csv_finalize_before_package_repaired_by_retry(
    sql_client, connection_string, tmp_path: Path
) -> None:
    """Simulate process death after CSV finalize, before package CONFIRMED.

    Setup uses the same claim/stage path as production confirm, then finalizes
    the CSV import alone (outside package finalize). Asserts the mismatch is
    detectable and that retry confirm completes the package atomically.
    """
    inventory_id, aisle_id = _seed_inventory_and_aisle(sql_client)
    export_id = f"export-crash-{uuid.uuid4().hex[:8]}"
    staging = tmp_path / "crash"
    stack = _build_stack(sql_client, staging_root=staging)
    preview = stack["preview"]
    assert isinstance(preview, PreviewLocalInventoryPackage)
    preview.execute(
        inventory_id=inventory_id,
        content=_build_zip(
            inventory_id=inventory_id, aisle_id=aisle_id, export_id=export_id
        ),
    )

    package_repo = stack["package_repo"]
    csv_repo = stack["csv_repo"]
    writer = stack["writer"]
    assert isinstance(package_repo, SqlLocalInventoryPackageRepository)
    assert isinstance(csv_repo, SqlLocalCsvImportRepository)
    assert isinstance(writer, SqlLocalCsvInventoryResultWriter)

    claim_owner = "crash-inject-owner"
    clock = FixedClock()

    def apply_productive(
        record: LocalCsvImport,
        rows_to_import: tuple[LocalCsvImportRow, ...],
        confirmed_by_user_id: str | None,
        package: LocalInventoryPackage,
        *,
        cursor=None,
    ):
        _ = package
        return writer.apply_import(
            record=record,
            rows_to_import=rows_to_import,
            confirmed_by_user_id=confirmed_by_user_id,
            cursor=cursor,
        )

    claimed, duplicate = package_repo.confirm_package_atomically(
        inventory_id=inventory_id,
        export_id=export_id,
        conflict_policy="SKIP",
        confirmed_by_user_id="user-crash",
        apply_productive=apply_productive,
        clock_now=clock.now,
        owner=claim_owner,
        lease_sec=120,
    )
    assert duplicate is False
    assert claimed.status == "MATERIALIZING"
    assert claimed.csv_import is not None
    assert claimed.csv_import.status == "MATERIALIZING"
    fencing = int(claimed.csv_import.fencing_version)

    # Crash inject: CSV reaches CONFIRMED; package remains MATERIALIZING.
    csv_repo.finalize_import_confirmation(
        import_id=claimed.csv_import_id,
        clock_now=clock.now,
        confirmed_by_user_id="user-crash",
        owner=claim_owner,
        expected_fencing_version=fencing,
    )

    pkg_status, csv_status, productive_count = _fresh_read_statuses(
        connection_string, inventory_id=inventory_id, export_id=export_id
    )
    assert csv_status == "CONFIRMED"
    assert pkg_status == "MATERIALIZING"
    assert productive_count >= 1
    assert _package_csv_inconsistent(
        sql_client, inventory_id=inventory_id, export_id=export_id
    )

    # Repair path: retry package confirm finalizes package without duplicating productive.
    confirm = stack["confirm"]
    assert isinstance(confirm, ConfirmLocalInventoryPackage)
    repaired, _ = confirm.execute(
        inventory_id=inventory_id,
        export_id=export_id,
        confirmed_by_user_id="user-crash-retry",
        owner="crash-repair-owner",
    )
    assert repaired.status == "CONFIRMED"

    pkg_status, csv_status, productive_after = _fresh_read_statuses(
        connection_string, inventory_id=inventory_id, export_id=export_id
    )
    assert pkg_status == "CONFIRMED"
    assert csv_status == "CONFIRMED"
    assert productive_after == productive_count
    assert not _package_csv_inconsistent(
        sql_client, inventory_id=inventory_id, export_id=export_id
    )
