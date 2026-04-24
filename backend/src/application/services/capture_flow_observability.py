"""G7 — structured JSON logs and lightweight in-process metrics for capture grouping flows."""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


LOG_OP_G3_COMPUTE_GROUPS = "G3_compute_groups"
LOG_OP_G4_ASSIGN_GROUP_EXISTING_AISLE = "G4_assign_group_existing_aisle"
LOG_OP_G4_ASSIGN_GROUP_CREATE_AISLE = "G4_assign_group_create_aisle"
LOG_OP_G5_MATERIALIZE_GROUP = "G5_materialize_group"
LOG_OP_G5_MATERIALIZE_ALL_GROUPS = "G5_materialize_all_groups"
LOG_OP_G6_PREVIEW_GROUP = "G6_preview_group"

RESULT_SUCCESS = "success"
RESULT_PARTIAL = "partial"
RESULT_FAILED = "failed"


def emit_capture_flow_event(
    *,
    logger: logging.Logger,
    inventory_id: str,
    session_id: str,
    operation: str,
    result_status: str,
    counts: Mapping[str, int] | None = None,
    group_id: str | None = None,
    aisle_id: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> None:
    """Emit one machine-readable JSON object per line (INFO)."""
    payload: dict[str, Any] = {
        "inventory_id": (inventory_id or "").strip(),
        "session_id": (session_id or "").strip(),
        "operation": operation,
        "result_status": result_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if group_id:
        payload["group_id"] = (group_id or "").strip()
    if aisle_id:
        payload["aisle_id"] = (aisle_id or "").strip()
    if counts:
        payload["counts"] = {k: int(v) for k, v in counts.items()}
    if extra:
        for k, v in extra.items():
            if v is not None:
                payload[k] = v
    payload["metrics"] = get_capture_flow_metrics().snapshot()
    logger.info("%s", json.dumps(payload, default=str))


@dataclass
class CaptureFlowMetricsRegistry:
    """Thread-safe counters for G7 operational visibility (no external metrics backend)."""

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    materializations_total: int = 0
    previews_total: int = 0
    g3_compute_groups_total: int = 0
    g4_assignments_total: int = 0
    failures_by_phase: dict[str, int] = field(default_factory=dict)
    materialization_asset_created_total: int = 0
    materialization_group_runs_with_items: int = 0
    materialization_imported_items_total: int = 0

    def record_g3_compute(self) -> None:
        with self._lock:
            self.g3_compute_groups_total += 1

    def record_g4_assign(self) -> None:
        with self._lock:
            self.g4_assignments_total += 1

    def record_materialization(
        self,
        *,
        created: int,
        skipped: int,
        failed: int,
        imported_item_count: int,
        failed_whole_group: bool = False,
    ) -> None:
        with self._lock:
            self.materializations_total += 1
            self.materialization_asset_created_total += int(created)
            if imported_item_count > 0:
                self.materialization_group_runs_with_items += 1
                self.materialization_imported_items_total += int(imported_item_count)
            self._bump("G5", failed_whole_group or failed > 0)

    def record_preview(self, *, failed: bool = False) -> None:
        with self._lock:
            self.previews_total += 1
            self._bump("G6", failed)

    def _bump(self, phase: str, failed: bool) -> None:
        if failed:
            self.failures_by_phase[phase] = self.failures_by_phase.get(phase, 0) + 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            mg = self.materialization_group_runs_with_items
            avg_items = (
                round(self.materialization_imported_items_total / mg, 4) if mg else 0.0
            )
            mat = self.materializations_total
            avg_assets = (
                round(self.materialization_asset_created_total / mat, 4) if mat else 0.0
            )
            return {
                "materializations_total": self.materializations_total,
                "previews_total": self.previews_total,
                "g3_compute_groups_total": self.g3_compute_groups_total,
                "g4_assignments_total": self.g4_assignments_total,
                "failures_by_phase": dict(self.failures_by_phase),
                "avg_imported_items_per_materialized_group": avg_items,
                "avg_assets_created_per_materialization": avg_assets,
            }

    def reset_for_tests(self) -> None:
        with self._lock:
            self.materializations_total = 0
            self.previews_total = 0
            self.g3_compute_groups_total = 0
            self.g4_assignments_total = 0
            self.failures_by_phase.clear()
            self.materialization_asset_created_total = 0
            self.materialization_group_runs_with_items = 0
            self.materialization_imported_items_total = 0


_METRICS = CaptureFlowMetricsRegistry()


def get_capture_flow_metrics() -> CaptureFlowMetricsRegistry:
    return _METRICS
