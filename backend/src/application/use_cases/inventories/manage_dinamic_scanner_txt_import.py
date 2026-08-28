"""Preview and confirm Dinamic Scanner TXT imports."""

from __future__ import annotations

from dataclasses import dataclass, replace

from src.application.ports.clock import Clock
from src.application.ports.local_csv_import_repository import LocalCsvImportRepository
from src.application.ports.repositories import InventoryRepository
from src.application.services.dinamic_scanner_aisle_resolver import DinamicScannerAisleResolver
from src.application.services.dinamic_scanner_txt_parser import (
    aisle_code_from_txt_filename,
    parse_dinamic_scanner_txt,
)
from src.application.services.dinamic_scanner_txt_to_local_csv import (
    build_parsed_local_csv_from_scanner_txt,
)
from src.application.use_cases.inventories.manage_local_csv_import import (
    ConfirmLocalCsvImport,
    PreviewLocalCsvImport,
)
from src.domain.dinamic_scanner_txt.constants import SCANNER_TXT_PENDING_AISLE_ID
from src.domain.dinamic_scanner_txt.errors import (
    DinamicScannerTxtImportDisabledError,
    DinamicScannerTxtImportError,
)
from src.domain.dinamic_scanner_txt.metadata import DinamicScannerTxtImportMetadata
from src.domain.local_csv_import.entities import LocalCsvImport
from src.domain.local_csv_import.errors import (
    LOCAL_CSV_IMPORT_NOT_FOUND,
    LocalCsvImportError,
)


@dataclass(frozen=True)
class DinamicScannerTxtPreviewResult:
    aisle_code: str
    aisle_id: str
    aisle_created: bool
    aisle_will_be_created: bool
    positions_imported: int
    products_imported: int
    omitted_records: int
    parse_warnings: tuple[str, ...]
    csv_import: LocalCsvImport


@dataclass(frozen=True)
class DinamicScannerTxtConfirmResult:
    aisle_code: str
    aisle_id: str
    aisle_created: bool
    aisle_will_be_created: bool
    positions_imported: int
    products_imported: int
    omitted_records: int
    parse_warnings: tuple[str, ...]
    csv_import: LocalCsvImport
    duplicate: bool


class PreviewDinamicScannerTxtImport:
    def __init__(
        self,
        *,
        inventory_repo: InventoryRepository,
        aisle_resolver: DinamicScannerAisleResolver,
        import_repo: LocalCsvImportRepository,
        csv_preview: PreviewLocalCsvImport,
        clock: Clock,
        enabled: bool,
        max_lines: int,
        max_line_length: int,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_resolver = aisle_resolver
        self._import_repo = import_repo
        self._csv_preview = csv_preview
        self._clock = clock
        self._enabled = enabled
        self._max_lines = max_lines
        self._max_line_length = max_line_length

    def execute(
        self,
        *,
        inventory_id: str,
        content: bytes,
        filename: str | None,
    ) -> DinamicScannerTxtPreviewResult:
        if not self._enabled:
            raise DinamicScannerTxtImportDisabledError()
        if self._inventory_repo.get_by_id(inventory_id) is None:
            raise DinamicScannerTxtImportError(
                "INVENTORY_NOT_FOUND", f"Inventory {inventory_id} not found"
            )

        aisle_code = aisle_code_from_txt_filename(filename)
        parsed_txt = parse_dinamic_scanner_txt(
            content,
            max_lines=self._max_lines,
            max_line_length=self._max_line_length,
        )
        existing_aisle = self._aisle_resolver.find_existing(
            inventory_id=inventory_id,
            aisle_code=aisle_code,
        )
        aisle_will_be_created = existing_aisle is None
        staging_aisle_id = (
            existing_aisle.id if existing_aisle is not None else SCANNER_TXT_PENDING_AISLE_ID
        )
        now = self._clock.now()
        parsed_csv = build_parsed_local_csv_from_scanner_txt(
            parsed_txt=parsed_txt,
            inventory_id=inventory_id,
            aisle_id=staging_aisle_id,
            aisle_code=aisle_code,
            exported_at=now,
        )
        try:
            csv_import = self._csv_preview.execute_from_parsed(
                inventory_id=inventory_id,
                parsed=parsed_csv,
                pending_aisle_ids=frozenset({SCANNER_TXT_PENDING_AISLE_ID}),
            )
        except LocalCsvImportError as exc:
            raise DinamicScannerTxtImportError(exc.code, str(exc)) from exc

        omitted = sum(1 for product in parsed_txt.products if product.errors)
        valid_products = len(parsed_txt.products) - omitted
        metadata = DinamicScannerTxtImportMetadata(
            aisle_code=aisle_code,
            aisle_will_be_created=aisle_will_be_created,
            target_aisle_id=existing_aisle.id if existing_aisle is not None else None,
            positions_imported=len(parsed_txt.positions),
            products_imported=valid_products,
            omitted_records=omitted + len(parsed_txt.parse_warnings),
            parse_warnings=parsed_txt.parse_warnings,
        )
        csv_import = self._import_repo.save(
            replace(csv_import, source_metadata_json=metadata.to_json())
        )

        return DinamicScannerTxtPreviewResult(
            aisle_code=aisle_code,
            aisle_id=existing_aisle.id if existing_aisle is not None else "",
            aisle_created=False,
            aisle_will_be_created=aisle_will_be_created,
            positions_imported=len(parsed_txt.positions),
            products_imported=valid_products,
            omitted_records=omitted + len(parsed_txt.parse_warnings),
            parse_warnings=parsed_txt.parse_warnings,
            csv_import=csv_import,
        )


class ConfirmDinamicScannerTxtImport:
    def __init__(
        self,
        *,
        import_repo: LocalCsvImportRepository,
        aisle_resolver: DinamicScannerAisleResolver,
        csv_confirm: ConfirmLocalCsvImport,
        enabled: bool,
    ) -> None:
        self._import_repo = import_repo
        self._aisle_resolver = aisle_resolver
        self._csv_confirm = csv_confirm
        self._enabled = enabled

    def execute(
        self,
        *,
        inventory_id: str,
        export_id: str,
        conflict_policy: str = "SKIP",
        confirmed_by_user_id: str | None = None,
    ) -> DinamicScannerTxtConfirmResult:
        if not self._enabled:
            raise DinamicScannerTxtImportDisabledError()

        staged = self._import_repo.get_by_export_id(
            inventory_id=inventory_id, export_id=export_id.strip()
        )
        if staged is None:
            raise DinamicScannerTxtImportError(
                LOCAL_CSV_IMPORT_NOT_FOUND, "Scanner TXT import not found"
            )
        metadata = DinamicScannerTxtImportMetadata.from_json(staged.source_metadata_json)
        if metadata is None:
            raise DinamicScannerTxtImportError(
                "DINAMIC_SCANNER_TXT_METADATA_MISSING",
                "Staged import is missing scanner TXT metadata",
            )

        aisle_created = False
        if metadata.aisle_will_be_created:
            created_aisle, aisle_created = self._aisle_resolver.create_for_confirm(
                inventory_id=inventory_id,
                aisle_code=metadata.aisle_code,
            )
            target_aisle_id = created_aisle.id
        else:
            existing_aisle = self._aisle_resolver.find_existing(
                inventory_id=inventory_id,
                aisle_code=metadata.aisle_code,
            )
            if existing_aisle is None:
                raise DinamicScannerTxtImportError(
                    "DINAMIC_SCANNER_TXT_AISLE_NOT_FOUND",
                    f"Aisle {metadata.aisle_code!r} no longer exists",
                )
            target_aisle_id = existing_aisle.id

        if any(row.aisle_id == SCANNER_TXT_PENDING_AISLE_ID for row in staged.rows):
            updated_rows = tuple(
                replace(row, aisle_id=target_aisle_id) for row in staged.rows
            )
            staged = self._import_repo.save(
                replace(staged, rows=updated_rows, source_metadata_json=metadata.to_json())
            )

        try:
            confirmed, duplicate = self._csv_confirm.execute(
                inventory_id=inventory_id,
                export_id=export_id,
                conflict_policy=conflict_policy,
                confirmed_by_user_id=confirmed_by_user_id,
            )
        except LocalCsvImportError as exc:
            raise DinamicScannerTxtImportError(exc.code, str(exc)) from exc

        if aisle_created:
            metadata = replace(metadata, aisle_created_on_confirm=True)
            confirmed = self._import_repo.save(
                replace(confirmed, source_metadata_json=metadata.to_json())
            )

        return DinamicScannerTxtConfirmResult(
            aisle_code=metadata.aisle_code,
            aisle_id=target_aisle_id,
            aisle_created=aisle_created,
            aisle_will_be_created=metadata.aisle_will_be_created,
            positions_imported=metadata.positions_imported,
            products_imported=metadata.products_imported,
            omitted_records=metadata.omitted_records,
            parse_warnings=metadata.parse_warnings,
            csv_import=confirmed,
            duplicate=duplicate,
        )
