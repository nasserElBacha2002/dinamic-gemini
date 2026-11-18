"""Scanner package import metadata serialization."""

from __future__ import annotations

from src.domain.local_inventory_package.scanner_metadata import (
    LocalScannerPackageImportMetadata,
)


def test_metadata_round_trip() -> None:
    metadata = LocalScannerPackageImportMetadata(
        aisle_code="PASILLO_09",
        aisle_will_be_created=True,
        client_id="client-a",
        inventory_name="prueba-local",
        inventory_provisional=True,
    )
    parsed = LocalScannerPackageImportMetadata.from_json(metadata.to_json())
    assert parsed is not None
    assert parsed.aisle_code == "PASILLO_09"
    assert parsed.aisle_will_be_created is True
    assert parsed.inventory_provisional is True
