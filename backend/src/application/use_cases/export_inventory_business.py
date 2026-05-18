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
from src.application.services.csv_inventory_exporter import CsvInventoryExporter
from src.application.services.export_cost_helpers import job_total_cost_string
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
from src.domain.jobs.entities import Job


def _job_for_bundle(
    job_repo: JobRepository | None,
    bundle: ExportAisleOperationalBundle,
) -> Job | None:
    if job_repo is None or not bundle.job_id_for_slice:
        return None
    return job_repo.get_by_id(bundle.job_id_for_slice)


def _aisle_costs_from_data(
    data: ExportInventoryOperationalData,
    job_repo: JobRepository | None,
) -> dict[str, str]:
    if job_repo is None:
        return {}
    return {
        bundle.aisle.id: job_total_cost_string(_job_for_bundle(job_repo, bundle))
        for bundle in data.aisle_bundles
    }


def build_inventory_summary_csv_from_data(
    data: ExportInventoryOperationalData,
    *,
    summary: ExportSummaryBuilder,
    job_repo: JobRepository | None,
) -> str:
    rollups = summary.build_rollups(data)
    inv_cost = ExportSummaryBuilder.sum_aisle_job_costs(
        [_job_for_bundle(job_repo, b) for b in data.aisle_bundles]
    )
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
        data = self._collector.collect_inventory(inventory_id, include_deleted_rows=True)
        body = build_inventory_summary_csv_from_data(
            data, summary=self._summary, job_repo=self._job_repo
        )
        filename = inventory_summary_csv_filename(data.inventory.name, data.inventory.id)
        return body, filename

    def execute_aisles_summary_csv(self, inventory_id: str) -> tuple[str, str]:
        data = self._collector.collect_inventory(inventory_id, include_deleted_rows=True)
        body = build_aisles_summary_csv_from_data(
            data, summary=self._summary, job_repo=self._job_repo
        )
        filename = inventory_aisles_summary_csv_filename(data.inventory.name, data.inventory.id)
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
        data = self._collector.collect_inventory(inventory_id, include_deleted_rows=True)

        entries: dict[str, str] = {
            "inventory_summary.csv": build_inventory_summary_csv_from_data(
                data, summary=self._summary, job_repo=self._job_repo
            ),
            "aisles_summary.csv": build_aisles_summary_csv_from_data(
                data, summary=self._summary, job_repo=self._job_repo
            ),
        }
        for bundle in data.aisle_bundles:
            csv_body = build_business_aisle_operational_csv_from_bundle(data, bundle)
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
