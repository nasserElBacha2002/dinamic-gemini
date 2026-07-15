"""Additive inventory export use cases (business profile, summary, ZIP package)."""

from __future__ import annotations

from src.application.errors import InventoryNotFoundError
from src.application.ports.repositories import (
    AisleRepository,
    ClientRepository,
    ClientSupplierRepository,
    InventoryRepository,
    JobRepository,
    PositionRepository,
    ProductRecordRepository,
)
from src.application.services.billable_job_cost_aggregation import (
    export_cost_strings_by_aisle_id,
    export_inventory_total_cost_string,
)
from src.application.services.csv_inventory_exporter import CsvInventoryExporter
from src.application.services.export_csv_column_mapper import (
    BUSINESS_AISLES_SUMMARY_CSV_FIELDS,
    BUSINESS_INVENTORY_SUMMARY_CSV_FIELDS,
)
from src.application.services.export_filename_helpers import (
    aisle_operational_csv_filename,
    inventory_aisles_summary_csv_filename,
    inventory_package_zip_filename,
    inventory_summary_csv_filename,
    sanitize_filename_part,
)
from src.application.services.export_inventory_collector import (
    ExportAisleOperationalBundle,
    ExportInventoryCollector,
    ExportInventoryOperationalData,
)
from src.application.services.export_operational_csv_builder import ExportOperationalCsvBuilder
from src.application.services.export_summary_builder import ExportSummaryBuilder
from src.application.services.export_zip_packager import ExportZipPackager
from src.application.services.result_context_resolver import ResultContextResolver


def _aisle_costs_from_data(
    data: ExportInventoryOperationalData,
    job_repo: JobRepository | None,
) -> dict[str, str]:
    """Accumulated billable cost per aisle (all countable runs), not operational-only."""
    aisle_ids = [bundle.aisle.id for bundle in data.aisle_bundles]
    return export_cost_strings_by_aisle_id(job_repo, aisle_ids)


def build_inventory_summary_csv_from_data(
    data: ExportInventoryOperationalData,
    *,
    summary: ExportSummaryBuilder,
    job_repo: JobRepository | None,
    cost_data: ExportInventoryOperationalData | None = None,
) -> str:
    """Build inventory summary CSV.

    Quantity rollups come from ``data`` (typically active aisles only). Job costs
    come from ``cost_data`` when provided (typically all aisles, including inactive):
    sum of every billable ``process_aisle`` job per aisle, not only the operational job.
    """
    rollups = summary.build_rollups(data)
    cost_source = cost_data if cost_data is not None else data
    aisle_ids = [b.aisle.id for b in cost_source.aisle_bundles]
    inv_cost = export_inventory_total_cost_string(job_repo, aisle_ids)
    row = summary.inventory_summary_row(data, rollups, inventory_total_cost=inv_cost)
    return CsvInventoryExporter.to_csv([row], fieldnames=BUSINESS_INVENTORY_SUMMARY_CSV_FIELDS)


def build_aisles_summary_csv_from_data(
    data: ExportInventoryOperationalData,
    *,
    summary: ExportSummaryBuilder,
    job_repo: JobRepository | None,
) -> str:
    rollups = summary.build_rollups(data)
    aisle_costs = _aisle_costs_from_data(data, job_repo)
    last_updated = {
        b.aisle.id: ExportSummaryBuilder.max_updated_at_for_bundle(b.rows)
        for b in data.aisle_bundles
    }
    rows = summary.aisles_summary_rows(
        data,
        rollups,
        aisle_cost_by_id=aisle_costs,
        last_updated_by_aisle=last_updated,
    )
    return CsvInventoryExporter.to_csv(rows, fieldnames=BUSINESS_AISLES_SUMMARY_CSV_FIELDS)


def build_business_aisle_operational_csv_from_bundle(
    data: ExportInventoryOperationalData,
    bundle: ExportAisleOperationalBundle,
) -> str:
    rows = ExportOperationalCsvBuilder.business_rows_for_bundle(data, bundle)
    return ExportOperationalCsvBuilder.to_csv(rows, profile="business")


class ExportInventorySummaryCsvUseCase:
    """Export inventory-level and aisle-level summary CSV."""

    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        position_repo: PositionRepository,
        product_record_repo: ProductRecordRepository,
        result_context_resolver: ResultContextResolver,
        client_repo: ClientRepository | None = None,
        client_supplier_repo: ClientSupplierRepository | None = None,
        job_repo: JobRepository | None = None,
    ) -> None:
        self._collector = ExportInventoryCollector(
            inventory_repo,
            aisle_repo,
            position_repo,
            product_record_repo,
            result_context_resolver,
            client_repo=client_repo,
            client_supplier_repo=client_supplier_repo,
        )
        self._summary = ExportSummaryBuilder()
        self._job_repo = job_repo

    def execute_inventory_summary_csv(self, inventory_id: str) -> tuple[str, str]:
        ops_data = self._collector.collect_inventory(
            inventory_id, include_deleted_rows=True, operational_only=True
        )
        all_data = self._collector.collect_inventory(
            inventory_id, include_deleted_rows=True, operational_only=False
        )
        body = build_inventory_summary_csv_from_data(
            ops_data,
            summary=self._summary,
            job_repo=self._job_repo,
            cost_data=all_data,
        )
        filename = inventory_summary_csv_filename(ops_data.inventory.name, ops_data.inventory.id)
        return body, filename

    def execute_aisles_summary_csv(self, inventory_id: str) -> tuple[str, str]:
        # Include inactive aisles with historical qty + cost at aisle grain.
        all_data = self._collector.collect_inventory(
            inventory_id, include_deleted_rows=True, operational_only=False
        )
        body = build_aisles_summary_csv_from_data(
            all_data, summary=self._summary, job_repo=self._job_repo
        )
        filename = inventory_aisles_summary_csv_filename(
            all_data.inventory.name, all_data.inventory.id
        )
        return body, filename


class ExportInventoryPackageZipUseCase:
    """ZIP with inventory summary, aisles summary, and per-aisle business operational CSVs."""

    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        position_repo: PositionRepository,
        product_record_repo: ProductRecordRepository,
        result_context_resolver: ResultContextResolver,
        client_repo: ClientRepository | None = None,
        client_supplier_repo: ClientSupplierRepository | None = None,
        job_repo: JobRepository | None = None,
    ) -> None:
        self._collector = ExportInventoryCollector(
            inventory_repo,
            aisle_repo,
            position_repo,
            product_record_repo,
            result_context_resolver,
            client_repo=client_repo,
            client_supplier_repo=client_supplier_repo,
        )
        self._summary = ExportSummaryBuilder()
        self._job_repo = job_repo
        self._inventory_repo = inventory_repo

    def execute_zip(self, inventory_id: str) -> tuple[bytes, str]:
        inv = self._inventory_repo.get_by_id(inventory_id)
        if inv is None:
            raise InventoryNotFoundError(f"Inventory not found: {inventory_id}")
        # Consolidated inventory qty: active aisles only; costs + per-aisle files: all aisles.
        ops_data = self._collector.collect_inventory(
            inventory_id, include_deleted_rows=True, operational_only=True
        )
        all_data = self._collector.collect_inventory(
            inventory_id, include_deleted_rows=True, operational_only=False
        )

        entries: dict[str, str] = {
            "inventory_summary.csv": build_inventory_summary_csv_from_data(
                ops_data,
                summary=self._summary,
                job_repo=self._job_repo,
                cost_data=all_data,
            ),
            "aisles_summary.csv": build_aisles_summary_csv_from_data(
                all_data, summary=self._summary, job_repo=self._job_repo
            ),
        }
        for bundle in all_data.aisle_bundles:
            csv_body = build_business_aisle_operational_csv_from_bundle(all_data, bundle)
            aisle_part = sanitize_filename_part(bundle.aisle.code, fallback=bundle.aisle.id)
            entries[f"aisles/aisle_{aisle_part}_operational.csv"] = csv_body

        zip_bytes = ExportZipPackager.build_zip(entries)
        filename = inventory_package_zip_filename(inv.name, inv.id)
        return zip_bytes, filename


class ExportAisleBusinessCsvUseCase:
    """Business-profile aisle operational CSV (additive; legacy default unchanged on route)."""

    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        position_repo: PositionRepository,
        product_record_repo: ProductRecordRepository,
        result_context_resolver: ResultContextResolver,
        client_repo: ClientRepository | None = None,
        client_supplier_repo: ClientSupplierRepository | None = None,
    ) -> None:
        self._collector = ExportInventoryCollector(
            inventory_repo,
            aisle_repo,
            position_repo,
            product_record_repo,
            result_context_resolver,
            client_repo=client_repo,
            client_supplier_repo=client_supplier_repo,
        )

    def execute_csv(
        self,
        inventory_id: str,
        aisle_id: str,
        *,
        job_id: str | None = None,
    ) -> tuple[str, str]:
        jid = str(job_id).strip() if job_id and str(job_id).strip() else None
        data = self._collector.collect_aisle(
            inventory_id,
            aisle_id,
            explicit_job_id=jid,
            include_deleted_rows=True,
        )
        bundle = data.aisle_bundles[0]
        csv_body = build_business_aisle_operational_csv_from_bundle(data, bundle)
        filename = aisle_operational_csv_filename(
            inventory_name=data.inventory.name,
            inventory_id=data.inventory.id,
            aisle_code=bundle.aisle.code,
            aisle_id=bundle.aisle.id,
            profile="business",
        )
        return csv_body, filename
