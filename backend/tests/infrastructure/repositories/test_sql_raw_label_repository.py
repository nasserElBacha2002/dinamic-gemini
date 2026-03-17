"""
Integration tests for SqlRawLabelRepository — v3.2.3.

Runs against a real SQL Server when SQLSERVER_CONNECTION_STRING (or equivalent env) is set.
Skips when DB is not configured. Requires v3 schema to be applied (raw_labels table).
"""

from __future__ import annotations

import os
import pytest

from src.database.sqlserver import SqlServerClient, now_utc
from src.domain.labels.entities import RawLabel
from src.infrastructure.repositories.sql_raw_label_repository import SqlRawLabelRepository


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
    cs = _connection_string()
    if not cs:
        pytest.skip("SQL Server not configured (set SQLSERVER_CONNECTION_STRING or server/database/uid/pwd)")
    return SqlServerClient(cs)


@pytest.fixture
def repo(sql_client):
    return SqlRawLabelRepository(sql_client)


def test_sql_raw_label_repository_save_and_list_for_scope(repo: SqlRawLabelRepository) -> None:
    now = now_utc()
    labels = [
        RawLabel(
            id="test-raw-001",
            inventory_id="inv-test",
            aisle_id="aisle-test",
            position_id="pos-test",
            evidence_id="ev-test",
            group_key="position:pos-test:evidence:ev-test",
            provider="pipeline",
            source_type="hybrid_report",
            source_reference="entity-1",
            sku_raw="SKU-1",
            sku_candidate="SKU-1",
            product_name_raw="Name",
            detected_text="SKU-1",
            confidence=0.9,
            metadata={"k": "v"},
            created_at=now,
        )
    ]
    repo.save_many(labels)
    loaded = list(repo.list_for_scope("inv-test", "aisle-test"))
    ids = [l.id for l in loaded]
    assert "test-raw-001" in ids

