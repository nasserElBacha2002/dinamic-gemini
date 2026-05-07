"""v3 clients CRUD (Phase A1: create/get/list)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.constants.route_paths import API_V3_CLIENTS_ROUTER_PREFIX
from src.api.dependencies import (
    get_create_client_supplier_use_case,
    get_create_client_use_case,
    get_get_client_supplier_use_case,
    get_get_client_use_case,
    get_list_client_suppliers_use_case,
    get_list_clients_use_case,
)
from src.api.errors import reraise_if_mapped
from src.api.schemas.client_schemas import (
    ClientResponse,
    CreateClientRequest,
    PaginatedClientListResponse,
)
from src.api.schemas.client_supplier_schemas import (
    ClientSupplierResponse,
    CreateClientSupplierRequest,
    PaginatedClientSupplierListResponse,
)
from src.api.schemas.listing_schemas import compute_total_pages
from src.application.errors import (
    DuplicateClientSupplierNameError,
    InvalidClientNameError,
    InvalidClientSupplierNameError,
)
from src.application.use_cases.create_client import CreateClientCommand, CreateClientUseCase
from src.application.use_cases.create_client_supplier import (
    CreateClientSupplierCommand,
    CreateClientSupplierUseCase,
)
from src.application.use_cases.get_client import GetClientUseCase
from src.application.use_cases.get_client_supplier import GetClientSupplierUseCase
from src.application.use_cases.list_client_suppliers import ListClientSuppliersUseCase
from src.application.use_cases.list_clients import ListClientsUseCase
from src.auth.dependencies import get_current_admin
from src.domain.client.entities import Client, ClientStatus
from src.domain.client_supplier.entities import ClientSupplier, ClientSupplierStatus

router = APIRouter(
    prefix=API_V3_CLIENTS_ROUTER_PREFIX,
    tags=["clients-v3"],
    dependencies=[Depends(get_current_admin)],
)


def _to_response(client: Client) -> ClientResponse:
    return ClientResponse(
        id=client.id,
        name=client.name,
        status=client.status.value,
        created_at=client.created_at,
        updated_at=client.updated_at,
    )


def _to_supplier_response(supplier: ClientSupplier) -> ClientSupplierResponse:
    return ClientSupplierResponse(
        id=supplier.id,
        client_id=supplier.client_id,
        name=supplier.name,
        status=supplier.status.value,
        created_at=supplier.created_at,
        updated_at=supplier.updated_at,
    )


@router.post("/", response_model=ClientResponse, status_code=201)
def create_client(
    payload: CreateClientRequest,
    use_case: CreateClientUseCase = Depends(get_create_client_use_case),
) -> ClientResponse:
    try:
        client = use_case.execute(
            CreateClientCommand(name=payload.name, status=ClientStatus(payload.status))
        )
    except InvalidClientNameError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return _to_response(client)


@router.get("/", response_model=PaginatedClientListResponse)
def list_clients(
    use_case: ListClientsUseCase = Depends(get_list_clients_use_case),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
) -> PaginatedClientListResponse:
    rows = list(use_case.execute())
    total = len(rows)
    start = (page - 1) * page_size
    end = start + page_size
    window = rows[start:end]
    return PaginatedClientListResponse(
        items=[_to_response(item) for item in window],
        page=page,
        page_size=page_size,
        total_items=total,
        total_pages=compute_total_pages(total, page_size),
    )


@router.get("/{client_id}", response_model=ClientResponse)
def get_client(
    client_id: str,
    use_case: GetClientUseCase = Depends(get_get_client_use_case),
) -> ClientResponse:
    try:
        client = use_case.execute(client_id)
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return _to_response(client)


@router.post("/{client_id}/suppliers", response_model=ClientSupplierResponse, status_code=201)
def create_client_supplier(
    client_id: str,
    payload: CreateClientSupplierRequest,
    use_case: CreateClientSupplierUseCase = Depends(get_create_client_supplier_use_case),
) -> ClientSupplierResponse:
    try:
        supplier = use_case.execute(
            CreateClientSupplierCommand(
                client_id=client_id,
                name=payload.name,
                status=ClientSupplierStatus(payload.status),
            )
        )
    except InvalidClientSupplierNameError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except DuplicateClientSupplierNameError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return _to_supplier_response(supplier)


@router.get("/{client_id}/suppliers", response_model=PaginatedClientSupplierListResponse)
def list_client_suppliers(
    client_id: str,
    use_case: ListClientSuppliersUseCase = Depends(get_list_client_suppliers_use_case),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
) -> PaginatedClientSupplierListResponse:
    try:
        rows = list(use_case.execute(client_id))
    except Exception as e:
        reraise_if_mapped(e)
        raise
    total = len(rows)
    start = (page - 1) * page_size
    end = start + page_size
    window = rows[start:end]
    return PaginatedClientSupplierListResponse(
        items=[_to_supplier_response(item) for item in window],
        page=page,
        page_size=page_size,
        total_items=total,
        total_pages=compute_total_pages(total, page_size),
    )


@router.get("/{client_id}/suppliers/{supplier_id}", response_model=ClientSupplierResponse)
def get_client_supplier(
    client_id: str,
    supplier_id: str,
    use_case: GetClientSupplierUseCase = Depends(get_get_client_supplier_use_case),
) -> ClientSupplierResponse:
    try:
        supplier = use_case.execute(client_id, supplier_id)
    except Exception as e:
        reraise_if_mapped(e)
        raise
    return _to_supplier_response(supplier)

