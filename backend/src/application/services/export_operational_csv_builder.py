"""Build operational CSV text for business profile exports."""

from __future__ import annotations

from src.application.services.csv_inventory_exporter import (
    INVENTORY_RESULTS_CSV_FIELDS,
    INVENTORY_RESULTS_TECHNICAL_CSV_FIELDS,
    CsvInventoryExporter,
)
from src.application.services.export_csv_column_mapper import (
    BUSINESS_OPERATIONAL_CSV_FIELDS,
    ExportCsvColumnMapper,
    ExportCsvProfile,
)
from src.application.services.export_inventory_collector import (
    ExportAisleOperationalBundle,
    ExportInventoryOperationalData,
)


class ExportOperationalCsvBuilder:
    @staticmethod
    def business_rows_for_bundle(
        data: ExportInventoryOperationalData,
        bundle: ExportAisleOperationalBundle,
    ) -> list[dict]:
        supplier_name = data.supplier_names_by_aisle_id.get(bundle.aisle.id, "")
        job_id = bundle.job_id_for_slice or ""
        mapped: list[dict] = []
        for row_bundle in bundle.rows:
            mapped.append(
                ExportCsvColumnMapper.map_operational_row(
                    row_bundle.internal_row,
                    profile="business",
                    client_name=data.client_name,
                    supplier_name=supplier_name,
                    included_in_totals=row_bundle.rollup_result.included_in_totals,
                    exclusion_reason=row_bundle.rollup_result.exclusion_reason,
                    job_id=job_id,
                )
            )
        return mapped

    @staticmethod
    def to_csv(
        rows: list[dict],
        *,
        profile: ExportCsvProfile,
        technical: bool = False,
    ) -> str:
        if technical:
            fieldnames = INVENTORY_RESULTS_TECHNICAL_CSV_FIELDS
        elif profile == "business":
            fieldnames = BUSINESS_OPERATIONAL_CSV_FIELDS
        else:
            fieldnames = INVENTORY_RESULTS_CSV_FIELDS
        return CsvInventoryExporter.to_csv(rows, fieldnames=fieldnames)
