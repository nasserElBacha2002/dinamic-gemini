"""Minimal aisle lifecycle providers required as FastAPI dependency seams.

Only ``get_create_aisle_use_case`` lives here so capture providers can depend on
it without importing the public ``src.api.dependencies`` facade. Additional aisle
lifecycle providers remain in ``dependencies.py`` until a later extraction phase.
"""

from __future__ import annotations

from fastapi import Depends

from src.api.deps.infrastructure import get_inventory_status_reconciler
from src.application.ports.clock import Clock
from src.application.ports.repositories import (
    AisleRepository,
    ClientSupplierRepository,
    InventoryRepository,
)
from src.application.services.inventory_status_reconciler import InventoryStatusReconciler
from src.application.use_cases.aisles.create_aisle import CreateAisleUseCase
from src.runtime.v3_deps import (
    get_aisle_repo,
    get_client_supplier_repo,
    get_clock,
    get_inventory_repo,
)


def get_create_aisle_use_case(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    aisle_repo: AisleRepository = Depends(get_aisle_repo),
    client_supplier_repo: ClientSupplierRepository = Depends(get_client_supplier_repo),
    clock: Clock = Depends(get_clock),
    status_reconciler: InventoryStatusReconciler = Depends(get_inventory_status_reconciler),
) -> CreateAisleUseCase:
    return CreateAisleUseCase(
        inventory_repo=inventory_repo,
        aisle_repo=aisle_repo,
        client_supplier_repo=client_supplier_repo,
        clock=clock,
        status_reconciler=status_reconciler,
    )
