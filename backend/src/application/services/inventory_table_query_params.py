"""Normalize OpenAPI query params into :class:`InventoryTableQuery` for inventory listing."""

from __future__ import annotations

from src.application.ports.contracts import InventoryTableQuery


def build_inventory_table_query_from_route_params(
    *,
    search: str | None,
    status: str | None,
    sort_by: str,
    sort_dir: str,
    page: int,
    page_size: int,
) -> InventoryTableQuery:
    return InventoryTableQuery(
        search=search.strip() if search and search.strip() else None,
        status=status.strip() if status and str(status).strip() else None,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        page_size=page_size,
    )
