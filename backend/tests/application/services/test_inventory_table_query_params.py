"""Tests for :mod:`src.application.services.inventory_table_query_params`."""

from __future__ import annotations

from src.application.services.inventory_table_query_params import (
    build_inventory_table_query_from_route_params,
)


def test_build_inventory_table_query_strips_search_and_status() -> None:
    q = build_inventory_table_query_from_route_params(
        search="  inv  ",
        status="  draft  ",
        sort_by="name",
        sort_dir="asc",
        page=3,
        page_size=100,
    )
    assert q.search == "inv"
    assert q.status == "draft"
    assert q.sort_by == "name"
    assert q.sort_dir == "asc"
    assert q.page == 3
    assert q.page_size == 100


def test_build_inventory_table_query_none_when_blank() -> None:
    q = build_inventory_table_query_from_route_params(
        search="   ",
        status=None,
        sort_by="created_at",
        sort_dir="desc",
        page=1,
        page_size=25,
    )
    assert q.search is None
    assert q.status is None
