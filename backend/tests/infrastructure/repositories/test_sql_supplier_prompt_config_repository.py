"""Integration tests for SqlSupplierPromptConfigRepository — Phase D2."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest

from src.database.sqlserver import now_utc
from src.domain.client.entities import Client, ClientStatus
from src.domain.client_supplier.entities import ClientSupplier, ClientSupplierStatus
from src.domain.client_supplier.prompt_config import SupplierPromptConfig
from src.infrastructure.repositories.sql_client_repository import SqlClientRepository
from src.infrastructure.repositories.sql_client_supplier_repository import (
    SqlClientSupplierRepository,
)
from src.infrastructure.repositories.sql_supplier_prompt_config_repository import (
    SqlSupplierPromptConfigRepository,
)
from tests.support.sql_integration import sql_server_client_or_skip
from tests.support.sqlserver_test_connection import resolved_sqlserver_connection_string_for_tests

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def sql_client():
    return sql_server_client_or_skip(resolved_sqlserver_connection_string_for_tests())


@pytest.fixture
def repos(sql_client):
    return (
        SqlClientRepository(sql_client),
        SqlClientSupplierRepository(sql_client),
        SqlSupplierPromptConfigRepository(sql_client),
    )


def _ensure_supplier(
    client_repo: SqlClientRepository,
    supplier_repo: SqlClientSupplierRepository,
) -> tuple[str, str]:
    client_id = f"test-client-d2-{uuid4()}"
    supplier_id = f"test-supplier-d2-{uuid4()}"
    now = now_utc()
    client_repo.save(
        Client(
            id=client_id,
            name=f"Client {client_id}",
            status=ClientStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )
    supplier_repo.save(
        ClientSupplier(
            id=supplier_id,
            client_id=client_id,
            name=f"Supplier {supplier_id}",
            status=ClientSupplierStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )
    return client_id, supplier_id


def _cfg(
    *,
    config_id: str,
    supplier_id: str,
    provider: str,
    model: str | None,
    version: int,
    active: bool,
    created_at: datetime,
) -> SupplierPromptConfig:
    return SupplierPromptConfig(
        id=config_id,
        client_supplier_id=supplier_id,
        provider_name=provider,
        model_name=model,
        instructions_text=f"instructions {config_id}",
        version=version,
        is_active=active,
        created_at=created_at,
        updated_at=created_at,
    )


def test_sql_supplier_prompt_config_repository_scope_and_activation(repos) -> None:
    client_repo, supplier_repo, prompt_repo = repos
    _, supplier_id = _ensure_supplier(client_repo, supplier_repo)
    now = now_utc()

    cfg_default_v1 = _cfg(
        config_id=f"cfg-default-v1-{uuid4()}",
        supplier_id=supplier_id,
        provider="gemini",
        model=None,
        version=1,
        active=True,
        created_at=now,
    )
    cfg_default_v2 = _cfg(
        config_id=f"cfg-default-v2-{uuid4()}",
        supplier_id=supplier_id,
        provider="gemini",
        model=None,
        version=2,
        active=False,
        created_at=now_utc(),
    )
    cfg_model_v1 = _cfg(
        config_id=f"cfg-model-v1-{uuid4()}",
        supplier_id=supplier_id,
        provider="gemini",
        model="gemini-2.0-flash-exp",
        version=1,
        active=True,
        created_at=now_utc(),
    )
    prompt_repo.create(cfg_default_v1)
    prompt_repo.create(cfg_default_v2)
    prompt_repo.create(cfg_model_v1)

    loaded = prompt_repo.get_by_id(cfg_default_v1.id)
    assert loaded is not None
    assert loaded.model_name is None
    assert loaded.provider_name == "gemini"

    versions_default = prompt_repo.list_versions_by_scope(supplier_id, "gemini", None)
    assert [row.version for row in versions_default][:2] == [2, 1]
    assert prompt_repo.get_latest_version_number(supplier_id, "gemini", None) == 2

    active_default = prompt_repo.get_active_by_scope(supplier_id, "gemini", None)
    active_model = prompt_repo.get_active_by_scope(
        supplier_id, "gemini", "gemini-2.0-flash-exp"
    )
    assert active_default is not None and active_default.id == cfg_default_v1.id
    assert active_model is not None and active_model.id == cfg_model_v1.id

    prompt_repo.deactivate_scope(supplier_id, "gemini", None)
    assert prompt_repo.get_active_by_scope(supplier_id, "gemini", None) is None
    # model-specific scope remains untouched
    assert (
        prompt_repo.get_active_by_scope(supplier_id, "gemini", "gemini-2.0-flash-exp")
        is not None
    )

    activated = prompt_repo.activate_version(cfg_default_v2.id)
    assert activated is not None and activated.id == cfg_default_v2.id
    active_default_after = prompt_repo.get_active_by_scope(supplier_id, "gemini", None)
    assert active_default_after is not None and active_default_after.id == cfg_default_v2.id

    rows = prompt_repo.list_by_supplier(supplier_id)
    ids = [row.id for row in rows]
    assert cfg_default_v2.id in ids
    assert cfg_default_v1.id in ids
    assert cfg_model_v1.id in ids
