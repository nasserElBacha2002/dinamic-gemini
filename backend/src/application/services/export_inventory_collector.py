"""Load and assemble export rows for inventory-scoped exports (shared by CSV/ZIP use cases)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from src.application.errors import AisleNotFoundError, InventoryNotFoundError
from src.application.mappers.inventory_export_rows import (
    export_position_sort_key,
    position_to_operational_export_row_dict,
)
from src.application.ports.repositories import (
    AisleRepository,
    ClientRepository,
    ClientSupplierRepository,
    InventoryRepository,
    PositionRepository,
    ProductRecordRepository,
)
from src.application.services.aisle_results_export_source import (
    AISLE_RESULTS_UI_CONSOLIDATE_BY_SKU,
    ui_aligned_rollup_service,
)
from src.application.services.display_primary_product import select_display_primary_product
from src.application.services.export_quantity_rollup import (
    ExportQuantityRollupService,
    ExportRollupRowInput,
    ExportRowRollupResult,
)
from src.application.services.position_sku_consolidation import consolidate_positions_by_sku
from src.application.services.result_context_resolver import ResultContextResolver
from src.application.utils.natural_sort import natural_sort_key_parts
from src.domain.aisle.entities import Aisle
from src.domain.inventory.entities import Inventory
from src.domain.positions.entities import Position, PositionStatus


@dataclass(frozen=True)
class ExportOperationalRowBundle:
    internal_row: dict
    rollup_input: ExportRollupRowInput
    rollup_result: ExportRowRollupResult
    job_id_for_slice: str | None


@dataclass(frozen=True)
class ExportAisleOperationalBundle:
    aisle: Aisle
    aisle_sequence: int
    rows: tuple[ExportOperationalRowBundle, ...]
    job_id_for_slice: str | None


@dataclass(frozen=True)
class ExportInventoryOperationalData:
    inventory: Inventory
    client_name: str
    aisles_in_order: tuple[Aisle, ...]
    aisle_bundles: tuple[ExportAisleOperationalBundle, ...]
    supplier_names_by_aisle_id: dict[str, str]


class ExportInventoryCollector:
    """Fetches inventory export data once for summary, business CSV, and ZIP flows."""

    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        position_repo: PositionRepository,
        product_record_repo: ProductRecordRepository,
        result_context_resolver: ResultContextResolver,
        client_repo: ClientRepository | None = None,
        client_supplier_repo: ClientSupplierRepository | None = None,
        rollup_service: ExportQuantityRollupService | None = None,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._position_repo = position_repo
        self._product_record_repo = product_record_repo
        self._resolver = result_context_resolver
        self._client_repo = client_repo
        self._client_supplier_repo = client_supplier_repo
        self._rollup = rollup_service or ui_aligned_rollup_service()

    def collect_inventory(
        self,
        inventory_id: str,
        *,
        explicit_job_id_by_aisle: dict[str, str | None] | None = None,
        include_deleted_rows: bool = False,
        consolidate_by_sku: bool = AISLE_RESULTS_UI_CONSOLIDATE_BY_SKU,
        operational_only: bool = True,
    ) -> ExportInventoryOperationalData:
        """Assemble inventory export data.

        ``operational_only=True`` (default for inventory-level exports) includes only
        active aisles for quantity rollups / consolidated rows. Pass ``False`` when
        historical aisle rows or all-aisle job costs are required.
        """
        inv = self._inventory_repo.get_by_id(inventory_id)
        if inv is None:
            raise InventoryNotFoundError(f"Inventory not found: {inventory_id}")

        client_name = ""
        if self._client_repo and inv.client_id:
            client = self._client_repo.get_by_id(inv.client_id)
            if client is not None:
                client_name = client.name

        aisles = list(self._aisle_repo.list_by_inventory(inventory_id))
        if operational_only:
            aisles = [a for a in aisles if a.is_active]
        sorted_aisles = sorted(
            aisles,
            key=lambda a: (natural_sort_key_parts(a.code), a.created_at, a.id),
        )
        aisle_ids = [a.id for a in sorted_aisles]
        all_positions = list(self._position_repo.list_by_aisles(aisle_ids)) if aisle_ids else []
        by_aisle: defaultdict[str, list[Position]] = defaultdict(list)
        for p in all_positions:
            by_aisle[p.aisle_id].append(p)

        supplier_names: dict[str, str] = {}
        job_overrides = explicit_job_id_by_aisle or {}
        bundles: list[ExportAisleOperationalBundle] = []

        for seq, aisle in enumerate(sorted_aisles, start=1):
            supplier_name = ""
            if self._client_supplier_repo and aisle.client_supplier_id:
                supplier = self._client_supplier_repo.get_by_id(aisle.client_supplier_id)
                if supplier is not None:
                    supplier_name = supplier.name
            supplier_names[aisle.id] = supplier_name

            explicit = job_overrides.get(aisle.id)
            bundle = self._collect_aisle(
                inv,
                aisle,
                aisle_sequence=seq,
                aisle_positions=list(by_aisle.get(aisle.id, [])),
                explicit_job_id=explicit,
                include_deleted_rows=include_deleted_rows,
                consolidate_by_sku=consolidate_by_sku,
            )
            bundles.append(bundle)

        return ExportInventoryOperationalData(
            inventory=inv,
            client_name=client_name,
            aisles_in_order=tuple(sorted_aisles),
            aisle_bundles=tuple(bundles),
            supplier_names_by_aisle_id=supplier_names,
        )

    def collect_aisle(
        self,
        inventory_id: str,
        aisle_id: str,
        *,
        explicit_job_id: str | None = None,
        include_deleted_rows: bool = False,
        consolidate_by_sku: bool = AISLE_RESULTS_UI_CONSOLIDATE_BY_SKU,
    ) -> ExportInventoryOperationalData:
        inv = self._inventory_repo.get_by_id(inventory_id)
        if inv is None:
            raise InventoryNotFoundError(f"Inventory not found: {inventory_id}")
        aisle = self._aisle_repo.get_by_id(aisle_id)
        if aisle is None or aisle.inventory_id != inventory_id:
            raise AisleNotFoundError(
                f"Aisle {aisle_id} not found or does not belong to inventory {inventory_id}"
            )
        positions = list(self._position_repo.list_by_aisles([aisle_id]))
        bundle = self._collect_aisle(
            inv,
            aisle,
            aisle_sequence=1,
            aisle_positions=positions,
            explicit_job_id=explicit_job_id,
            include_deleted_rows=include_deleted_rows,
            consolidate_by_sku=consolidate_by_sku,
        )
        client_name = ""
        if self._client_repo and inv.client_id:
            client = self._client_repo.get_by_id(inv.client_id)
            if client is not None:
                client_name = client.name
        supplier_name = ""
        if self._client_supplier_repo and aisle.client_supplier_id:
            supplier = self._client_supplier_repo.get_by_id(aisle.client_supplier_id)
            if supplier is not None:
                supplier_name = supplier.name
        return ExportInventoryOperationalData(
            inventory=inv,
            client_name=client_name,
            aisles_in_order=(aisle,),
            aisle_bundles=(bundle,),
            supplier_names_by_aisle_id={aisle.id: supplier_name},
        )

    def _collect_aisle(
        self,
        inv: Inventory,
        aisle: Aisle,
        *,
        aisle_sequence: int,
        aisle_positions: list[Position],
        explicit_job_id: str | None,
        include_deleted_rows: bool = False,
        consolidate_by_sku: bool = AISLE_RESULTS_UI_CONSOLIDATE_BY_SKU,
    ) -> ExportAisleOperationalBundle:
        ctx = self._resolver.resolve(aisle=aisle, explicit_job_id=explicit_job_id)
        slice_job = ctx.job_id_for_slice
        if include_deleted_rows:
            candidates = list(aisle_positions)
        else:
            candidates = [p for p in aisle_positions if p.status != PositionStatus.DELETED]
        if slice_job is None:
            raw = [p for p in candidates if p.job_id is None]
        else:
            raw = [p for p in candidates if p.job_id == slice_job]
        consolidated = consolidate_positions_by_sku(raw, enabled=consolidate_by_sku)
        consolidated_sorted = sorted(consolidated, key=export_position_sort_key)

        row_bundles: list[ExportOperationalRowBundle] = []
        for p in consolidated_sorted:
            products = self._product_record_repo.list_by_position(p.id)
            primary = select_display_primary_product(products)
            internal = position_to_operational_export_row_dict(
                inv, aisle, aisle_sequence, p, primary
            )
            rollup_input = ExportRollupRowInput(
                position_id=p.id,
                aisle_id=aisle.id,
                position_status=p.status.value,
                traceability_status=str(internal.get("traceability_status", "") or "") or None,
                needs_review=bool(internal.get("needs_review")),
                final_quantity=int(internal.get("final_quantity") or 0),
            )
            rollup_result = self._rollup.rollup_row(rollup_input)
            row_bundles.append(
                ExportOperationalRowBundle(
                    internal_row=internal,
                    rollup_input=rollup_input,
                    rollup_result=rollup_result,
                    job_id_for_slice=slice_job,
                )
            )
        return ExportAisleOperationalBundle(
            aisle=aisle,
            aisle_sequence=aisle_sequence,
            rows=tuple(row_bundles),
            job_id_for_slice=slice_job,
        )
