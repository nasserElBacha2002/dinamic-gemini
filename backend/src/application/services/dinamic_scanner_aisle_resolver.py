"""Resolve or create aisles for Dinamic Scanner TXT import (confirm only)."""

from __future__ import annotations

from src.application.errors import (
    ClientSupplierRequiredForAisleError,
    DuplicateAisleCodeError,
    InventoryClientRequiredForAisleError,
    InventoryNotFoundError,
)
from src.application.ports.repositories import (
    AisleRepository,
    ClientSupplierRepository,
    InventoryRepository,
)
from src.application.use_cases.aisles.create_aisle import CreateAisleCommand, CreateAisleUseCase
from src.domain.aisle.entities import Aisle
from src.domain.dinamic_scanner_txt.errors import (
    TXT_SUPPLIER_AMBIGUOUS,
    DinamicScannerTxtImportError,
)


class DinamicScannerAisleResolver:
    def __init__(
        self,
        *,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        client_supplier_repo: ClientSupplierRepository,
        create_aisle: CreateAisleUseCase,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._client_supplier_repo = client_supplier_repo
        self._create_aisle = create_aisle

    def find_existing(self, *, inventory_id: str, aisle_code: str) -> Aisle | None:
        code = (aisle_code or "").strip()
        if not code:
            raise DinamicScannerTxtImportError(
                "DINAMIC_SCANNER_TXT_EMPTY_AISLE_NAME", "Aisle code is required"
            )
        return self._aisle_repo.get_by_inventory_and_code(inventory_id, code)

    def resolve_client_supplier_id(self, *, inventory_id: str) -> str:
        inventory = self._inventory_repo.get_by_id(inventory_id)
        if inventory is None:
            raise InventoryNotFoundError(f"Inventory not found: {inventory_id}")
        client_id = inventory.client_id
        if not client_id:
            raise DinamicScannerTxtImportError(
                "DINAMIC_SCANNER_TXT_INVENTORY_CLIENT_REQUIRED",
                "Inventory must be associated with a client before creating aisles",
            )
        suppliers = self._client_supplier_repo.list_by_client(client_id)
        if len(suppliers) == 0:
            raise DinamicScannerTxtImportError(
                "DINAMIC_SCANNER_TXT_CLIENT_SUPPLIER_REQUIRED",
                "Client supplier is required to create a new aisle",
            )
        if len(suppliers) > 1:
            raise DinamicScannerTxtImportError(
                TXT_SUPPLIER_AMBIGUOUS,
                "Multiple client suppliers exist; specify supplier explicitly before creating aisles",
            )
        return suppliers[0].id

    def create_for_confirm(self, *, inventory_id: str, aisle_code: str) -> tuple[Aisle, bool]:
        """Create aisle on confirm, or return existing on idempotent retry / race."""
        code = (aisle_code or "").strip()
        if not code:
            raise DinamicScannerTxtImportError(
                "DINAMIC_SCANNER_TXT_EMPTY_AISLE_NAME", "Aisle code is required"
            )
        existing = self.find_existing(inventory_id=inventory_id, aisle_code=code)
        if existing is not None:
            return existing, False

        supplier_id = self.resolve_client_supplier_id(inventory_id=inventory_id)
        try:
            created = self._create_aisle.execute(
                CreateAisleCommand(
                    inventory_id=inventory_id,
                    code=code,
                    client_supplier_id=supplier_id,
                )
            )
        except DuplicateAisleCodeError:
            raced = self.find_existing(inventory_id=inventory_id, aisle_code=code)
            if raced is None:
                raise
            return raced, False
        except InventoryClientRequiredForAisleError as exc:
            raise DinamicScannerTxtImportError(
                "DINAMIC_SCANNER_TXT_INVENTORY_CLIENT_REQUIRED", str(exc)
            ) from exc
        except ClientSupplierRequiredForAisleError as exc:
            raise DinamicScannerTxtImportError(
                "DINAMIC_SCANNER_TXT_CLIENT_SUPPLIER_REQUIRED", str(exc)
            ) from exc
        return created, True
