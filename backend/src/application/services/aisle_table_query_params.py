"""Normalize OpenAPI query params into :class:`AisleTableQuery` for aisle listing."""

from __future__ import annotations

from src.application.ports.contracts import AisleTableQuery


def build_aisle_table_query_from_route_params(
    *,
    search: str | None,
    status: str | None,
    sort_by: str,
    sort_dir: str,
    page: int,
    page_size: int,
) -> AisleTableQuery:
    return AisleTableQuery(
        search=search.strip() if search and search.strip() else None,
        status=status.strip() if status and str(status).strip() else None,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        page_size=page_size,
    )
