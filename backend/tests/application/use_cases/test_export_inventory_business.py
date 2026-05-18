"""Additive business export use cases (summary, package, business aisle CSV)."""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import datetime, timezone

import pytest

from src.application.errors import InventoryNotFoundError
from src.application.services.csv_inventory_exporter import UTF8_BOM
from src.application.services.export_csv_column_mapper import BUSINESS_OPERATIONAL_CSV_FIELDS
from src.application.services.export_inventory_collector import ExportInventoryCollector
from src.application.services.result_context_resolver import ResultContextResolver
from src.application.use_cases.export_inventory_business import (
    ExportAisleBusinessCsvUseCase,
    ExportInventoryPackageZipUseCase,
    ExportInventorySummaryCsvUseCase,
    build_business_aisle_operational_csv_from_bundle,
)
from src.application.use_cases.export_inventory_results import ExportAisleResultsCsvUseCase
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.positions.entities import Position, PositionStatus
from src.domain.traceability import TraceabilityStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.repositories.memory_product_record_repository import (
    MemoryProductRecordRepository,
)

NOW = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)


def _parse_csv(text: str) -> tuple[list[str], list[dict[str, str]]]:
    if text.startswith(UTF8_BOM):
        text = text[len(UTF8_BOM) :]
    reader = csv.DictReader(io.StringIO(text))
    assert reader.fieldnames is not None
    return list(reader.fieldnames), list(reader)


def _repos_with_positions(
    *,
    inv: Inventory,
    aisles: list[Aisle],
    positions: list[Position],
) -> tuple[
    MemoryInventoryRepository,
    MemoryAisleRepository,
    MemoryPositionRepository,
    MemoryProductRecordRepository,
    MemoryJobRepository,
]:
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    pos_repo = MemoryPositionRepository()
    prod_repo = MemoryProductRecordRepository()
    job_repo = MemoryJobRepository()
    inv_repo.save(inv)
    for a in aisles:
        aisle_repo.save(a)
    for p in positions:
        pos_repo.save(p)
    return inv_repo, aisle_repo, pos_repo, prod_repo, job_repo


def test_inventory_summary_one_row_and_readable_filename() -> None:
    inv = Inventory("inv-1", "Warehouse", InventoryStatus.PROCESSING, NOW, NOW)
    aisle = Aisle("a1", "inv-1", "A1", AisleStatus.COMPLETED, NOW, NOW)
    pos = Position(
        id="p1",
        aisle_id="a1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id=None,
        created_at=NOW,
        updated_at=NOW,
        detected_summary_json={
            "internal_code": "SKU-A",
            "final_quantity": 3,
            "traceability_status": "valid",
        },
    )
    inv_repo, aisle_repo, pos_repo, prod_repo, job_repo = _repos_with_positions(
        inv=inv, aisles=[aisle], positions=[pos]
    )
    uc = ExportInventorySummaryCsvUseCase(
        inv_repo,
        aisle_repo,
        pos_repo,
        prod_repo,
        ResultContextResolver(job_repo),
        job_repo=job_repo,
    )
    csv_text, filename = uc.execute_inventory_summary_csv("inv-1")
    headers, rows = _parse_csv(csv_text)
    assert headers[0] == "Inventario"
    assert len(rows) == 1
    assert rows[0]["Total contabilizado"] == "3"
    assert rows[0]["Costo total del inventario"] == ""
    assert "Warehouse" in filename
    assert filename.endswith("_summary.csv")


def test_aisles_summary_one_row_per_aisle() -> None:
    inv = Inventory("inv-1", "Warehouse", InventoryStatus.PROCESSING, NOW, NOW)
    aisles = [
        Aisle("a1", "inv-1", "A1", AisleStatus.COMPLETED, NOW, NOW),
        Aisle("a2", "inv-1", "A2", AisleStatus.COMPLETED, NOW, NOW),
    ]
    positions = [
        Position(
            id="p-a1",
            aisle_id="a1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=NOW,
            updated_at=NOW,
            detected_summary_json={"internal_code": "SKU-A1", "final_quantity": 1},
        ),
        Position(
            id="p-a2",
            aisle_id="a2",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=NOW,
            updated_at=NOW,
            detected_summary_json={"internal_code": "SKU-A2", "final_quantity": 1},
        ),
    ]
    inv_repo, aisle_repo, pos_repo, prod_repo, job_repo = _repos_with_positions(
        inv=inv, aisles=aisles, positions=positions
    )
    uc = ExportInventorySummaryCsvUseCase(
        inv_repo,
        aisle_repo,
        pos_repo,
        prod_repo,
        ResultContextResolver(job_repo),
        job_repo=job_repo,
    )
    _, filename = uc.execute_aisles_summary_csv("inv-1")
    _, rows = _parse_csv(uc.execute_aisles_summary_csv("inv-1")[0])
    assert len(rows) == 2
    assert {r["Pasillo"] for r in rows} == {"A1", "A2"}
    assert "Warehouse" in filename
    assert filename.endswith("_aisles_summary.csv")


def test_business_aisle_csv_cost_columns_empty() -> None:
    inv = Inventory("inv-1", "Warehouse", InventoryStatus.PROCESSING, NOW, NOW)
    aisle = Aisle("a1", "inv-1", "A1", AisleStatus.COMPLETED, NOW, NOW)
    pos = Position(
        id="p1",
        aisle_id="a1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id=None,
        created_at=NOW,
        updated_at=NOW,
        detected_summary_json={"internal_code": "SKU", "final_quantity": 2},
    )
    inv_repo, aisle_repo, pos_repo, prod_repo, job_repo = _repos_with_positions(
        inv=inv, aisles=[aisle], positions=[pos]
    )
    uc = ExportAisleBusinessCsvUseCase(
        inv_repo,
        aisle_repo,
        pos_repo,
        prod_repo,
        ResultContextResolver(job_repo),
    )
    body, _ = uc.execute_csv("inv-1", "a1")
    _, rows = _parse_csv(body)
    assert rows[0]["Costo unitario"] == ""
    assert rows[0]["Costo total de línea"] == ""


def test_deleted_row_in_business_csv_excluded_from_summary_totals() -> None:
    inv = Inventory("inv-1", "Warehouse", InventoryStatus.PROCESSING, NOW, NOW)
    aisle = Aisle("a1", "inv-1", "A1", AisleStatus.COMPLETED, NOW, NOW)
    deleted = Position(
        id="p-del",
        aisle_id="a1",
        status=PositionStatus.DELETED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id=None,
        created_at=NOW,
        updated_at=NOW,
        detected_summary_json={"internal_code": "DEL", "final_quantity": 99},
    )
    active = Position(
        id="p-ok",
        aisle_id="a1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id=None,
        created_at=NOW,
        updated_at=NOW,
        detected_summary_json={"internal_code": "OK", "final_quantity": 2},
    )
    inv_repo, aisle_repo, pos_repo, prod_repo, job_repo = _repos_with_positions(
        inv=inv, aisles=[aisle], positions=[deleted, active]
    )
    aisle_uc = ExportAisleBusinessCsvUseCase(
        inv_repo,
        aisle_repo,
        pos_repo,
        prod_repo,
        ResultContextResolver(job_repo),
    )
    body, _ = aisle_uc.execute_csv("inv-1", "a1")
    _, rows = _parse_csv(body)
    assert len(rows) == 2
    del_row = next(r for r in rows if r["position_id"] == "p-del")
    assert del_row["Incluido en totales"] == "no"
    assert del_row["Motivo de exclusión"] == "Eliminada"
    summary_uc = ExportInventorySummaryCsvUseCase(
        inv_repo,
        aisle_repo,
        pos_repo,
        prod_repo,
        ResultContextResolver(job_repo),
        job_repo=job_repo,
    )
    _, summary_rows = _parse_csv(summary_uc.execute_inventory_summary_csv("inv-1")[0])
    assert summary_rows[0]["Total contabilizado"] == "2"


def test_legacy_aisle_export_still_excludes_deleted() -> None:
    inv = Inventory("inv-1", "Warehouse", InventoryStatus.PROCESSING, NOW, NOW)
    aisle = Aisle("a1", "inv-1", "A1", AisleStatus.COMPLETED, NOW, NOW)
    deleted = Position(
        id="p-del",
        aisle_id="a1",
        status=PositionStatus.DELETED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id=None,
        created_at=NOW,
        updated_at=NOW,
        detected_summary_json={"internal_code": "DEL", "final_quantity": 1},
    )
    active = Position(
        id="p-ok",
        aisle_id="a1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id=None,
        created_at=NOW,
        updated_at=NOW,
        detected_summary_json={"internal_code": "OK", "final_quantity": 2},
    )
    inv_repo, aisle_repo, pos_repo, prod_repo, job_repo = _repos_with_positions(
        inv=inv, aisles=[aisle], positions=[deleted, active]
    )
    legacy_uc = ExportAisleResultsCsvUseCase(
        inv_repo,
        aisle_repo,
        pos_repo,
        prod_repo,
        ResultContextResolver(job_repo),
    )
    _, rows = _parse_csv(legacy_uc.execute_csv("inv-1", "a1"))
    assert len(rows) == 1
    assert rows[0]["position_id"] == "p-ok"


def test_traceability_invalid_excluded_from_summaries() -> None:
    inv = Inventory("inv-1", "Warehouse", InventoryStatus.PROCESSING, NOW, NOW)
    aisle = Aisle("a1", "inv-1", "A1", AisleStatus.COMPLETED, NOW, NOW)
    invalid = Position(
        id="p-inv",
        aisle_id="a1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id=None,
        created_at=NOW,
        updated_at=NOW,
        detected_summary_json={
            "internal_code": "BAD",
            "final_quantity": 50,
            "traceability_status": TraceabilityStatus.INVALID.value,
        },
    )
    valid = Position(
        id="p-ok",
        aisle_id="a1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id=None,
        created_at=NOW,
        updated_at=NOW,
        detected_summary_json={
            "internal_code": "OK",
            "final_quantity": 4,
            "traceability_status": TraceabilityStatus.VALID.value,
        },
    )
    inv_repo, aisle_repo, pos_repo, prod_repo, job_repo = _repos_with_positions(
        inv=inv, aisles=[aisle], positions=[invalid, valid]
    )
    aisle_uc = ExportAisleBusinessCsvUseCase(
        inv_repo,
        aisle_repo,
        pos_repo,
        prod_repo,
        ResultContextResolver(job_repo),
    )
    body, _ = aisle_uc.execute_csv("inv-1", "a1")
    _, rows = _parse_csv(body)
    bad_row = next(r for r in rows if r["position_id"] == "p-inv")
    assert bad_row["Incluido en totales"] == "no"
    assert bad_row["Motivo de exclusión"] == "Trazabilidad inválida"
    summary_uc = ExportInventorySummaryCsvUseCase(
        inv_repo,
        aisle_repo,
        pos_repo,
        prod_repo,
        ResultContextResolver(job_repo),
        job_repo=job_repo,
    )
    inv_csv, _ = summary_uc.execute_inventory_summary_csv("inv-1")
    _, inv_rows = _parse_csv(inv_csv)
    assert inv_rows[0]["Total contabilizado"] == "4"
    aisles_csv, _ = summary_uc.execute_aisles_summary_csv("inv-1")
    _, aisle_rows = _parse_csv(aisles_csv)
    assert aisle_rows[0]["Total contabilizado"] == "4"


class _CountingCollector(ExportInventoryCollector):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.collect_inventory_calls = 0

    def collect_inventory(self, inventory_id: str, **kwargs):
        self.collect_inventory_calls += 1
        return super().collect_inventory(inventory_id, **kwargs)


def test_package_zip_collects_inventory_once() -> None:
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    pos_repo = MemoryPositionRepository()
    prod_repo = MemoryProductRecordRepository()
    job_repo = MemoryJobRepository()
    inv = Inventory("inv-1", "Warehouse", InventoryStatus.PROCESSING, NOW, NOW)
    aisle_repo.save(Aisle("a1", "inv-1", "A1", AisleStatus.COMPLETED, NOW, NOW))
    pos_repo.save(
        Position(
            id="p1",
            aisle_id="a1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=NOW,
            updated_at=NOW,
            detected_summary_json={"internal_code": "SKU", "final_quantity": 1},
        )
    )
    inv_repo.save(inv)
    collector = _CountingCollector(
        inv_repo,
        aisle_repo,
        pos_repo,
        prod_repo,
        ResultContextResolver(job_repo),
    )
    uc = ExportInventoryPackageZipUseCase(
        inv_repo,
        aisle_repo,
        pos_repo,
        prod_repo,
        ResultContextResolver(job_repo),
        job_repo=job_repo,
    )
    uc._collector = collector
    uc.execute_zip("inv-1")
    assert collector.collect_inventory_calls == 1


def test_zip_aisle_csv_matches_standalone_business_export() -> None:
    inv_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    pos_repo = MemoryPositionRepository()
    prod_repo = MemoryProductRecordRepository()
    job_repo = MemoryJobRepository()
    inv = Inventory("inv-1", "Warehouse", InventoryStatus.PROCESSING, NOW, NOW)
    aisle = Aisle("a1", "inv-1", "A1", AisleStatus.COMPLETED, NOW, NOW)
    pos_repo.save(
        Position(
            id="p1",
            aisle_id="a1",
            status=PositionStatus.DETECTED,
            confidence=0.9,
            needs_review=False,
            primary_evidence_id=None,
            created_at=NOW,
            updated_at=NOW,
            detected_summary_json={"internal_code": "SKU", "final_quantity": 7},
        )
    )
    inv_repo.save(inv)
    aisle_repo.save(aisle)
    resolver = ResultContextResolver(job_repo)
    standalone_uc = ExportAisleBusinessCsvUseCase(
        inv_repo, aisle_repo, pos_repo, prod_repo, resolver
    )
    standalone_body, _ = standalone_uc.execute_csv("inv-1", "a1")
    package_uc = ExportInventoryPackageZipUseCase(
        inv_repo, aisle_repo, pos_repo, prod_repo, resolver, job_repo=job_repo
    )
    zip_bytes, _ = package_uc.execute_zip("inv-1")
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        zip_aisle_path = next(
            n for n in zf.namelist() if n.startswith("aisles/aisle_") and n.endswith("_operational.csv")
        )
        zip_body = zf.read(zip_aisle_path).decode("utf-8-sig")
    assert _parse_csv(zip_body) == _parse_csv(standalone_body)
    collector = ExportInventoryCollector(inv_repo, aisle_repo, pos_repo, prod_repo, resolver)
    data = collector.collect_inventory("inv-1", include_deleted_rows=True)
    bundle = data.aisle_bundles[0]
    built = build_business_aisle_operational_csv_from_bundle(data, bundle)
    assert _parse_csv(built) == _parse_csv(standalone_body)


def test_package_zip_structure() -> None:
    inv = Inventory("inv-1", "Warehouse", InventoryStatus.PROCESSING, NOW, NOW)
    aisle = Aisle("a1", "inv-1", "A1", AisleStatus.COMPLETED, NOW, NOW)
    pos = Position(
        id="p1",
        aisle_id="a1",
        status=PositionStatus.DETECTED,
        confidence=0.9,
        needs_review=False,
        primary_evidence_id=None,
        created_at=NOW,
        updated_at=NOW,
        detected_summary_json={"internal_code": "SKU", "final_quantity": 1},
    )
    inv_repo, aisle_repo, pos_repo, prod_repo, job_repo = _repos_with_positions(
        inv=inv, aisles=[aisle], positions=[pos]
    )
    uc = ExportInventoryPackageZipUseCase(
        inv_repo,
        aisle_repo,
        pos_repo,
        prod_repo,
        ResultContextResolver(job_repo),
        job_repo=job_repo,
    )
    data, name = uc.execute_zip("inv-1")
    assert name.endswith("_export.zip")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
        assert "inventory_summary.csv" in names
        assert "aisles_summary.csv" in names
        assert any(n.startswith("aisles/aisle_") and n.endswith("_operational.csv") for n in names)
        _, inv_sum = _parse_csv(zf.read("inventory_summary.csv").decode("utf-8-sig"))
        assert inv_sum[0]["Total contabilizado"] == "1"


def test_summary_not_found() -> None:
    uc = ExportInventorySummaryCsvUseCase(
        MemoryInventoryRepository(),
        MemoryAisleRepository(),
        MemoryPositionRepository(),
        MemoryProductRecordRepository(),
        ResultContextResolver(MemoryJobRepository()),
    )
    with pytest.raises(InventoryNotFoundError):
        uc.execute_inventory_summary_csv("missing")
