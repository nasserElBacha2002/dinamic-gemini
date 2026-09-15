"""SQL Stage 2 corrections — tenant isolation + transactional soft-delete with cleanup."""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone

import pytest

from src.application.errors import (
    ClientNotFoundError,
    InventoryNotFoundError,
    InventorySoftDeleteConsistencyError,
)
from src.application.use_cases.clients.get_client import GetClientUseCase
from src.application.use_cases.clients.list_clients import ListClientsUseCase
from src.application.use_cases.inventories.get_inventory import GetInventoryUseCase
from src.application.use_cases.inventories.soft_delete_inventories import (
    SoftDeleteInventoriesCommand,
    SoftDeleteInventoriesUseCase,
)
from src.domain.client.entities import Client, ClientStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.infrastructure.database import sql_transaction as sql_txn_mod
from src.infrastructure.repositories.sql_client_repository import SqlClientRepository
from src.infrastructure.repositories.sql_inventory_repository import SqlInventoryRepository
from tests.support.access_principal_helpers import company_principal, platform_principal
from tests.support.sql_integration import sql_server_client_or_skip
from tests.support.sqlserver_test_connection import resolved_sqlserver_connection_string_for_tests

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def sql_client():
    return sql_server_client_or_skip(resolved_sqlserver_connection_string_for_tests())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


def _cleanup(
    sql_client,
    *,
    client_ids: list[str],
    inventory_ids: list[str],
) -> None:
    with sql_client.cursor() as cur:
        for iid in inventory_ids:
            cur.execute("DELETE FROM inventories WHERE id = ?", (iid,))
        for cid in client_ids:
            cur.execute("DELETE FROM clients WHERE id = ?", (cid,))


def _assert_gone(sql_client, *, client_ids: list[str], inventory_ids: list[str]) -> None:
    with sql_client.cursor() as cur:
        for iid in inventory_ids:
            cur.execute("SELECT COUNT(1) AS c FROM inventories WHERE id = ?", (iid,))
            assert int(cur.fetchone().c) == 0
        for cid in client_ids:
            cur.execute("SELECT COUNT(1) AS c FROM clients WHERE id = ?", (cid,))
            assert int(cur.fetchone().c) == 0


def test_sql_tenant_clients_and_inventories_scoped(sql_client) -> None:
    suffix = uuid.uuid4().hex[:10]
    client_a = f"cli-a-{suffix}"
    client_b = f"cli-b-{suffix}"
    inv_a = f"inv-a-{suffix}"
    inv_b = f"inv-b-{suffix}"
    now = _now()
    client_ids = [client_a, client_b]
    inventory_ids = [inv_a, inv_b]

    clients = SqlClientRepository(sql_client)
    inventories = SqlInventoryRepository(sql_client)
    try:
        clients.save(
            Client(
                id=client_a,
                name=f"A-{suffix}",
                status=ClientStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
        )
        clients.save(
            Client(
                id=client_b,
                name=f"B-{suffix}",
                status=ClientStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
        )
        inventories.save(
            Inventory(
                id=inv_a,
                name=f"IA-{suffix}",
                status=InventoryStatus.DRAFT,
                created_at=now,
                updated_at=now,
                client_id=client_a,
            )
        )
        inventories.save(
            Inventory(
                id=inv_b,
                name=f"IB-{suffix}",
                status=InventoryStatus.DRAFT,
                created_at=now,
                updated_at=now,
                client_id=client_b,
            )
        )

        listed_a = ListClientsUseCase(clients).execute(company_principal(client_a))
        assert [c.id for c in listed_a] == [client_a]

        assert GetClientUseCase(clients).execute(client_a, company_principal(client_a)).id == client_a
        with pytest.raises(ClientNotFoundError):
            GetClientUseCase(clients).execute(client_b, company_principal(client_a))

        scoped = inventories.list_for_client(client_a)
        assert {i.id for i in scoped} == {inv_a}

        assert GetInventoryUseCase(inventories).execute(
            inv_a, company_principal(client_a)
        ).id == inv_a
        with pytest.raises(InventoryNotFoundError):
            GetInventoryUseCase(inventories).execute(inv_b, company_principal(client_a))

        plat_clients = ListClientsUseCase(clients).execute(platform_principal())
        assert {client_a, client_b}.issubset({c.id for c in plat_clients})
    finally:
        _cleanup(sql_client, client_ids=client_ids, inventory_ids=inventory_ids)
        _assert_gone(sql_client, client_ids=client_ids, inventory_ids=inventory_ids)


def test_sql_soft_delete_mixed_ids_atomic(sql_client) -> None:
    suffix = uuid.uuid4().hex[:10]
    client_a = f"cli-a-{suffix}"
    client_b = f"cli-b-{suffix}"
    inv_a1 = f"inv-a1-{suffix}"
    inv_a2 = f"inv-a2-{suffix}"
    inv_b = f"inv-b-{suffix}"
    now = _now()
    client_ids = [client_a, client_b]
    inventory_ids = [inv_a1, inv_a2, inv_b]

    clients = SqlClientRepository(sql_client)
    inventories = SqlInventoryRepository(sql_client)
    clock = FixedClock(now)
    try:
        for cid, name in ((client_a, "A"), (client_b, "B")):
            clients.save(
                Client(
                    id=cid,
                    name=f"{name}-{suffix}",
                    status=ClientStatus.ACTIVE,
                    created_at=now,
                    updated_at=now,
                )
            )
        for iid, cid in ((inv_a1, client_a), (inv_a2, client_a), (inv_b, client_b)):
            inventories.save(
                Inventory(
                    id=iid,
                    name=iid,
                    status=InventoryStatus.DRAFT,
                    created_at=now,
                    updated_at=now,
                    client_id=cid,
                )
            )

        uc = SoftDeleteInventoriesUseCase(inventories, clock)
        mixed = uc.execute(
            SoftDeleteInventoriesCommand(
                inventory_ids=(inv_a1, inv_b),
                principal=company_principal(client_a),
            )
        )
        assert mixed.deleted_ids == ()
        assert inv_b in mixed.not_found_ids
        for iid in (inv_a1, inv_a2, inv_b):
            row = inventories.get_by_id(iid)
            assert row is not None
            assert row.deleted_at is None

        missing = uc.execute(
            SoftDeleteInventoriesCommand(
                inventory_ids=(inv_a1, "missing-" + suffix),
                principal=company_principal(client_a),
            )
        )
        assert missing.deleted_ids == ()
        assert inventories.get_by_id(inv_a1).deleted_at is None  # type: ignore[union-attr]

        ok = uc.execute(
            SoftDeleteInventoriesCommand(
                inventory_ids=(inv_a1, inv_a2),
                principal=company_principal(client_a),
            )
        )
        assert set(ok.deleted_ids) == {inv_a1, inv_a2}
        assert inventories.get_by_id(inv_a1).is_deleted  # type: ignore[union-attr]
        assert inventories.get_by_id(inv_b).deleted_at is None  # type: ignore[union-attr]

        again = uc.execute(
            SoftDeleteInventoriesCommand(
                inventory_ids=(inv_a1, inv_a2),
                principal=company_principal(client_a),
            )
        )
        assert again.deleted_ids == ()
        assert set(again.already_deleted_ids) == {inv_a1, inv_a2}
    finally:
        _cleanup(sql_client, client_ids=client_ids, inventory_ids=inventory_ids)
        _assert_gone(sql_client, client_ids=client_ids, inventory_ids=inventory_ids)


def test_sql_soft_delete_induced_failure_rolls_back(sql_client) -> None:
    """Fail during second UPDATE → standalone txn rolls back; zero durable deletes."""
    suffix = uuid.uuid4().hex[:10]
    client_a = f"cli-a-{suffix}"
    inv_1 = f"inv-1-{suffix}"
    inv_2 = f"inv-2-{suffix}"
    now = _now()
    client_ids = [client_a]
    inventory_ids = [inv_1, inv_2]

    clients = SqlClientRepository(sql_client)
    base = SqlInventoryRepository(sql_client)
    update_count = {"n": 0}
    real_cursor_cm = sql_txn_mod.sql_repository_cursor

    class _FailSecondUpdateCursor:
        def __init__(self, inner: object) -> None:
            self._inner = inner

        def execute(self, sql: str, params: object = None) -> object:
            text = (sql or "").lstrip().upper()
            if text.startswith("UPDATE"):
                update_count["n"] += 1
                if update_count["n"] == 2:
                    raise RuntimeError("induced failure on second UPDATE")
            if params is None:
                return self._inner.execute(sql)  # type: ignore[attr-defined]
            return self._inner.execute(sql, params)  # type: ignore[attr-defined]

        def fetchall(self) -> object:
            return self._inner.fetchall()  # type: ignore[attr-defined]

        def close(self) -> None:
            self._inner.close()  # type: ignore[attr-defined]

        def __getattr__(self, name: str) -> object:
            return getattr(self._inner, name)

    from contextlib import contextmanager

    @contextmanager
    def _wrapped_cursor(client, *, connection=None):  # type: ignore[no-untyped-def]
        with real_cursor_cm(client, connection=connection) as cur:
            yield _FailSecondUpdateCursor(cur)

    try:
        clients.save(
            Client(
                id=client_a,
                name=f"A-{suffix}",
                status=ClientStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
        )
        for iid in (inv_1, inv_2):
            base.save(
                Inventory(
                    id=iid,
                    name=iid,
                    status=InventoryStatus.DRAFT,
                    created_at=now,
                    updated_at=now,
                    client_id=client_a,
                )
            )

        monkey = pytest.MonkeyPatch()
        monkey.setattr(sql_txn_mod, "sql_repository_cursor", _wrapped_cursor)
        # Repo module bound the symbol at import time — patch there too.
        import src.infrastructure.repositories.sql_inventory_repository as inv_mod

        monkey.setattr(inv_mod, "sql_repository_cursor", _wrapped_cursor)
        try:
            with pytest.raises(RuntimeError, match="induced failure on second UPDATE"):
                base.soft_delete_many_for_scope(
                    [inv_1, inv_2],
                    allow_all_clients=False,
                    client_id=client_a,
                    deleted_at=now,
                    deleted_by="tester",
                )
        finally:
            monkey.undo()

        assert update_count["n"] == 2
        for iid in (inv_1, inv_2):
            row = base.get_by_id(iid)
            assert row is not None
            assert row.deleted_at is None
    finally:
        _cleanup(sql_client, client_ids=client_ids, inventory_ids=inventory_ids)
        _assert_gone(sql_client, client_ids=client_ids, inventory_ids=inventory_ids)


def test_sql_soft_delete_uow_second_update_failure_rolls_back(sql_client) -> None:
    """UoW path: exception mid-batch propagates; owner rollback leaves zero deletes."""
    suffix = uuid.uuid4().hex[:10]
    client_a = f"cli-a-{suffix}"
    inv_1 = f"inv-u1f-{suffix}"
    inv_2 = f"inv-u2f-{suffix}"
    now = _now()
    client_ids = [client_a]
    inventory_ids = [inv_1, inv_2]
    clients = SqlClientRepository(sql_client)
    standalone = SqlInventoryRepository(sql_client)
    update_count = {"n": 0}
    real_cursor_cm = sql_txn_mod.sql_repository_cursor

    class _FailSecondUpdateCursor:
        def __init__(self, inner: object) -> None:
            self._inner = inner

        def execute(self, sql: str, params: object = None) -> object:
            text = (sql or "").lstrip().upper()
            if text.startswith("UPDATE"):
                update_count["n"] += 1
                if update_count["n"] == 2:
                    raise RuntimeError("induced failure on second UPDATE")
            if params is None:
                return self._inner.execute(sql)  # type: ignore[attr-defined]
            return self._inner.execute(sql, params)  # type: ignore[attr-defined]

        def fetchall(self) -> object:
            return self._inner.fetchall()  # type: ignore[attr-defined]

        def close(self) -> None:
            self._inner.close()  # type: ignore[attr-defined]

        def __getattr__(self, name: str) -> object:
            return getattr(self._inner, name)

    from contextlib import contextmanager

    @contextmanager
    def _wrapped_cursor(client, *, connection=None):  # type: ignore[no-untyped-def]
        with real_cursor_cm(client, connection=connection) as cur:
            yield _FailSecondUpdateCursor(cur)

    try:
        clients.save(
            Client(
                id=client_a,
                name=f"A-{suffix}",
                status=ClientStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
        )
        for iid in (inv_1, inv_2):
            standalone.save(
                Inventory(
                    id=iid,
                    name=iid,
                    status=InventoryStatus.DRAFT,
                    created_at=now,
                    updated_at=now,
                    client_id=client_a,
                )
            )

        monkey = pytest.MonkeyPatch()
        import src.infrastructure.repositories.sql_inventory_repository as inv_mod

        monkey.setattr(inv_mod, "sql_repository_cursor", _wrapped_cursor)
        try:
            with sql_client.begin_transaction() as txn:
                scoped = SqlInventoryRepository(sql_client, connection=txn.connection)
                with pytest.raises(RuntimeError, match="induced failure on second UPDATE"):
                    scoped.soft_delete_many_for_scope(
                        [inv_1, inv_2],
                        allow_all_clients=False,
                        client_id=client_a,
                        deleted_at=now,
                        deleted_by="uow",
                    )
                txn.rollback()
        finally:
            monkey.undo()

        assert update_count["n"] == 2
        assert standalone.get_by_id(inv_1).deleted_at is None  # type: ignore[union-attr]
        assert standalone.get_by_id(inv_2).deleted_at is None  # type: ignore[union-attr]
    finally:
        _cleanup(sql_client, client_ids=client_ids, inventory_ids=inventory_ids)
        _assert_gone(sql_client, client_ids=client_ids, inventory_ids=inventory_ids)


def test_sql_soft_delete_empty_output_while_active_raises(sql_client) -> None:
    """First UPDATE succeeds; second has empty OUTPUT while active → raise + full rollback."""
    suffix = uuid.uuid4().hex[:10]
    client_a = f"cli-a-{suffix}"
    inv_1 = f"inv-out1-{suffix}"
    inv_2 = f"inv-out2-{suffix}"
    now = _now()
    client_ids = [client_a]
    inventory_ids = [inv_1, inv_2]
    clients = SqlClientRepository(sql_client)
    base = SqlInventoryRepository(sql_client)
    real_cursor_cm = sql_txn_mod.sql_repository_cursor
    update_n = {"n": 0}

    class _AnomalyOnSecondOutputCursor:
        def __init__(self, inner: object) -> None:
            self._inner = inner
            self._mode: str | None = None

        def execute(self, sql: str, params: object = None) -> object:
            text = (sql or "").lstrip().upper()
            if text.startswith("UPDATE") and "OUTPUT" in text:
                update_n["n"] += 1
                if update_n["n"] == 1:
                    self._mode = "real"
                    if params is None:
                        return self._inner.execute(sql)  # type: ignore[attr-defined]
                    return self._inner.execute(sql, params)  # type: ignore[attr-defined]
                # Second UPDATE: skip write; empty OUTPUT while row remains active.
                self._mode = "anomaly"
                return None
            self._mode = None
            if params is None:
                return self._inner.execute(sql)  # type: ignore[attr-defined]
            return self._inner.execute(sql, params)  # type: ignore[attr-defined]

        def fetchall(self) -> object:
            if self._mode == "anomaly":
                self._mode = None
                return []
            self._mode = None
            return self._inner.fetchall()  # type: ignore[attr-defined]

        def close(self) -> None:
            self._inner.close()  # type: ignore[attr-defined]

        def __getattr__(self, name: str) -> object:
            return getattr(self._inner, name)

    from contextlib import contextmanager

    @contextmanager
    def _wrapped_cursor(client, *, connection=None):  # type: ignore[no-untyped-def]
        with real_cursor_cm(client, connection=connection) as cur:
            yield _AnomalyOnSecondOutputCursor(cur)

    try:
        clients.save(
            Client(
                id=client_a,
                name=f"A-{suffix}",
                status=ClientStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
        )
        for iid in (inv_1, inv_2):
            base.save(
                Inventory(
                    id=iid,
                    name=iid,
                    status=InventoryStatus.DRAFT,
                    created_at=now,
                    updated_at=now,
                    client_id=client_a,
                )
            )

        monkey = pytest.MonkeyPatch()
        import src.infrastructure.repositories.sql_inventory_repository as inv_mod

        monkey.setattr(inv_mod, "sql_repository_cursor", _wrapped_cursor)
        try:
            with pytest.raises(InventorySoftDeleteConsistencyError) as ei:
                base.soft_delete_many_for_scope(
                    [inv_1, inv_2],
                    allow_all_clients=False,
                    client_id=client_a,
                    deleted_at=now,
                    deleted_by="tester",
                )
            assert ei.value.error_code == "INVENTORY_SOFT_DELETE_CONSISTENCY"
            assert inv_1 not in str(ei.value)
            assert inv_2 not in str(ei.value)
        finally:
            monkey.undo()

        assert update_n["n"] == 2
        for iid in (inv_1, inv_2):
            row = base.get_by_id(iid)
            assert row is not None
            assert row.deleted_at is None
    finally:
        _cleanup(sql_client, client_ids=client_ids, inventory_ids=inventory_ids)
        _assert_gone(sql_client, client_ids=client_ids, inventory_ids=inventory_ids)


def test_sql_soft_delete_uow_connection_path(sql_client) -> None:
    """When repo is bound to an external connection, same SQL algorithm; UoW owns commit."""
    suffix = uuid.uuid4().hex[:10]
    client_a = f"cli-a-{suffix}"
    inv_1 = f"inv-u1-{suffix}"
    inv_2 = f"inv-u2-{suffix}"
    now = _now()
    client_ids = [client_a]
    inventory_ids = [inv_1, inv_2]

    clients = SqlClientRepository(sql_client)
    standalone = SqlInventoryRepository(sql_client)
    try:
        clients.save(
            Client(
                id=client_a,
                name=f"A-{suffix}",
                status=ClientStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
        )
        for iid in (inv_1, inv_2):
            standalone.save(
                Inventory(
                    id=iid,
                    name=iid,
                    status=InventoryStatus.DRAFT,
                    created_at=now,
                    updated_at=now,
                    client_id=client_a,
                )
            )

        with sql_client.begin_transaction() as txn:
            scoped = SqlInventoryRepository(sql_client, connection=txn.connection)
            deleted, already, not_found = scoped.soft_delete_many_for_scope(
                [inv_1, inv_2],
                allow_all_clients=False,
                client_id=client_a,
                deleted_at=now,
                deleted_by="uow",
            )
            assert set(deleted) == {inv_1, inv_2}
            assert already == ()
            assert not_found == ()
            # Before commit, durable read via other connection may still see active rows
            # depending on isolation; commit then verify.
            txn.commit()

        assert standalone.get_by_id(inv_1).is_deleted  # type: ignore[union-attr]
        assert standalone.get_by_id(inv_2).is_deleted  # type: ignore[union-attr]

        # Mixed under UoW → no writes; outer rollback.
        inv_3 = f"inv-u3-{suffix}"
        inventory_ids.append(inv_3)
        standalone.save(
            Inventory(
                id=inv_3,
                name=inv_3,
                status=InventoryStatus.DRAFT,
                created_at=now,
                updated_at=now,
                client_id=client_a,
            )
        )
        with sql_client.begin_transaction() as txn:
            scoped = SqlInventoryRepository(sql_client, connection=txn.connection)
            _d, _a, nf = scoped.soft_delete_many_for_scope(
                [inv_3, "missing-" + suffix],
                allow_all_clients=False,
                client_id=client_a,
                deleted_at=now,
                deleted_by="uow",
            )
            assert nf
            txn.rollback()
        assert standalone.get_by_id(inv_3).deleted_at is None  # type: ignore[union-attr]
    finally:
        _cleanup(sql_client, client_ids=client_ids, inventory_ids=inventory_ids)
        _assert_gone(sql_client, client_ids=client_ids, inventory_ids=inventory_ids)


def test_sql_soft_delete_concurrent_overlapping(sql_client) -> None:
    suffix = uuid.uuid4().hex[:10]
    client_a = f"cli-a-{suffix}"
    inv_x = f"inv-x-{suffix}"
    inv_y = f"inv-y-{suffix}"
    now = _now()
    client_ids = [client_a]
    inventory_ids = [inv_x, inv_y]
    clients = SqlClientRepository(sql_client)
    inventories = SqlInventoryRepository(sql_client)
    errors: list[BaseException] = []
    results: list[tuple] = []

    try:
        clients.save(
            Client(
                id=client_a,
                name=f"A-{suffix}",
                status=ClientStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
        )
        for iid in (inv_x, inv_y):
            inventories.save(
                Inventory(
                    id=iid,
                    name=iid,
                    status=InventoryStatus.DRAFT,
                    created_at=now,
                    updated_at=now,
                    client_id=client_a,
                )
            )

        barrier = threading.Barrier(2)

        def worker(ids: tuple[str, ...]) -> None:
            try:
                barrier.wait(timeout=10)
                repo = SqlInventoryRepository(sql_client)
                results.append(
                    repo.soft_delete_many_for_scope(
                        list(ids),
                        allow_all_clients=False,
                        client_id=client_a,
                        deleted_at=now,
                        deleted_by="t",
                    )
                )
            except BaseException as exc:  # noqa: BLE001 — capture for assertion
                errors.append(exc)

        t1 = threading.Thread(target=worker, args=((inv_x, inv_y),))
        t2 = threading.Thread(target=worker, args=((inv_x, inv_y),))
        t1.start()
        t2.start()
        t1.join(timeout=30)
        t2.join(timeout=30)
        assert not errors, errors
        assert len(results) == 2
        # Exactly one thread should report both as deleted; the other already_deleted or mix.
        deleted_sets = [set(r[0]) for r in results]
        already_sets = [set(r[1]) for r in results]
        assert {inv_x, inv_y} == deleted_sets[0] | deleted_sets[1] | already_sets[0] | already_sets[1]
        assert inventories.get_by_id(inv_x).is_deleted  # type: ignore[union-attr]
        assert inventories.get_by_id(inv_y).is_deleted  # type: ignore[union-attr]
    finally:
        _cleanup(sql_client, client_ids=client_ids, inventory_ids=inventory_ids)
        _assert_gone(sql_client, client_ids=client_ids, inventory_ids=inventory_ids)
