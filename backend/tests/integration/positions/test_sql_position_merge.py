"""SQL integration for operator position merge (requires SQL Server + migration 0097)."""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.application.dto.access_principal import AccessPrincipal
from src.application.errors import PositionMergeStalePreviewError
from src.application.services.aisle_review_lifecycle_sync import AisleReviewLifecycleSync
from src.application.services.inventory_access_policy import InventoryAccessPolicy
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.use_cases.positions.merge_positions import (
    ConfirmMergePositionsUseCase,
    PreviewMergePositionsUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.positions.entities import Position, PositionStatus
from src.domain.products.entities import ProductRecord
from src.infrastructure.persistence.sql_position_merge_unit_of_work import (
    build_sql_position_merge_uow_factory,
)
from src.infrastructure.repositories.sql_aisle_repository import SqlAisleRepository
from src.infrastructure.repositories.sql_inventory_repository import SqlInventoryRepository
from src.infrastructure.repositories.sql_position_repository import SqlPositionRepository
from src.infrastructure.repositories.sql_product_record_repository import SqlProductRecordRepository
from src.infrastructure.repositories.sql_review_action_repository import SqlReviewActionRepository
from tests.support.sql_integration import sql_server_client_or_skip
from tests.support.sqlserver_test_connection import resolved_sqlserver_connection_string_for_tests

pytestmark = pytest.mark.integration

_MIGRATION_DIR = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "database"
    / "migrations"
    / "versions"
)


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


@pytest.fixture(scope="module")
def sql_client():
    return sql_server_client_or_skip(resolved_sqlserver_connection_string_for_tests())


def _exec_migration_batches(sql_client, path: Path) -> None:
    import re

    text = path.read_text(encoding="utf-8")
    batches = [b.strip() for b in re.split(r"(?im)^\s*GO\s*$", text) if b.strip()]
    with sql_client.cursor() as cur:
        for batch in batches:
            cur.execute(batch)


@pytest.fixture(scope="module")
def _require_merge_columns(sql_client):
    """Ensure soft-delete (0096) + merge (0097) columns exist on the IT database."""
    soft = _MIGRATION_DIR / "0096_inventories_soft_delete.sql"
    up = _MIGRATION_DIR / "0097_positions_merge.sql"
    with sql_client.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM sys.columns
            WHERE object_id = OBJECT_ID(N'dbo.inventories')
              AND name = N'deleted_at'
            """
        )
        need_soft = cur.fetchone() is None
        cur.execute(
            """
            SELECT 1 FROM sys.columns
            WHERE object_id = OBJECT_ID(N'dbo.positions')
              AND name = N'merged_into_position_id'
            """
        )
        need_merge = cur.fetchone() is None
    if need_soft:
        if not soft.exists():
            pytest.skip("inventories.deleted_at missing; apply migration 0096")
        _exec_migration_batches(sql_client, soft)
    if need_merge:
        if not up.exists():
            pytest.skip("positions.merged_into_position_id missing; apply migration 0097")
        _exec_migration_batches(sql_client, up)


def _platform() -> AccessPrincipal:
    return AccessPrincipal(
        actor_id="sql-merge-admin",
        client_id=None,
        roles=frozenset({"platform_admin"}),
        is_platform=True,
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _seed(sql_client, *, qtys: tuple[int, ...] = (4, 3)) -> tuple[str, str, list[str], FixedClock]:
    now = _now()
    inv_id = str(uuid.uuid4())
    aisle_id = str(uuid.uuid4())
    inv_repo = SqlInventoryRepository(sql_client)
    aisle_repo = SqlAisleRepository(sql_client)
    pos_repo = SqlPositionRepository(sql_client)
    prod_repo = SqlProductRecordRepository(sql_client)
    inv_repo.save(
        Inventory(inv_id, "Merge IT", InventoryStatus.DRAFT, now, now)
    )
    aisle_repo.save(Aisle(aisle_id, inv_id, f"M{inv_id[:6]}", AisleStatus.PROCESSED, now, now))
    ids: list[str] = []
    for i, qty in enumerate(qtys):
        pid = str(uuid.uuid4())
        ids.append(pid)
        created = now
        pos_repo.save(
            Position(
                id=pid,
                aisle_id=aisle_id,
                status=PositionStatus.DETECTED,
                confidence=0.9,
                needs_review=True,
                primary_evidence_id=None,
                created_at=created,
                updated_at=created,
                detected_summary_json={
                    "internal_code": "SKU-MERGE",
                    "final_quantity": qty,
                },
            )
        )
        prod_repo.save(
            ProductRecord(
                id=str(uuid.uuid4()),
                position_id=pid,
                sku="SKU-MERGE",
                detected_quantity=qty,
                confidence=0.9,
                created_at=created,
                updated_at=created,
            )
        )
    return inv_id, aisle_id, ids, FixedClock(now)


def _ucs(sql_client, clock: FixedClock, *, with_uow: bool = True):
    inv_repo = SqlInventoryRepository(sql_client)
    aisle_repo = SqlAisleRepository(sql_client)
    pos_repo = SqlPositionRepository(sql_client)
    prod_repo = SqlProductRecordRepository(sql_client)
    review_repo = SqlReviewActionRepository(sql_client)
    access = InventoryAccessPolicy(inv_repo, aisle_repo=aisle_repo)
    sync = AisleReviewLifecycleSync(
        aisle_repo,
        pos_repo,
        clock,
        InventoryStatusReconciler(inv_repo, aisle_repo, clock),
    )
    preview = PreviewMergePositionsUseCase(
        access_policy=access,
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        position_repo=pos_repo,
        product_record_repo=prod_repo,
    )
    confirm = ConfirmMergePositionsUseCase(
        access_policy=access,
        inventory_repo=inv_repo,
        aisle_repo=aisle_repo,
        position_repo=pos_repo,
        product_record_repo=prod_repo,
        review_repo=review_repo,
        clock=clock,
        aisle_review_sync=sync,
        uow_factory=build_sql_position_merge_uow_factory(sql_client, clock) if with_uow else None,
    )
    return preview, confirm, pos_repo, review_repo


def test_sql_merge_persists_survivor_and_sources(sql_client, _require_merge_columns) -> None:
    inv_id, aisle_id, ids, clock = _seed(sql_client)
    preview, confirm, pos_repo, review_repo = _ucs(sql_client, clock)
    pre = preview.execute(
        inventory_id=inv_id, aisle_id=aisle_id, result_ids=ids, principal=_platform()
    )
    assert pre.can_merge is True
    assert pre.merged_quantity == 7
    out = confirm.execute(
        inventory_id=inv_id,
        aisle_id=aisle_id,
        result_ids=ids,
        preview_token=pre.preview_token,
        principal=_platform(),
    )
    survivor = pos_repo.get_by_id(out.survivor_id)
    source = pos_repo.get_by_id([i for i in ids if i != out.survivor_id][0])
    assert survivor is not None
    assert survivor.detected_summary_json is not None
    assert survivor.detected_summary_json.get("final_quantity") == 7
    assert source is not None
    assert source.merged_into_position_id == out.survivor_id
    assert source.merged_at is not None
    listed = pos_repo.list_by_aisle(aisle_id, page_size=50)
    assert [p.id for p in listed] == [out.survivor_id]
    actions = review_repo.list_by_position(out.survivor_id)
    assert any(a.user_id == "sql-merge-admin" for a in actions)


def test_sql_stale_product_quantity(sql_client, _require_merge_columns) -> None:
    inv_id, aisle_id, ids, clock = _seed(sql_client, qtys=(4, 3))
    preview, confirm, _, _ = _ucs(sql_client, clock)
    prod_repo = SqlProductRecordRepository(sql_client)
    pre = preview.execute(
        inventory_id=inv_id, aisle_id=aisle_id, result_ids=ids, principal=_platform()
    )
    products = list(prod_repo.list_by_position_ids(ids))
    assert products
    target = sorted(products, key=lambda p: p.created_at)[-1]
    target.corrected_quantity = 9
    target.updated_at = _now()
    prod_repo.save(target)
    with pytest.raises(PositionMergeStalePreviewError):
        confirm.execute(
            inventory_id=inv_id,
            aisle_id=aisle_id,
            result_ids=ids,
            preview_token=pre.preview_token,
            principal=_platform(),
        )


def test_sql_concurrent_same_set(sql_client, _require_merge_columns) -> None:
    inv_id, aisle_id, ids, clock = _seed(sql_client, qtys=(2, 2))
    preview, confirm, pos_repo, _ = _ucs(sql_client, clock)
    pre = preview.execute(
        inventory_id=inv_id, aisle_id=aisle_id, result_ids=ids, principal=_platform()
    )
    results: list[object] = []
    errors: list[BaseException] = []

    def _run() -> None:
        try:
            results.append(
                confirm.execute(
                    inventory_id=inv_id,
                    aisle_id=aisle_id,
                    result_ids=ids,
                    preview_token=pre.preview_token,
                    principal=_platform(),
                )
            )
        except BaseException as exc:  # noqa: BLE001 — collect for assertion
            errors.append(exc)

    t1 = threading.Thread(target=_run)
    t2 = threading.Thread(target=_run)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    successes = [r for r in results if getattr(r, "survivor_id", None)]
    assert len(successes) >= 1
    # One success + optional idempotent/stale/conflict — never two distinct survivors.
    survivors = {getattr(r, "survivor_id") for r in successes}
    assert len(survivors) == 1
    sources = [p for p in pos_repo.list_all_by_aisles([aisle_id]) if p.is_merged_source]
    assert len(sources) == 1
    assert all(s.merged_into_position_id == next(iter(survivors)) for s in sources)


def test_sql_concurrent_overlapping_sets(sql_client, _require_merge_columns) -> None:
    """Tx A [P1,P2] vs Tx B [P2,P3] must not corrupt merge pointers or double-count operationally."""
    from src.application.errors import PositionMergeConflictError, PositionMergeStalePreviewError

    inv_id, aisle_id, ids, clock = _seed(sql_client, qtys=(2, 2, 2))
    preview, confirm, pos_repo, _ = _ucs(sql_client, clock)
    set_a, set_b = ids[:2], ids[1:]
    pre_a = preview.execute(
        inventory_id=inv_id, aisle_id=aisle_id, result_ids=set_a, principal=_platform()
    )
    pre_b = preview.execute(
        inventory_id=inv_id, aisle_id=aisle_id, result_ids=set_b, principal=_platform()
    )
    results: list[object] = []
    errors: list[BaseException] = []

    def _run(result_ids: list[str], token: str) -> None:
        try:
            results.append(
                confirm.execute(
                    inventory_id=inv_id,
                    aisle_id=aisle_id,
                    result_ids=result_ids,
                    preview_token=token,
                    principal=_platform(),
                )
            )
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    t1 = threading.Thread(target=_run, args=(set_a, pre_a.preview_token))
    t2 = threading.Thread(target=_run, args=(set_b, pre_b.preview_token))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert len(results) + len(errors) == 2
    assert len(results) >= 1
    assert all(
        isinstance(e, (PositionMergeConflictError, PositionMergeStalePreviewError)) for e in errors
    )
    all_rows = list(pos_repo.list_all_by_aisles([aisle_id]))
    by_id = {p.id: p for p in all_rows}
    operational = list(pos_repo.list_by_aisles([aisle_id]))
    # One merge wins → 2 operational (survivor + untouched); both serialize → 1 operational.
    assert len(operational) in (1, 2)
    assert len(results) == 1 or len(operational) == 1

    def _ultimate(pid: str) -> str:
        seen: set[str] = set()
        cur = pid
        while True:
            row = by_id[cur]
            if not row.is_merged_source:
                return cur
            nxt = (row.merged_into_position_id or "").strip()
            assert nxt and nxt not in seen and nxt != cur
            seen.add(cur)
            cur = nxt

    for p in all_rows:
        if p.is_merged_source:
            assert p.id != p.merged_into_position_id
            assert _ultimate(p.id) in {o.id for o in operational}

    op_qty = 0
    for p in operational:
        summary = p.detected_summary_json if isinstance(p.detected_summary_json, dict) else {}
        raw = summary.get("final_quantity")
        assert isinstance(raw, int)
        op_qty += raw
    assert op_qty == 6


def test_sql_rollback_on_review_failure(sql_client, _require_merge_columns, monkeypatch) -> None:
    """Exception after writes must leave positions/products unchanged (TX rollback)."""
    from src.infrastructure.repositories import sql_review_action_repository as review_mod

    inv_id, aisle_id, ids, clock = _seed(sql_client, qtys=(5, 1))
    preview, confirm, pos_repo, _ = _ucs(sql_client, clock)
    pre = preview.execute(
        inventory_id=inv_id, aisle_id=aisle_id, result_ids=ids, principal=_platform()
    )
    before = {p.id: (p.merged_into_position_id, p.updated_at) for p in pos_repo.get_by_ids(ids)}

    original_save = review_mod.SqlReviewActionRepository.save

    def _boom(self, review):  # noqa: ANN001
        raise RuntimeError("forced review failure")

    monkeypatch.setattr(review_mod.SqlReviewActionRepository, "save", _boom)
    with pytest.raises(RuntimeError, match="forced review failure"):
        confirm.execute(
            inventory_id=inv_id,
            aisle_id=aisle_id,
            result_ids=ids,
            preview_token=pre.preview_token,
            principal=_platform(),
        )
    monkeypatch.setattr(review_mod.SqlReviewActionRepository, "save", original_save)
    after = {p.id: (p.merged_into_position_id, p.updated_at) for p in pos_repo.get_by_ids(ids)}
    assert after == before
    assert all(mid is None for mid, _ in after.values())


def test_sql_migration_0097_up_down_up(sql_client) -> None:
    """Apply 0097 up → down → up and verify columns/FK/check/index."""
    import re

    up = _MIGRATION_DIR / "0097_positions_merge.sql"
    down = _MIGRATION_DIR / "0097_positions_merge.down.sql"
    if not up.exists() or not down.exists():
        pytest.skip("0097 migration files missing")

    def _exec_batches(path: Path) -> None:
        text = path.read_text(encoding="utf-8")
        batches = [b.strip() for b in re.split(r"(?im)^\s*GO\s*$", text) if b.strip()]
        with sql_client.cursor() as cur:
            for batch in batches:
                cur.execute(batch)

    _exec_batches(up)
    with sql_client.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM sys.columns
            WHERE object_id = OBJECT_ID(N'dbo.positions') AND name = N'merged_into_position_id'
            """
        )
        assert cur.fetchone() is not None
    _exec_batches(down)
    with sql_client.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM sys.columns
            WHERE object_id = OBJECT_ID(N'dbo.positions') AND name = N'merged_into_position_id'
            """
        )
        assert cur.fetchone() is None
    _exec_batches(up)
    with sql_client.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM sys.check_constraints
            WHERE name = N'CK_positions_merged_into_not_self'
            """
        )
        assert cur.fetchone() is not None
        cur.execute(
            """
            SELECT 1 FROM sys.foreign_keys
            WHERE name = N'FK_positions_merged_into'
            """
        )
        assert cur.fetchone() is not None
        cur.execute(
            """
            SELECT 1 FROM sys.indexes
            WHERE object_id = OBJECT_ID(N'dbo.positions')
              AND name = N'IX_positions_merged_into'
            """
        )
        assert cur.fetchone() is not None
