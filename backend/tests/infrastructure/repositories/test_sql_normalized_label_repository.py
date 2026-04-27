"""
Integration tests for SqlNormalizedLabelRepository — v3.2.3.

Runs against a real SQL Server when SQLSERVER_CONNECTION_STRING (or equivalent env) is set.
Skips when DB is not configured. Requires v3 schema to be applied (normalized_labels table).
"""

from __future__ import annotations

import os
import pytest

from src.database.sqlserver import now_utc
from src.domain.labels.entities import NormalizedLabel
from src.infrastructure.repositories.sql_normalized_label_repository import SqlNormalizedLabelRepository
from tests.support.sql_integration import sql_server_client_or_skip

pytestmark = pytest.mark.integration


def _connection_string() -> str:
    raw = (os.getenv("SQLSERVER_CONNECTION_STRING") or "").strip()
    if raw:
        return raw
    server = (os.getenv("SQLSERVER_SERVER") or "").strip()
    database = (os.getenv("SQLSERVER_DATABASE") or "").strip()
    uid = (os.getenv("SQLSERVER_UID") or "").strip()
    pwd = (os.getenv("SQLSERVER_PWD") or "").strip()
    if server and database and uid and pwd:
        driver = (os.getenv("SQLSERVER_DRIVER") or "").strip()
        if not driver:
            try:
                import pyodbc

                for d in pyodbc.drivers():
                    if "SQL Server" in d:
                        driver = d
                        break
            except Exception:
                pass
        if driver:
            return f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};UID={uid};PWD={pwd};TrustServerCertificate=yes"
    return ""


@pytest.fixture(scope="module")
def sql_client():
    return sql_server_client_or_skip(_connection_string())


@pytest.fixture
def repo(sql_client):
    return SqlNormalizedLabelRepository(sql_client)


def test_sql_normalized_label_repository_save_list_and_replace_for_scope(repo: SqlNormalizedLabelRepository) -> None:
    now = now_utc()
    inv_id = "inv-test"
    aisle_id = "aisle-test"

    repo.replace_for_scope(inv_id, aisle_id)

    labels = [
        NormalizedLabel(
            id="test-norm-001",
            inventory_id=inv_id,
            aisle_id=aisle_id,
            position_id="pos-test",
            group_key="position:pos-test:evidence:ev-test",
            canonical_sku="SKU-1",
            canonical_product_name="Name",
            raw_label_ids=["raw-1", "raw-2"],
            merge_rule_applied="same_sku_same_group",
            merge_confidence=0.9,
            merge_reason="test",
            review_required=False,
            metadata={"raw_count": 2},
            created_at=now,
        )
    ]
    repo.save_many(labels)
    loaded = list(repo.list_for_scope(inv_id, aisle_id))
    assert any(l.id == "test-norm-001" for l in loaded)

    repo.replace_for_scope(inv_id, aisle_id)
    loaded2 = list(repo.list_for_scope(inv_id, aisle_id))
    assert all(l.id != "test-norm-001" for l in loaded2)

