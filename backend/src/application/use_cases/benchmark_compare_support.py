"""Pure helpers for Phase 6 benchmark compare (same-aisle, explicit job ids).

Cross-run alignment is **heuristic**, not guaranteed physical entity matching. After per-run
SKU consolidation, each consolidated row gets a ``cross_run_match_key``: prefer normalized
``internal_code`` (``sku:...``), else a position-code key from corrected code or detected
``position_barcode`` / ``pallet_id`` / ``entity_uid`` (``pos:...``), else a per-run fallback
``row:<position_id>``. When SKU or position identity shifts between runs, the same real-world
item may show as ``only_a`` / ``only_b`` rather than ``both_changed`` because no stable shared
key was derived.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from src.application.mappers.inventory_export_rows import export_position_code
from src.application.services.position_sku_consolidation import (
    canonical_internal_code_lower,
    consolidate_positions_by_sku,
    position_quantity_from_summary,
)
from src.domain.jobs.entities import Job
from src.domain.positions.entities import Position, PositionStatus


def sanitize_llm_cost_snapshot_for_compare(snapshot: dict[str, object]) -> dict[str, object]:
    """Drop bulky audit-only fields from usage before returning compare API payloads."""
    out = dict(snapshot)
    usage = out.get("usage")
    if isinstance(usage, dict) and "raw_provider_usage_json" in usage:
        out["usage"] = {k: v for k, v in usage.items() if k != "raw_provider_usage_json"}
    return out


def _position_code_key(p: Position) -> str:
    c = (p.corrected_position_code or "").strip().lower()
    if c:
        return c
    summary = p.detected_summary_json if isinstance(p.detected_summary_json, dict) else {}
    for k in ("position_barcode", "pallet_id", "entity_uid"):
        v = summary.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip().lower()
    return ""


def cross_run_match_key(p: Position) -> str:
    """Best-effort key to pair consolidated rows across runs (heuristic; see module docstring)."""
    sku = canonical_internal_code_lower(p)
    if sku:
        return f"sku:{sku}"
    pc = _position_code_key(p)
    if pc:
        return f"pos:{pc}"
    return f"row:{p.id}"


@dataclass(frozen=True)
class ConsolidatedRowSig:
    key: str
    quantity: int
    sku_lower: str
    position_code: str
    needs_review: bool


def signatures_for_consolidated(
    consolidated: Sequence[Position],
) -> Dict[str, ConsolidatedRowSig]:
    out: Dict[str, ConsolidatedRowSig] = {}
    for p in consolidated:
        key = cross_run_match_key(p)
        out[key] = ConsolidatedRowSig(
            key=key,
            quantity=position_quantity_from_summary(p),
            sku_lower=canonical_internal_code_lower(p),
            position_code=export_position_code(p),
            needs_review=bool(p.needs_review),
        )
    return out


def load_consolidated_for_job_slice(
    *,
    positions: Sequence[Position],
) -> List[Position]:
    active = [p for p in positions if p.status != PositionStatus.DELETED]
    return consolidate_positions_by_sku(active)


@dataclass(frozen=True)
class RunAggregateMetrics:
    raw_rows_considered: int
    consolidated_positions: int
    total_quantity: int
    unknown_internal_code_count: int
    needs_review_count: int


def aggregate_metrics(consolidated: Sequence[Position], *, raw_fetched: int) -> RunAggregateMetrics:
    unk = sum(1 for p in consolidated if not canonical_internal_code_lower(p))
    nr = sum(1 for p in consolidated if p.needs_review)
    tq = sum(position_quantity_from_summary(p) for p in consolidated)
    return RunAggregateMetrics(
        raw_rows_considered=raw_fetched,
        consolidated_positions=len(consolidated),
        total_quantity=int(tq),
        unknown_internal_code_count=int(unk),
        needs_review_count=int(nr),
    )


@dataclass(frozen=True)
class CompareDiffSummary:
    keys_only_in_a: int
    keys_only_in_b: int
    keys_in_both: int
    quantity_changed: int
    sku_changed: int
    position_code_changed: int


def compute_compare_diff(
    sig_a: Mapping[str, ConsolidatedRowSig],
    sig_b: Mapping[str, ConsolidatedRowSig],
) -> CompareDiffSummary:
    keys_a = set(sig_a.keys())
    keys_b = set(sig_b.keys())
    only_a = keys_a - keys_b
    only_b = keys_b - keys_a
    both = keys_a & keys_b
    qty_d = 0
    sku_d = 0
    pos_d = 0
    for k in both:
        ra, rb = sig_a[k], sig_b[k]
        if ra.quantity != rb.quantity:
            qty_d += 1
        if ra.sku_lower != rb.sku_lower:
            sku_d += 1
        if ra.position_code.strip().lower() != rb.position_code.strip().lower():
            pos_d += 1
    return CompareDiffSummary(
        keys_only_in_a=len(only_a),
        keys_only_in_b=len(only_b),
        keys_in_both=len(both),
        quantity_changed=qty_d,
        sku_changed=sku_d,
        position_code_changed=pos_d,
    )


@dataclass(frozen=True)
class CompareDiffRow:
    match_key: str
    side: str
    quantity_a: int | None
    quantity_b: int | None
    sku_a: str | None
    sku_b: str | None
    position_code_a: str | None
    position_code_b: str | None


def build_compare_diff_rows(
    sig_a: Mapping[str, ConsolidatedRowSig],
    sig_b: Mapping[str, ConsolidatedRowSig],
    *,
    max_rows: int,
) -> Tuple[List[CompareDiffRow], bool]:
    rows: List[CompareDiffRow] = []
    keys_a = set(sig_a.keys())
    keys_b = set(sig_b.keys())
    for k in sorted(keys_a - keys_b):
        s = sig_a[k]
        rows.append(
            CompareDiffRow(
                match_key=k,
                side="only_a",
                quantity_a=s.quantity,
                quantity_b=None,
                sku_a=s.sku_lower or None,
                sku_b=None,
                position_code_a=s.position_code or None,
                position_code_b=None,
            )
        )
        if len(rows) >= max_rows:
            return rows, True
    for k in sorted(keys_b - keys_a):
        s = sig_b[k]
        rows.append(
            CompareDiffRow(
                match_key=k,
                side="only_b",
                quantity_a=None,
                quantity_b=s.quantity,
                sku_a=None,
                sku_b=s.sku_lower or None,
                position_code_a=None,
                position_code_b=s.position_code or None,
            )
        )
        if len(rows) >= max_rows:
            return rows, True
    for k in sorted(keys_a & keys_b):
        ra, rb = sig_a[k], sig_b[k]
        changed = (
            ra.quantity != rb.quantity
            or ra.sku_lower != rb.sku_lower
            or ra.position_code.strip().lower() != rb.position_code.strip().lower()
        )
        if not changed:
            continue
        rows.append(
            CompareDiffRow(
                match_key=k,
                side="both_changed",
                quantity_a=ra.quantity,
                quantity_b=rb.quantity,
                sku_a=ra.sku_lower or None,
                sku_b=rb.sku_lower or None,
                position_code_a=ra.position_code or None,
                position_code_b=rb.position_code or None,
            )
        )
        if len(rows) >= max_rows:
            return rows, True
    return rows, False


def job_execution_duration_seconds(job: Job) -> Optional[float]:
    """Wall-clock processing duration when both timestamps exist and are coherent."""
    if job.started_at is None or job.finished_at is None:
        return None
    delta = job.finished_at - job.started_at
    secs = float(delta.total_seconds())
    if secs < 0:
        return None
    return secs


def format_execution_duration_human(seconds: float) -> str:
    """Stable operator-facing duration (wall clock), not locale-aware."""
    if not math.isfinite(seconds) or seconds < 0:
        return ""
    if seconds < 60:
        text = f"{seconds:.1f}".rstrip("0").rstrip(".")
        return f"{text}s"
    total = int(round(seconds))
    minutes, sec = divmod(total, 60)
    if sec == 0:
        return f"{minutes}m"
    return f"{minutes}m {sec:02d}s"


def job_execution_duration_human(job: Job) -> Optional[str]:
    secs = job_execution_duration_seconds(job)
    if secs is None:
        return None
    return format_execution_duration_human(secs)


def job_metadata_dict(job: Job) -> dict[str, object | None]:
    llm_cost_snapshot = None
    if isinstance(job.result_json, dict):
        raw_snapshot = job.result_json.get("llm_cost_snapshot")
        if isinstance(raw_snapshot, dict):
            llm_cost_snapshot = sanitize_llm_cost_snapshot_for_compare(raw_snapshot)
    return {
        "job_id": job.id,
        "status": job.status.value,
        "provider_name": job.provider_name,
        "model_name": job.model_name,
        "prompt_key": job.prompt_key,
        "prompt_version": job.prompt_version,
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "execution_time_seconds": job_execution_duration_seconds(job),
        "execution_time_human": job_execution_duration_human(job),
        "llm_cost_snapshot": llm_cost_snapshot,
    }


def compare_csv_row_dict(r: CompareDiffRow) -> dict[str, object | None]:
    return {
        "match_key": r.match_key,
        "side": r.side,
        "quantity_a": r.quantity_a,
        "quantity_b": r.quantity_b,
        "delta_quantity": (
            (r.quantity_b - r.quantity_a)
            if r.quantity_a is not None and r.quantity_b is not None
            else None
        ),
        "sku_a": r.sku_a,
        "sku_b": r.sku_b,
        "position_code_a": r.position_code_a,
        "position_code_b": r.position_code_b,
    }
