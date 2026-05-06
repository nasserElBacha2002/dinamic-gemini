"""
Integration tests for SqlRawLabelRepository — v3.2.3.

Runs against a real SQL Server when SQLSERVER_CONNECTION_STRING (or equivalent env) is set.
Skips when DB is not configured. Requires v3 schema to be applied (raw_labels table).
"""

from __future__ import annotations

import pytest

from src.database.sqlserver import now_utc
from src.domain.labels.entities import RawLabel
from src.infrastructure.repositories.sql_raw_label_repository import SqlRawLabelRepository
from tests.support.sql_integration import sql_server_client_or_skip
from tests.support.sqlserver_test_connection import resolved_sqlserver_connection_string_for_tests

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def sql_client():
    return sql_server_client_or_skip(resolved_sqlserver_connection_string_for_tests())


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
    ids = [label.id for label in loaded]
    assert "test-raw-001" in ids
