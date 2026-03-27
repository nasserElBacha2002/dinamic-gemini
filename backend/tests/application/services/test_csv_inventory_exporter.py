"""CsvInventoryExporter — UTF-8 BOM for Excel."""

from src.application.services.csv_inventory_exporter import CsvInventoryExporter, UTF8_BOM


def test_csv_exporter_prefixes_utf8_bom() -> None:
    out = CsvInventoryExporter.to_csv([])
    assert out.startswith(UTF8_BOM)
    assert "inventory_id" in out
