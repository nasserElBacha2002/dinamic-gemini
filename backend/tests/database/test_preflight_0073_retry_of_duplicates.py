"""Unit tests for migration 0073 preflight duplicate detection."""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PREFLIGHT_PATH = _REPO_ROOT / "scripts/ops/preflight_0073_retry_of_duplicates.py"
_spec = importlib.util.spec_from_file_location("preflight_0073_retry_of_duplicates", _PREFLIGHT_PATH)
assert _spec and _spec.loader
_preflight = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _preflight
_spec.loader.exec_module(_preflight)

DuplicateRetryGroup = _preflight.DuplicateRetryGroup
RetryChildRow = _preflight.RetryChildRow
fetch_duplicate_retry_groups = _preflight.fetch_duplicate_retry_groups
format_groups_text = _preflight.format_groups_text
groups_to_json = _preflight.groups_to_json


class _Cursor:
    def __init__(self, parent_groups: list[tuple], children: dict[str, list]) -> None:
        self._parent_groups = parent_groups
        self._children = children
        self._last_parent: str | None = None

    def execute(self, sql: str, params=()) -> None:
        if "GROUP BY retry_of_job_id" in sql:
            self._last_parent = None
            return
        if "WHERE retry_of_job_id = ?" in sql:
            self._last_parent = str(params[0])

    def fetchall(self):
        if self._last_parent is None:
            return [
                SimpleNamespace(retry_of_job_id=pid, child_count=count)
                for pid, count in self._parent_groups
            ]
        rows = self._children.get(self._last_parent, [])
        return [
            SimpleNamespace(id=r[0], status=r[1], created_at=r[2])
            for r in rows
        ]


def test_fetch_duplicate_retry_groups_empty() -> None:
    cur = _Cursor([], {})
    assert fetch_duplicate_retry_groups(cur) == []


def test_fetch_duplicate_retry_groups_with_children() -> None:
    created = datetime(2026, 7, 1, tzinfo=timezone.utc)
    cur = _Cursor([("parent-1", 2)], {
        "parent-1": [
            ("child-a", "failed", created),
            ("child-b", "queued", created),
        ]
    })
    groups = fetch_duplicate_retry_groups(cur)
    assert len(groups) == 1
    group = groups[0]
    assert group.retry_of_job_id == "parent-1"
    assert group.child_count == 2
    assert [c.id for c in group.children] == ["child-a", "child-b"]


def test_format_groups_text_reports_manual_resolution() -> None:
    group = DuplicateRetryGroup(
        retry_of_job_id="p1",
        child_count=2,
        children=(
            RetryChildRow(id="c1", status="queued", created_at="2026-07-01T00:00:00+00:00"),
            RetryChildRow(id="c2", status="failed", created_at="2026-07-02T00:00:00+00:00"),
        ),
    )
    text = format_groups_text([group])
    assert "duplicate retry_of_job_id" in text.lower()
    assert "c1" in text and "c2" in text
    assert "0073_README" in text


def test_groups_to_json_shape() -> None:
    payload = groups_to_json([])
    assert payload["duplicate_group_count"] == 0
    assert payload["groups"] == []
