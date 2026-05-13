"""Tests for :class:`src.application.services.run_auditability_models.RunAuditabilityView.to_jsonable`."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.services.run_auditability_models import (
    RunAuditabilityView,
    RunAuditMetadataSources,
    RunAuditReferenceUsage,
)

_NOW = datetime(2026, 5, 11, 12, 0, 0, tzinfo=timezone.utc)


def test_to_jsonable_serializes_datetimes_and_nested_structures() -> None:
    ru = RunAuditReferenceUsage(
        resolved=True,
        resolved_count=2,
        provider_consumed=False,
        provider_consumed_count=0,
        reference_ids=["a", "b"],
        resolution_error=None,
    )
    view = RunAuditabilityView(
        job_id="j1",
        status="succeeded",
        target_type="aisle",
        target_id="a1",
        created_at=_NOW,
        started_at=_NOW,
        finished_at=None,
        reference_usage=ru,
        metadata_sources=RunAuditMetadataSources(
            job_row=True,
            result_json=True,
            aisle_join=True,
            inventory_join=True,
            hybrid_report=False,
            execution_log=True,
        ),
        missing_metadata=["hybrid_report"],
        legacy_mode=False,
    )
    d = view.to_jsonable()
    assert d["created_at"] == _NOW.isoformat()
    assert d["started_at"] == _NOW.isoformat()
    assert d["finished_at"] is None
    assert d["reference_usage"] is not None
    assert d["reference_usage"]["reference_ids"] == ["a", "b"]
    assert d["metadata_sources"]["hybrid_report"] is False
    assert d["metadata_sources"]["execution_log"] is True
    assert d["metadata_sources"]["run_audit_snapshot"] is False
    assert d["missing_metadata"] == ["hybrid_report"]
    assert d.get("cost_snapshot") is None
    # Lists are copies (mutating d must not mutate view)
    d["missing_metadata"].append("x")
    assert view.missing_metadata == ["hybrid_report"]
