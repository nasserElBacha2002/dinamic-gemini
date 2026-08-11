"""SQL Server: PLAN→STAGE→APPLY race window for package confirm."""

from __future__ import annotations

import threading
import uuid
from pathlib import Path

import pytest

from src.domain.local_csv_import.entities import LocalCsvImport, LocalCsvImportRow
from src.domain.local_inventory_package.entities import LocalInventoryPackage
from src.infrastructure.repositories.local_csv_inventory_result_writer import (
    SqlLocalCsvInventoryResultWriter,
)
from src.infrastructure.repositories.sql_local_csv_import_repository import (
    SqlLocalCsvImportRepository,
    partition_secondary_key_candidates,
)
from src.infrastructure.repositories.sql_local_inventory_package_repository import (
    SqlLocalInventoryPackageRepository,
)
from tests.integration.local_inventory_package.test_sql_package_confirm_transaction import (
    FixedClock,
    _build_stack,
    _count_productive,
    _csv_bytes,
    _preview_package,
    _seed_inventory_and_aisle,
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


def test_plan_stage_apply_race_marks_duplicate_without_productive_dupes(
    sql_client, tmp_path: Path
) -> None:
    """PLAN sees row importable; concurrent confirm claims secondary_key; APPLY → DUPLICATE.

    Policy: staged SourceAsset for the losing row may remain as a recoverable orphan
    (upload_batch_id=package.id, not referenced by productive results). Storage stays
    outside SQL locks; unique constraints remain authority.
    """
    inv_id, aisle_id = _seed_inventory_and_aisle(sql_client)
    stack = _build_stack(sql_client, staging_root=tmp_path)
    shared_session = f"sess-race-{uuid.uuid4().hex[:8]}"
    shared_photo = "photo-shared"
    export_a = f"exp-a-{uuid.uuid4().hex[:8]}"
    export_b = f"exp-b-{uuid.uuid4().hex[:8]}"

    # Package A — PLAN will see this secondary key as importable.
    _preview_package(
        stack,
        inventory_id=inv_id,
        aisle_id=aisle_id,
        export_id=export_a,
        session_id=shared_session,
        photo_id=shared_photo,
    )

    # CSV-only import B with the same (session, photo:…) secondary key.
    csv_preview = stack["csv_preview"]
    csv_preview.execute(  # type: ignore[attr-defined]
        inventory_id=inv_id,
        content=_csv_bytes(
            inventory_id=inv_id,
            aisle_id=aisle_id,
            export_id=export_b,
            session_id=shared_session,
            photo_id=shared_photo,
            client_file_id="file-b",
        ),
    )

    package_repo = stack["package_repo"]
    assert isinstance(package_repo, SqlLocalInventoryPackageRepository)
    writer = stack["writer"]
    assert isinstance(writer, SqlLocalCsvInventoryResultWriter)
    confirm_uc = stack["confirm"]
    clock = FixedClock()

    plan_done = threading.Event()
    b_done = threading.Event()
    staged_assets: dict[str, str] = {}
    errors: list[BaseException] = []

    def stage_evidence(
        pkg: LocalInventoryPackage,
        record: LocalCsvImport,
        rows_to_import: tuple[LocalCsvImportRow, ...],
    ) -> dict[str, str]:
        # PLAN locks released; pause before staging so B can confirm first.
        plan_done.set()
        assert b_done.wait(timeout=45), "thread B did not confirm in time"
        assets = confirm_uc._stage_source_assets_for_rows(  # noqa: SLF001
            pkg, record, rows_to_import
        )
        staged_assets.update(assets)
        return assets

    def apply_productive(
        record: LocalCsvImport,
        rows_to_import: tuple[LocalCsvImportRow, ...],
        confirmed_by_user_id: str | None,
        package: LocalInventoryPackage,
        *,
        cursor=None,
    ):
        _ = package
        evidence = {
            row.id: staged_assets[row.capture_photo_id]
            for row in rows_to_import
            if row.capture_photo_id in staged_assets
        }
        return writer.apply_import(
            record=record,
            rows_to_import=rows_to_import,
            confirmed_by_user_id=confirmed_by_user_id,
            image_evidence_by_import_row_id=evidence,
            cursor=cursor,
        )

    def thread_a() -> None:
        try:
            package_repo.confirm_package_atomically(
                inventory_id=inv_id,
                export_id=export_a,
                conflict_policy="SKIP",
                confirmed_by_user_id="user-a",
                apply_productive=apply_productive,
                clock_now=clock.now,
                stage_evidence=stage_evidence,
            )
        except BaseException as exc:  # noqa: BLE001 — capture for main thread
            errors.append(exc)

    def thread_b() -> None:
        try:
            assert plan_done.wait(timeout=45), "thread A plan did not complete"
            csv_confirm = stack["csv_confirm"]
            csv_confirm.execute(  # type: ignore[attr-defined]
                inventory_id=inv_id,
                export_id=export_b,
                conflict_policy="SKIP",
                confirmed_by_user_id="user-b",
            )
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            b_done.set()

    t_a = threading.Thread(target=thread_a, name="pkg-confirm-a")
    t_b = threading.Thread(target=thread_b, name="csv-confirm-b")
    t_a.start()
    t_b.start()
    t_a.join(timeout=90)
    t_b.join(timeout=90)
    assert not t_a.is_alive() and not t_b.is_alive()
    assert not errors, f"concurrent errors: {errors!r}"

    # Fresh connection read
    fresh = type(sql_client)(sql_client.connection_string)
    csv_fresh = SqlLocalCsvImportRepository(fresh)
    pkg_fresh = SqlLocalInventoryPackageRepository(fresh, csv_import_repo=csv_fresh)
    writer_fresh = SqlLocalCsvInventoryResultWriter(fresh)

    pkg_final = pkg_fresh.get_by_export_id(inventory_id=inv_id, export_id=export_a)
    assert pkg_final is not None
    assert pkg_final.status == "CONFIRMED"
    csv_a = csv_fresh.get_by_id(pkg_final.csv_import_id)
    assert csv_a is not None
    assert csv_a.status == "CONFIRMED"
    assert csv_a.rows[0].status == "DUPLICATE"

    csv_b = csv_fresh.get_by_export_id(inventory_id=inv_id, export_id=export_b)
    assert csv_b is not None
    assert csv_b.status == "CONFIRMED"
    assert csv_b.rows[0].status == "IMPORTED"

    productives = writer_fresh.list_for_inventory(inv_id)
    assert len(productives) == 1
    assert productives[0].import_id == csv_b.id
    assert productives[0].capture_photo_id == shared_photo
    assert _count_productive(fresh, inv_id) == 1

    if staged_assets:
        used = {p.source_asset_id for p in productives if p.source_asset_id}
        orphans = [aid for aid in staged_assets.values() if aid not in used]
        assert all(aid not in used for aid in orphans)


def test_partition_rejects_unknown_secondary_key_prefix() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        partition_secondary_key_candidates({("sess", "future:xyz")})
