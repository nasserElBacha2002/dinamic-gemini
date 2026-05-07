"""v3 clients CRUD (Phase A1: create/get/list)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.constants.route_paths import API_V3_CLIENTS_ROUTER_PREFIX
from src.api.dependencies import (
    get_create_client_use_case,
    get_get_client_use_case,
    get_list_clients_use_case,
)
from src.api.errors import reraise_if_mapped
from src.api.schemas.client_schemas import (
    ClientResponse,
    CreateClientRequest,
    PaginatedClientListResponse,
)
from src.api.schemas.listing_schemas import compute_total_pages
from src.application.errors import InvalidClientNameError
from src.application.use_cases.create_client import CreateClientCommand, CreateClientUseCase
from src.application.use_cases.get_client import GetClientUseCase
from src.application.use_cases.list_clients import ListClientsUseCase
from src.auth.dependencies import get_current_admin
from src.domain.client.entities import Client, ClientStatus

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

