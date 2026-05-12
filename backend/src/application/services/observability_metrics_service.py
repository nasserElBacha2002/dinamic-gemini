"""Aggregate read-only observability metrics from jobs and joins (Phase H5).

Does not scan execution logs or hybrid reports. Uses job row, aisle/inventory joins,
``result_json.run_audit_snapshot`` (H4), and ``visual_reference_context`` when present.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from src.application.ports.repositories import AisleRepository, InventoryRepository, JobRepository
from src.application.services.reference_usage_from_job_result import (
    VISUAL_REFERENCE_CONTEXT_RESULT_JSON_KEY,
)
from src.application.services.run_audit_snapshot import RUN_AUDIT_SNAPSHOT_SCHEMA_VERSION
from src.application.services.supplier_prompt_resolver import SupplierPromptFallbackReason
from src.domain.jobs.entities import Job, JobStatus
from src.pipeline.run_metadata import RUN_METADATA_KEY_RUN_AUDIT_SNAPSHOT

logger = logging.getLogger(__name__)

DEFAULT_RANGE_DAYS = 30
MAX_RANGE_DAYS = 90
METRICS_JOB_LIMIT = 5000
AISLE_TARGET = "aisle"
PROCESS_AISLE_JOB_TYPE = "process_aisle"


@dataclass(frozen=True)
class ObservabilityMetricsFilters:
    created_from: datetime
    created_to: datetime
    client_id: str | None = None
    client_supplier_id: str | None = None
    provider_name: str | None = None
    model_name: str | None = None


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def resolve_metrics_time_range(
    from_raw: datetime | None,
    to_raw: datetime | None,
) -> tuple[datetime, datetime]:
    """Default last 30 days ending at ``to_raw`` or now; enforce max 90 days."""
    now = datetime.now(timezone.utc)
    to_dt = _utc(to_raw) if to_raw is not None else now
    from_dt = _utc(from_raw) if from_raw is not None else to_dt - timedelta(days=DEFAULT_RANGE_DAYS)
    if from_dt > to_dt:
        raise ValueError("from_after_to")
    if (to_dt - from_dt) > timedelta(days=MAX_RANGE_DAYS):
        raise ValueError("range_too_large")
    return from_dt, to_dt


def _is_terminal(status: JobStatus) -> bool:
    return status in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELED)


def _strip(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _h4_snapshot(result_json: dict[str, Any] | None) -> dict[str, Any] | None:
    if not result_json:
        return None
    raw = result_json.get(RUN_METADATA_KEY_RUN_AUDIT_SNAPSHOT)
    if not isinstance(raw, dict):
        return None
    if raw.get("schema_version") != RUN_AUDIT_SNAPSHOT_SCHEMA_VERSION:
        return None
    return raw


def _provider_model_for_job(job: Job, snap: dict[str, Any] | None) -> tuple[str | None, str | None]:
    p = _strip(snap.get("provider_name") if snap else None) or _strip(job.provider_name)
    m = _strip(snap.get("model_name") if snap else None) or _strip(job.model_name)
    return p, m


def _client_supplier_for_job(
    job: Job,
    snap: dict[str, Any] | None,
    aisle_repo: AisleRepository,
    inventory_repo: InventoryRepository,
) -> tuple[str | None, str | None]:
    join_client: str | None = None
    join_supplier: str | None = None
    if job.target_type == AISLE_TARGET and job.target_id:
        aisle = aisle_repo.get_by_id(str(job.target_id).strip())
        if aisle is not None:
            join_supplier = _strip(getattr(aisle, "client_supplier_id", None))
            inv = inventory_repo.get_by_id(aisle.inventory_id)
            if inv is not None:
                join_client = _strip(getattr(inv, "client_id", None))
    snap_client = _strip(snap.get("client_id")) if snap else None
    snap_supplier = _strip(snap.get("client_supplier_id")) if snap else None
    client_id = join_client or snap_client
    supplier_id = join_supplier or snap_supplier
    return client_id, supplier_id


def _passes_filters(
    *,
    client_id: str | None,
    supplier_id: str | None,
    provider: str | None,
    model: str | None,
    filters: ObservabilityMetricsFilters,
) -> bool:
    if filters.client_id and _strip(filters.client_id) != client_id:
        return False
    if filters.client_supplier_id and _strip(filters.client_supplier_id) != supplier_id:
        return False
    if filters.provider_name and _strip(filters.provider_name) != provider:
        return False
    if filters.model_name and _strip(filters.model_name) != model:
        return False
    return True


def _missing_reference_succeeded(job: Job, snap: dict[str, Any] | None) -> bool:
    if job.status != JobStatus.SUCCEEDED:
        return False
    if snap:
        src = _strip(snap.get("reference_source"))
        if src == "supplier_reference_images":
            cnt = snap.get("reference_image_count")
            used = snap.get("supplier_reference_images_used")
            if isinstance(cnt, int) and cnt <= 0:
                return True
            if used is False:
                return True
        return False
    rj = job.result_json if isinstance(job.result_json, dict) else {}
    vrc = rj.get(VISUAL_REFERENCE_CONTEXT_RESULT_JSON_KEY)
    if isinstance(vrc, dict):
        if vrc.get("resolution_error"):
            return True
        if vrc.get("resolved") is False:
            return True
    return False


def _missing_prompt_succeeded(
    job: Job, snap: dict[str, Any] | None, client_id: str | None
) -> bool:
    if job.status != JobStatus.SUCCEEDED:
        return False
    if not client_id:
        return False
    if not snap:
        return False
    spid = _strip(snap.get("supplier_prompt_config_id"))
    if spid:
        return False
    if snap.get("supplier_prompt_fallback_used") is True:
        return True
    reason = _strip(snap.get("supplier_prompt_fallback_reason"))
    if reason == SupplierPromptFallbackReason.NO_ACTIVE_SUPPLIER_PROMPT_CONFIG:
        return True
    return bool(snap.get("prompt_composition_available"))


def _fallback_run(snap: dict[str, Any] | None) -> bool:
    if not snap:
        return False
    return snap.get("supplier_prompt_fallback_used") is True


def _rate(num: int, den: int) -> float | None:
    if den <= 0:
        return None
    return round(num / den, 4)


class ObservabilityMetricsService:
    """Read-only metrics over v3 aisle processing jobs."""

    def __init__(
        self,
        *,
        job_repo: JobRepository,
        aisle_repo: AisleRepository,
        inventory_repo: InventoryRepository,
    ) -> None:
        self._job_repo = job_repo
        self._aisle_repo = aisle_repo
        self._inventory_repo = inventory_repo

    def build(self, filters: ObservabilityMetricsFilters) -> dict[str, Any]:
        jobs = self._job_repo.list_jobs_for_metrics(
            created_from=filters.created_from,
            created_to=filters.created_to,
            job_type=PROCESS_AISLE_JOB_TYPE,
            target_type=AISLE_TARGET,
            limit=METRICS_JOB_LIMIT,
        )
        if len(jobs) >= METRICS_JOB_LIMIT:
            logger.info(
                "observability_metrics_row_cap_hit limit=%s from=%s to=%s",
                METRICS_JOB_LIMIT,
                filters.created_from.isoformat(),
                filters.created_to.isoformat(),
            )

        terminal_jobs: list[tuple[Job, dict[str, Any] | None, str | None, str | None, str | None, str | None]] = []
        for job in jobs:
            snap = _h4_snapshot(job.result_json if isinstance(job.result_json, dict) else None)
            client_id, supplier_id = _client_supplier_for_job(
                job, snap, self._aisle_repo, self._inventory_repo
            )
            prov, model = _provider_model_for_job(job, snap)
            if not _passes_filters(
                client_id=client_id,
                supplier_id=supplier_id,
                provider=prov,
                model=model,
                filters=filters,
            ):
                continue
            if _is_terminal(job.status):
                terminal_jobs.append((job, snap, client_id, supplier_id, prov, model))

        runs_total = len(terminal_jobs)
        runs_succeeded = sum(1 for j, _, _, _, _, _ in terminal_jobs if j.status == JobStatus.SUCCEEDED)
        runs_failed = sum(
            1 for j, _, _, _, _, _ in terminal_jobs if j.status in (JobStatus.FAILED, JobStatus.CANCELED)
        )
        success_rate = _rate(runs_succeeded, runs_total)
        failure_rate = _rate(runs_failed, runs_total)

        legacy_runs = sum(1 for _, s, _, _, _, _ in terminal_jobs if s is None)
        with_snap = runs_total - legacy_runs

        fallback_runs = sum(1 for j, s, _, _, _, _ in terminal_jobs if j.status == JobStatus.SUCCEEDED and _fallback_run(s))
        missing_prompt_config_runs = sum(
            1 for j, s, c, _, _, _ in terminal_jobs if _missing_prompt_succeeded(j, s, c)
        )
        missing_reference_runs = sum(
            1 for j, s, _, _, _, _ in terminal_jobs if _missing_reference_succeeded(j, s)
        )

        jobs_with_audit_snapshot = with_snap
        jobs_without_audit_snapshot = legacy_runs
        jobs_with_missing_metadata = sum(
            1
            for j, s, c, _, _, _ in terminal_jobs
            if j.status == JobStatus.SUCCEEDED and (s is None or (s is not None and not _strip(s.get("supplier_prompt_config_id")) and c))
        )
        artifact_dependent_jobs = sum(1 for _, s, _, _, _, _ in terminal_jobs if s is None)

        by_client: dict[str | None, dict[str, int]] = defaultdict(
            lambda: {"runs_total": 0, "runs_succeeded": 0, "runs_failed": 0}
        )
        by_supplier: dict[str | None, dict[str, Any]] = {}
        by_pm: dict[tuple[str | None, str | None], dict[str, int]] = defaultdict(
            lambda: {"runs_total": 0, "runs_succeeded": 0, "runs_failed": 0}
        )

        for job, snap, cid, csid, prov, model in terminal_jobs:
            by_client[cid]["runs_total"] += 1
            if job.status == JobStatus.SUCCEEDED:
                by_client[cid]["runs_succeeded"] += 1
            elif job.status in (JobStatus.FAILED, JobStatus.CANCELED):
                by_client[cid]["runs_failed"] += 1

            sk = csid
            if sk not in by_supplier:
                by_supplier[sk] = {
                    "client_supplier_id": csid,
                    "client_id": cid,
                    "runs_total": 0,
                    "runs_succeeded": 0,
                    "runs_failed": 0,
                    "fallback_runs": 0,
                    "missing_reference_runs": 0,
                }
            b = by_supplier[sk]
            b["runs_total"] += 1
            if job.status == JobStatus.SUCCEEDED:
                b["runs_succeeded"] += 1
            elif job.status in (JobStatus.FAILED, JobStatus.CANCELED):
                b["runs_failed"] += 1
            if job.status == JobStatus.SUCCEEDED and _fallback_run(snap):
                b["fallback_runs"] += 1
            if _missing_reference_succeeded(job, snap):
                b["missing_reference_runs"] += 1

            pm_key = (prov, model)
            by_pm[pm_key]["runs_total"] += 1
            if job.status == JobStatus.SUCCEEDED:
                by_pm[pm_key]["runs_succeeded"] += 1
            elif job.status in (JobStatus.FAILED, JobStatus.CANCELED):
                by_pm[pm_key]["runs_failed"] += 1

        def client_rows() -> list[dict[str, Any]]:
            rows: list[dict[str, Any]] = []
            for cid, v in sorted(by_client.items(), key=lambda x: (-x[1]["runs_total"], x[0] or "")):
                rt = v["runs_total"]
                rf = v["runs_failed"]
                rows.append(
                    {
                        "client_id": cid,
                        "runs_total": rt,
                        "runs_succeeded": v["runs_succeeded"],
                        "runs_failed": rf,
                        "failure_rate": _rate(rf, rt),
                    }
                )
            return rows

        def supplier_rows() -> list[dict[str, Any]]:
            rows: list[dict[str, Any]] = []
            for csid in sorted(by_supplier.keys(), key=lambda k: (-by_supplier[k]["runs_total"], k or "")):
                v = by_supplier[csid]
                rt = v["runs_total"]
                rf = v["runs_failed"]
                rows.append(
                    {
                        "client_supplier_id": v["client_supplier_id"],
                        "client_id": v["client_id"],
                        "runs_total": rt,
                        "runs_succeeded": v["runs_succeeded"],
                        "runs_failed": rf,
                        "fallback_runs": v["fallback_runs"],
                        "missing_reference_runs": v["missing_reference_runs"],
                        "failure_rate": _rate(rf, rt),
                    }
                )
            return rows

        def pm_rows() -> list[dict[str, Any]]:
            rows: list[dict[str, Any]] = []
            for (p, m), v in sorted(by_pm.items(), key=lambda x: (-x[1]["runs_total"], x[0][0] or "", x[0][1] or "")):
                rt = v["runs_total"]
                rf = v["runs_failed"]
                rows.append(
                    {
                        "provider_name": p,
                        "model_name": m,
                        "runs_total": rt,
                        "runs_succeeded": v["runs_succeeded"],
                        "runs_failed": rf,
                        "failure_rate": _rate(rf, rt),
                    }
                )
            return rows

        return {
            "range": {
                "from": filters.created_from.isoformat().replace("+00:00", "Z"),
                "to": filters.created_to.isoformat().replace("+00:00", "Z"),
            },
            "filters": {
                "client_id": filters.client_id,
                "client_supplier_id": filters.client_supplier_id,
                "provider_name": filters.provider_name,
                "model_name": filters.model_name,
            },
            "totals": {
                "runs_total": runs_total,
                "runs_succeeded": runs_succeeded,
                "runs_failed": runs_failed,
                "success_rate": success_rate,
                "failure_rate": failure_rate,
                "fallback_runs": fallback_runs,
                "missing_prompt_config_runs": missing_prompt_config_runs,
                "missing_reference_runs": missing_reference_runs,
                "legacy_runs": legacy_runs,
            },
            "by_client": client_rows(),
            "by_supplier": supplier_rows(),
            "by_provider_model": pm_rows(),
            "data_quality": {
                "jobs_with_audit_snapshot": jobs_with_audit_snapshot,
                "jobs_without_audit_snapshot": jobs_without_audit_snapshot,
                "jobs_with_missing_metadata": jobs_with_missing_metadata,
                "artifact_dependent_jobs": artifact_dependent_jobs,
            },
        }
