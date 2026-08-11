"""Unit tests for package confirm transactional boundary (memory / injected failures)."""

from __future__ import annotations

import threading
from dataclasses import replace
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
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.local_inventory_package.errors import LocalInventoryPackageImportError
from src.infrastructure.repositories.local_csv_inventory_result_writer import (
    MemoryLocalCsvInventoryResultWriter,
)
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_inventory_counted_product_label_repository import (
    MemoryInventoryCountedProductLabelRepository,
)
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_issued_product_label_repository import (
    MemoryIssuedProductLabelRepository,
)
from src.infrastructure.repositories.memory_local_csv_import_repository import (
    MemoryLocalCsvImportRepository,
)
from src.infrastructure.repositories.memory_local_inventory_package_repository import (
    MemoryLocalInventoryPackageRepository,
)
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.repositories.memory_product_record_repository import (
    MemoryProductRecordRepository,
)
from src.infrastructure.repositories.memory_source_asset_repository import (
    MemorySourceAssetRepository,
)
from tests.unit.test_local_inventory_package import (
    NOW,
    FixedClock,
    MemoryArtifactStorage,
    _build_zip,
)


def _seed_previewed(tmp_path: Path):
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    inv_repo.save(
        Inventory(
            id="inventory-1",
            name="Inv",
            status=InventoryStatus.DRAFT,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    aisle_repo.save(
        Aisle(
            id="aisle-1",
            inventory_id="inventory-1",
            code="A1",
            status=AisleStatus.CREATED,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    csv_repo = MemoryLocalCsvImportRepository()
    package_repo = MemoryLocalInventoryPackageRepository(csv_import_repo=csv_repo)
    storage = MemoryArtifactStorage()
    assets = MemorySourceAssetRepository()
    writer = MemoryLocalCsvInventoryResultWriter()
    clock = FixedClock()
    materializer = AisleSourceAssetMaterializer(
        aisle_repo=aisle_repo,
        asset_repo=assets,
        artifact_storage=storage,  # type: ignore[arg-type]
        status_reconciler=InventoryStatusReconciler(
            inventory_repo=inv_repo,
            aisle_repo=aisle_repo,
            clock=clock,
        ),
    )
    positions = MemoryPositionRepository()
    products = MemoryProductRecordRepository()
    position_materializer = LocalCsvPositionMaterializer(
        position_repo=positions,
        product_record_repo=products,
        counted_product_label_repo=MemoryInventoryCountedProductLabelRepository(),
        issued_label_resolver=IssuedProductLabelResolver(
            issued_repo=MemoryIssuedProductLabelRepository()
        ),
        inventory_repo=inv_repo,
    )
    preview = PreviewLocalInventoryPackage(
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        csv_import_repo=csv_repo,
        package_repo=package_repo,
        csv_preview=PreviewLocalCsvImport(
            inventory_repo=inv_repo,
            aisle_repo=aisle_repo,
            import_repo=csv_repo,
            clock=clock,
            enabled=True,
        ),
        clock=clock,
        enabled=True,
        staging_root=tmp_path,
    )
    pkg = preview.execute(inventory_id="inventory-1", content=_build_zip())
    confirm = ConfirmLocalInventoryPackage(
        package_repo=package_repo,
        result_writer=writer,
        materializer=materializer,
        aisle_repo=aisle_repo,
        clock=clock,
        enabled=True,
        position_materializer=position_materializer,
    )
    return pkg, confirm, package_repo, csv_repo, writer, assets, aisle_repo, inv_repo, storage


def test_confirm_rollback_when_productive_fails(tmp_path: Path) -> None:
    pkg, confirm, package_repo, csv_repo, writer, _assets, _aisle, _inv, _storage = _seed_previewed(
        tmp_path
    )

    def boom(*_args, **_kwargs):
        raise RuntimeError("injected productive failure")

    confirm._result_writer.apply_import = boom  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="injected productive failure"):
        confirm.execute(
            inventory_id="inventory-1",
            export_id=pkg.export_id,
            confirmed_by_user_id="user-1",
        )
    again = package_repo.get_by_export_id(inventory_id="inventory-1", export_id=pkg.export_id)
    assert again is not None
    assert again.status == "PREVIEWED"
    csv = csv_repo.get_by_export_id(inventory_id="inventory-1", export_id=pkg.export_id)
    assert csv is not None
    assert csv.status == "PREVIEWED"
    assert writer.list_for_inventory("inventory-1") == ()


def test_confirm_idempotent_no_duplicate_productive(tmp_path: Path) -> None:
    pkg, confirm, _package_repo, _csv_repo, writer, assets, _aisle, _inv, _storage = _seed_previewed(
        tmp_path
    )
    first, dup1 = confirm.execute(
        inventory_id="inventory-1",
        export_id=pkg.export_id,
        confirmed_by_user_id="user-1",
    )
    assert first.status == "CONFIRMED"
    assert dup1 is False
    results1 = writer.list_for_inventory("inventory-1")
    assets1 = list(assets.list_by_aisle("aisle-1"))
    second, dup2 = confirm.execute(
        inventory_id="inventory-1",
        export_id=pkg.export_id,
        confirmed_by_user_id="user-1",
    )
    assert second.status == "CONFIRMED"
    assert dup2 is True
    assert len(writer.list_for_inventory("inventory-1")) == len(results1)
    assert len(list(assets.list_by_aisle("aisle-1"))) == len(assets1)


def test_concurrent_double_confirm_one_winner(tmp_path: Path) -> None:
    pkg, confirm, package_repo, csv_repo, writer, _assets, _aisle, _inv, _storage = _seed_previewed(
        tmp_path
    )
    results: list[tuple[str, bool]] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(2)

    def worker() -> None:
        try:
            barrier.wait(timeout=5)
            confirmed, duplicate = confirm.execute(
                inventory_id="inventory-1",
                export_id=pkg.export_id,
                confirmed_by_user_id="user-1",
            )
            results.append((confirmed.status, duplicate))
        except BaseException as exc:  # noqa: BLE001 — collect for assertion
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert errors == []
    assert len(results) == 2
    winners = [r for r in results if r[1] is False]
    idempotent = [r for r in results if r[1] is True]
    assert len(winners) == 1
    assert len(idempotent) == 1
    final = package_repo.get_by_export_id(inventory_id="inventory-1", export_id=pkg.export_id)
    assert final is not None and final.status == "CONFIRMED"
    csv = csv_repo.get_by_export_id(inventory_id="inventory-1", export_id=pkg.export_id)
    assert csv is not None and csv.status == "CONFIRMED"
    assert len(writer.list_for_inventory("inventory-1")) >= 1


def test_invalid_package_status_rejected(tmp_path: Path) -> None:
    pkg, confirm, package_repo, csv_repo, writer, assets, aisle_repo, inv_repo, storage = (
        _seed_previewed(tmp_path)
    )
    broken = replace(pkg, status="FAILED")
    package_repo._by_id[broken.id] = broken  # type: ignore[attr-defined]
    storage_before = len(storage.objects)
    assets_before = len(list(assets.list_by_aisle("aisle-1")))
    productive_before = len(writer.list_for_inventory("inventory-1"))
    clock = FixedClock()
    confirm = ConfirmLocalInventoryPackage(
        package_repo=package_repo,
        result_writer=writer,
        materializer=AisleSourceAssetMaterializer(
            aisle_repo=aisle_repo,
            asset_repo=assets,
            artifact_storage=storage,  # type: ignore[arg-type]
            status_reconciler=InventoryStatusReconciler(
                inventory_repo=inv_repo,
                aisle_repo=aisle_repo,
                clock=clock,
            ),
        ),
        aisle_repo=aisle_repo,
        clock=clock,
        enabled=True,
    )
    with pytest.raises(LocalInventoryPackageImportError) as exc:
        confirm.execute(
            inventory_id="inventory-1",
            export_id=pkg.export_id,
            confirmed_by_user_id="user-1",
        )
    assert exc.value.code == "PACKAGE_INVALID_STATUS"
    assert len(storage.objects) == storage_before
    assert len(list(assets.list_by_aisle("aisle-1"))) == assets_before
    assert len(writer.list_for_inventory("inventory-1")) == productive_before
    csv = csv_repo.get_by_export_id(inventory_id="inventory-1", export_id=pkg.export_id)
    assert csv is not None
    assert csv.status == "PREVIEWED"
    again = package_repo.get_by_export_id(inventory_id="inventory-1", export_id=pkg.export_id)
    assert again is not None
    assert again.status == "FAILED"


def test_post_commit_materialize_failure_then_retry_succeeds(tmp_path: Path) -> None:
    pkg, confirm, package_repo, _csv_repo, writer, _assets, _aisle, _inv, _storage = _seed_previewed(
        tmp_path
    )
    calls = {"count": 0}
    original_materialize = confirm._position_materializer.materialize  # type: ignore[union-attr]

    def flaky_materialize(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("post-commit materialize failure")
        return original_materialize(*args, **kwargs)

    confirm._position_materializer.materialize = flaky_materialize  # type: ignore[method-assign, union-attr]

    with pytest.raises(RuntimeError, match="post-commit materialize failure"):
        confirm.execute(
            inventory_id="inventory-1",
            export_id=pkg.export_id,
            confirmed_by_user_id="user-1",
        )

    confirmed = package_repo.get_by_export_id(inventory_id="inventory-1", export_id=pkg.export_id)
    assert confirmed is not None
    assert confirmed.status == "CONFIRMED"
    assert len(writer.list_for_inventory("inventory-1")) >= 1

    second, duplicate = confirm.execute(
        inventory_id="inventory-1",
        export_id=pkg.export_id,
        confirmed_by_user_id="user-1",
    )
    assert second.status == "CONFIRMED"
    assert duplicate is True
    assert calls["count"] >= 2
