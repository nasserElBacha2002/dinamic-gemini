"""Mobile builder ↔ backend parser contract (versioned fixture)."""

from __future__ import annotations

from src.application.services.local_csv_parser import parse_local_csv
from src.domain.local_csv_import.sources import INGESTION_SOURCE_LOCAL_CSV_IMPORT
from tests.fixtures.local_csv_mobile_contract_v1 import MOBILE_CSV_CONTRACT_V1


def test_mobile_contract_csv_is_accepted_by_backend_parser() -> None:
    parsed = parse_local_csv(MOBILE_CSV_CONTRACT_V1)

    assert parsed.export_id == "export-contract-1"
    assert parsed.inventory_id == "inventory-1"
    assert len(parsed.rows) == 1
    row = parsed.rows[0]
    assert row.detection_source == "LOCAL_CODE_SCAN"
    assert row.ingestion_source == INGESTION_SOURCE_LOCAL_CSV_IMPORT
    assert row.quantity == 7
    assert row.errors == ()
