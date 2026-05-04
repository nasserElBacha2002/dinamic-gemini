"""Tests for :mod:`src.application.services.aisle_table_query_params`."""

from __future__ import annotations

from src.application.services.aisle_table_query_params import (
    build_aisle_table_query_from_route_params,
)


def test_build_aisle_table_query_strips_search_and_status() -> None:
    q = build_aisle_table_query_from_route_params(
        search="  abc  ",
        status="  ready  ",
        sort_by="code",
        sort_dir="desc",
        page=2,
        page_size=50,
    )
    assert q.search == "abc"
    assert q.status == "ready"
    assert q.sort_by == "code"
    assert q.sort_dir == "desc"
    assert q.page == 2
    assert q.page_size == 50


def test_build_aisle_table_query_none_when_blank() -> None:
    q = build_aisle_table_query_from_route_params(
        search="   ",
        status=None,
        sort_by="status",
        sort_dir="asc",
        page=1,
        page_size=25,
    )
    assert q.search is None
    assert q.status is None
