"""ExportCsvColumnMapper — legacy vs business profiles."""

from __future__ import annotations

from src.application.services.csv_inventory_exporter import INVENTORY_RESULTS_CSV_FIELDS
from src.application.services.export_csv_column_mapper import (
    BUSINESS_OPERATIONAL_CSV_FIELDS,
    ExportCsvColumnMapper,
)


def _internal_row() -> dict:
    return {
        "inventory_id": "inv-1",
        "inventory_name": "Warehouse",
        "aisle_id": "a1",
        "aisle_code": "A1",
        "aisle_sequence": 1,
        "position_id": "p1",
        "position_status": "detected",
        "needs_review": False,
        "position_code": "P-01",
        "product_sku": "SKU1",
        "product_display_label": "Product One",
        "barcode": "123",
        "detected_quantity": 2,
        "corrected_quantity": "",
        "final_quantity": 2,
        "qty_source": "detected",
        "qty_inference_reason": "",
        "traceability_status": "valid",
        "source_image_id": "img-1",
        "primary_evidence_id": "ev-1",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }


def test_legacy_profile_preserves_internal_keys() -> None:
    internal = _internal_row()
    out = ExportCsvColumnMapper.map_operational_row(internal, profile="legacy")
    assert out == internal


def test_business_profile_spanish_headers_and_ids_not_first() -> None:
    out = ExportCsvColumnMapper.map_operational_row(
        _internal_row(),
        profile="business",
        client_name="Cliente SA",
        supplier_name="Proveedor X",
        included_in_totals=True,
        exclusion_reason=None,
    )
    assert list(out.keys())[:3] == ["Inventario", "Cliente", "Proveedor"]
    assert out["Inventario"] == "Warehouse"
    assert out["Pasillo"] == "A1"
    assert out["Incluido en totales"] == "sí"
    assert out["Motivo de exclusión"] == ""
    assert out["Costo unitario"] == ""
    assert out["Costo total de línea"] == ""
    assert out["inventory_id"] == "inv-1"
    assert BUSINESS_OPERATIONAL_CSV_FIELDS[0] == "Inventario"
    assert BUSINESS_OPERATIONAL_CSV_FIELDS[-1] == "job_id"


def test_business_fieldnames_order() -> None:
    fields = ExportCsvColumnMapper.operational_fieldnames(
        "business",
        legacy_fieldnames=INVENTORY_RESULTS_CSV_FIELDS,
        technical_fieldnames=(),
    )
    assert fields[0] == "Inventario"
    assert "inventory_id" in fields
    assert fields.index("inventory_id") > fields.index("Última actualización")
