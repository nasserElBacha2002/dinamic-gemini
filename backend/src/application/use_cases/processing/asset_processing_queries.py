"""Phase 7 — list / detail read models for per-asset processing observability."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from src.application.errors import (
    InventoryNotFoundError,
    JobDoesNotBelongToAisleError,
    JobNotFoundError,
    SourceAssetNotFoundForAisleError,
)
from src.application.ports.external_image_analysis_request_repository import (
    ExternalImageAnalysisRequestRepository,
)
from src.application.ports.image_processing_repositories import (
    JobAssetProcessingStateRepository,
    ProcessingAttemptRepository,
)
from src.application.ports.job_source_asset_repository import JobSourceAssetRepository
from src.application.ports.manual_image_coverage_repository import (
    ManualImageCoverageRepository,
)
from src.application.ports.processing_event_repository import ProcessingEventRepository
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    JobRepository,
    PositionRepository,
    SourceAssetRepository,
)
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.application.services.image_processing.available_asset_actions import (
    compute_available_actions,
)
from src.application.services.image_processing.processing_evidence_sanitizer import (
    sanitize_attempt_view,
    sanitize_metadata,
)
from src.config import load_settings
from src.domain.image_processing.external_image_analysis_request import (
    ExternalRequestStatus,
)
from src.domain.image_processing.processing_attempt import ProcessingAttempt

logger = logging.getLogger(__name__)


@dataclass
class ListAssetProcessingCommand:
    inventory_id: str
    aisle_id: str
    job_id: str
    status: str | None = None
    strategy: str | None = None
    resolved_by: str | None = None
    search: str | None = None
    page: int = 1
    page_size: int = 25
    has_warnings: bool | None = None
    has_fallback: bool | None = None


@dataclass
class GetAssetProcessingDetailCommand:
    inventory_id: str
    aisle_id: str
    job_id: str
    asset_id: str


def _feature_flags() -> dict[str, bool]:
    settings = load_settings()
    return {
        "processing_observability_enabled": bool(
            getattr(settings, "processing_observability_enabled", False)
        ),
        "processing_asset_logs_ui_enabled": bool(
            getattr(settings, "processing_asset_logs_ui_enabled", False)
        ),
        "processing_asset_reprocess_enabled": bool(
            getattr(settings, "processing_asset_reprocess_enabled", False)
        ),
        "processing_manual_actions_enabled": bool(
            getattr(settings, "processing_manual_actions_enabled", False)
        ),
        "processing_events_persistence_enabled": bool(
            getattr(settings, "processing_events_persistence_enabled", False)
        ),
        "external_fallback_per_image_enabled": bool(
            getattr(settings, "external_fallback_per_image_enabled", False)
        ),
    }


def _identification_block(job) -> dict[str, Any]:
    params = job.engine_params_json if isinstance(job.engine_params_json, dict) else {}
    ident = params.get("identification_execution")
    return ident if isinstance(ident, dict) else {}


def _profile_snapshot(job) -> dict[str, Any] | None:
    snap = _identification_block(job).get("supplier_extraction_profile")
    return snap if isinstance(snap, dict) else None


def _requested_mode(job) -> str | None:
    ident = _identification_block(job)
    raw = ident.get("requested_mode")
    if raw:
        return str(raw)
    mode = getattr(job, "identification_mode", None)
    return getattr(mode, "value", str(mode)) if mode is not None else None


def _executed_strategy(job, state_last_strategy: str | None) -> str | None:
    if state_last_strategy:
        return state_last_strategy
    ident = _identification_block(job)
    raw = ident.get("executed_strategy")
    if raw:
        return str(raw)
    strat = getattr(job, "execution_strategy", None)
    return getattr(strat, "value", str(strat)) if strat is not None else None


def _attempt_code_qty(attempt: ProcessingAttempt | None) -> tuple[str | None, float | None]:
    if attempt is None or not isinstance(attempt.normalized_result, dict):
        return None, None
    nr = attempt.normalized_result
    code = nr.get("internal_code")
    qty = nr.get("quantity")
    code_s = str(code).strip() if code is not None else None
    qty_f = float(qty) if isinstance(qty, (int, float)) and not isinstance(qty, bool) else None
    return code_s or None, qty_f


def _thumbnail_url(inventory_id: str, aisle_id: str, asset_id: str, job_id: str) -> str:
    return (
        f"/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets/"
        f"{asset_id}/file?job_id={job_id}"
    )


class ListAssetProcessingUseCase:
    def __init__(
        self,
        *,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        job_repo: JobRepository,
        state_repo: JobAssetProcessingStateRepository,
        attempt_repo: ProcessingAttemptRepository,
        job_source_asset_repo: JobSourceAssetRepository,
        source_asset_repo: SourceAssetRepository,
        external_request_repo: ExternalImageAnalysisRequestRepository | None = None,
        coverage_repo: ManualImageCoverageRepository | None = None,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._job_repo = job_repo
        self._state_repo = state_repo
        self._attempt_repo = attempt_repo
        self._job_source_asset_repo = job_source_asset_repo
        self._source_asset_repo = source_asset_repo
        self._external_request_repo = external_request_repo
        self._coverage_repo = coverage_repo

    def execute(self, command: ListAssetProcessingCommand) -> dict[str, Any]:
        job = self._load_scoped_job(command.inventory_id, command.aisle_id, command.job_id)
        links = list(self._job_source_asset_repo.list_for_job(command.job_id))
        states = {s.asset_id: s for s in self._state_repo.list_by_job(command.job_id)}
        attempts_by_asset: dict[str, list[ProcessingAttempt]] = {}
        for att in self._attempt_repo.list_by_job(command.job_id):
            attempts_by_asset.setdefault(att.asset_id, []).append(att)

        external_by_asset: dict[str, list] = {}
        if self._external_request_repo is not None:
            try:
                for req in self._external_request_repo.list_by_job(command.job_id):
                    external_by_asset.setdefault(req.asset_id, []).append(req)
            except (AttributeError, TypeError, ValueError, OSError) as exc:
                logger.warning(
                    "processing.list_external_requests_failed job_id=%s err=%s",
                    command.job_id,
                    exc,
                )
                external_by_asset = {}

        manual_by_asset: set[str] = set()
        if self._coverage_repo is not None:
            try:
                for cov in self._coverage_repo.list_by_job(command.job_id):
                    manual_by_asset.add(cov.source_asset_id)
            except (AttributeError, TypeError, ValueError, OSError) as exc:
                logger.warning(
                    "processing.list_manual_coverage_failed job_id=%s err=%s",
                    command.job_id,
                    exc,
                )
                manual_by_asset = set()

        items: list[dict[str, Any]] = []
        for link in links:
            asset_id = link.source_asset_id
            state = states.get(asset_id)
            asset = self._source_asset_repo.get_by_id(asset_id)
            file_name = getattr(asset, "file_name", None) if asset else None
            atts = sorted(
                attempts_by_asset.get(asset_id, []),
                key=lambda a: (a.attempt_number, a.created_at),
            )
            latest = atts[-1] if atts else None
            code, qty = _attempt_code_qty(latest)
            ext_reqs = external_by_asset.get(asset_id, [])
            has_fallback = bool(ext_reqs)
            cost = None
            for r in ext_reqs:
                if r.estimated_cost is not None:
                    cost = (cost or 0.0) + float(r.estimated_cost)
            has_manual = asset_id in manual_by_asset

            status = state.status.value if state else "PENDING"
            warnings: list[str] = []
            if latest and isinstance(latest.validation_result, dict):
                raw_w = latest.validation_result.get("warnings")
                if isinstance(raw_w, list):
                    warnings = [str(w) for w in raw_w[:20]]

            summary = {
                "asset_id": asset_id,
                "file_name": file_name,
                "thumbnail_url": _thumbnail_url(
                    command.inventory_id, command.aisle_id, asset_id, command.job_id
                ),
                "status": status,
                "requested_mode": _requested_mode(job),
                "executed_strategy": _executed_strategy(
                    job, state.last_strategy if state else None
                ),
                "resolved_by": (latest.strategy if latest else None),
                "internal_code": code,
                "quantity": qty,
                "attempt_count": state.attempt_count if state else len(atts),
                "last_error_code": (state.error_code if state else None)
                or (latest.error_code if latest else None),
                "warnings": warnings,
                "duration_ms": state.duration_ms if state else None,
                "persistence_status": None,
                "has_fallback": has_fallback,
                "has_manual_result": has_manual,
                "estimated_external_cost": cost,
                "state_version": state.version if state else 0,
            }
            if ext_reqs:
                last_req = ext_reqs[-1]
                summary["persistence_status"] = last_req.status.value

            if not self._matches_filters(command, summary):
                continue
            items.append(summary)

        items.sort(key=lambda x: (x.get("file_name") or x["asset_id"]))
        total = len(items)
        page = max(1, int(command.page))
        page_size = min(200, max(1, int(command.page_size)))
        start = (page - 1) * page_size
        page_items = items[start : start + page_size]

        progress = self._state_repo.aggregate_progress(command.job_id)
        return {
            "items": page_items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "summary": {
                "total": progress.total or total,
                "resolved": progress.resolved,
                "failed": progress.failed,
                "pending": progress.pending,
                "processing": progress.processing,
                "manual_review": progress.manual_review,
                "unrecognized": progress.unrecognized,
                "cancelled": progress.cancelled,
            },
        }

    def _matches_filters(self, command: ListAssetProcessingCommand, row: dict) -> bool:
        if command.status and str(row.get("status")) != command.status:
            return False
        if command.strategy and str(row.get("executed_strategy") or "") != command.strategy:
            return False
        if command.resolved_by and str(row.get("resolved_by") or "") != command.resolved_by:
            return False
        if command.has_warnings is True and not row.get("warnings"):
            return False
        if command.has_warnings is False and row.get("warnings"):
            return False
        if command.has_fallback is True and not row.get("has_fallback"):
            return False
        if command.has_fallback is False and row.get("has_fallback"):
            return False
        if command.search:
            q = command.search.strip().lower()
            blob = " ".join(
                [
                    str(row.get("asset_id") or ""),
                    str(row.get("file_name") or ""),
                    str(row.get("internal_code") or ""),
                ]
            ).lower()
            if q not in blob:
                return False
        return True

    def _load_scoped_job(self, inventory_id: str, aisle_id: str, job_id: str):
        inventory = self._inventory_repo.get_by_id(inventory_id)
        if inventory is None:
            raise InventoryNotFoundError(f"Inventory not found: {inventory_id}")
        aisle = require_aisle_scoped_to_inventory(
            self._aisle_repo, aisle_id=aisle_id, inventory_id=inventory_id
        )
        job = self._job_repo.get_by_id(job_id)
        if job is None:
            raise JobNotFoundError(f"Job not found: {job_id}")
        if job.target_id != aisle.id:
            raise JobDoesNotBelongToAisleError(
                f"Job {job_id} does not belong to aisle {aisle_id}"
            )
        return job


class GetAssetProcessingDetailUseCase:
    def __init__(
        self,
        *,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        job_repo: JobRepository,
        state_repo: JobAssetProcessingStateRepository,
        attempt_repo: ProcessingAttemptRepository,
        job_source_asset_repo: JobSourceAssetRepository,
        source_asset_repo: SourceAssetRepository,
        external_request_repo: ExternalImageAnalysisRequestRepository | None = None,
        coverage_repo: ManualImageCoverageRepository | None = None,
        event_repo: ProcessingEventRepository | None = None,
        position_repo: PositionRepository | None = None,
    ) -> None:
        self._list_uc = ListAssetProcessingUseCase(
            inventory_repo=inventory_repo,
            aisle_repo=aisle_repo,
            job_repo=job_repo,
            state_repo=state_repo,
            attempt_repo=attempt_repo,
            job_source_asset_repo=job_source_asset_repo,
            source_asset_repo=source_asset_repo,
            external_request_repo=external_request_repo,
            coverage_repo=coverage_repo,
        )
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._job_repo = job_repo
        self._state_repo = state_repo
        self._attempt_repo = attempt_repo
        self._job_source_asset_repo = job_source_asset_repo
        self._source_asset_repo = source_asset_repo
        self._external_request_repo = external_request_repo
        self._coverage_repo = coverage_repo
        self._event_repo = event_repo
        self._position_repo = position_repo

    def execute(self, command: GetAssetProcessingDetailCommand) -> dict[str, Any]:
        job = self._list_uc._load_scoped_job(
            command.inventory_id, command.aisle_id, command.job_id
        )
        links = {
            link.source_asset_id: link
            for link in self._job_source_asset_repo.list_for_job(command.job_id)
        }
        if command.asset_id not in links:
            raise SourceAssetNotFoundForAisleError(
                f"Asset {command.asset_id} is not part of job snapshot {command.job_id}"
            )

        state = self._state_repo.get_by_job_and_asset(command.job_id, command.asset_id)
        historical_incomplete = state is None and not any(
            True for _ in self._attempt_repo.list_by_job_and_asset(command.job_id, command.asset_id)
        )

        listed = self._list_uc.execute(
            ListAssetProcessingCommand(
                inventory_id=command.inventory_id,
                aisle_id=command.aisle_id,
                job_id=command.job_id,
                search=command.asset_id,
                page=1,
                page_size=1,
            )
        )
        asset_summary = next(
            (i for i in listed["items"] if i["asset_id"] == command.asset_id),
            None,
        )
        if asset_summary is None:
            asset = self._source_asset_repo.get_by_id(command.asset_id)
            asset_summary = {
                "asset_id": command.asset_id,
                "file_name": getattr(asset, "file_name", None) if asset else None,
                "thumbnail_url": _thumbnail_url(
                    command.inventory_id,
                    command.aisle_id,
                    command.asset_id,
                    command.job_id,
                ),
                "status": state.status.value if state else "UNKNOWN",
                "requested_mode": _requested_mode(job),
                "executed_strategy": _executed_strategy(
                    job, state.last_strategy if state else None
                ),
                "resolved_by": None,
                "internal_code": None,
                "quantity": None,
                "attempt_count": state.attempt_count if state else 0,
                "last_error_code": state.error_code if state else None,
                "warnings": [],
                "duration_ms": state.duration_ms if state else None,
                "persistence_status": None,
                "has_fallback": False,
                "has_manual_result": False,
                "estimated_external_cost": None,
                "state_version": state.version if state else 0,
            }

        attempts = [
            sanitize_attempt_view(
                {
                    "id": a.id,
                    "attempt_number": a.attempt_number,
                    "strategy": a.strategy,
                    "provider": a.provider,
                    "model": a.model,
                    "status": a.status.value,
                    "started_at": a.started_at.isoformat() if a.started_at else None,
                    "finished_at": a.finished_at.isoformat() if a.finished_at else None,
                    "duration_ms": a.duration_ms,
                    "error_code": a.error_code,
                    "error_message": a.error_message,
                    "normalized_result": a.normalized_result,
                    "validation_result": a.validation_result,
                    "execution_scope": a.execution_scope,
                }
            )
            for a in self._attempt_repo.list_by_job_and_asset(
                command.job_id, command.asset_id
            )
        ]

        external_requests: list[dict[str, Any]] = []
        has_reusable = False
        if self._external_request_repo is not None:
            try:
                for req in self._external_request_repo.list_by_job_and_asset(
                    command.job_id, command.asset_id
                ):
                    if (
                        req.status
                        in (
                            ExternalRequestStatus.PROVIDER_SUCCEEDED,
                            ExternalRequestStatus.PERSISTENCE_PENDING,
                            ExternalRequestStatus.PERSISTED,
                        )
                        and req.normalized_result
                    ):
                        has_reusable = True
                    external_requests.append(
                        sanitize_metadata(
                            {
                                "id": req.id,
                                "status": req.status.value,
                                "provider": req.provider,
                                "model": req.model,
                                "prompt_key": req.prompt_key,
                                "prompt_version": req.prompt_version,
                                "estimated_cost": req.estimated_cost,
                                "duration_ms": req.duration_ms,
                                "confidence": req.confidence,
                                "error_code": req.error_code,
                                "position_id": req.position_id,
                                "active_result_id": req.active_result_id,
                                "request_image_sha256": req.request_image_sha256,
                                "provider_response_sha256": req.provider_response_sha256,
                                "normalized_result_sha256": req.normalized_result_sha256,
                            }
                        )
                    )
            except (AttributeError, TypeError, ValueError, OSError) as exc:
                logger.warning(
                    "processing.detail_external_requests_failed job_id=%s asset_id=%s err=%s",
                    command.job_id,
                    command.asset_id,
                    exc,
                )
                external_requests = []

        events: list[dict[str, Any]] = []
        if self._event_repo is not None:
            for ev in self._event_repo.list_by_job_asset(
                command.job_id, command.asset_id, limit=100, offset=0
            ):
                events.append(
                    {
                        "id": ev.id,
                        "event_type": ev.event_type,
                        "timestamp": ev.created_at.isoformat(),
                        "level": ev.severity,
                        "message": ev.message,
                        "metadata": sanitize_metadata(ev.metadata),
                    }
                )

        has_manual = bool(asset_summary.get("has_manual_result"))
        actions = compute_available_actions(
            job=job,
            state=state,
            has_manual_result=has_manual,
            has_reusable_external_normalized=has_reusable,
            flags=_feature_flags(),
            historical_incomplete=historical_incomplete,
        )

        current_state = None
        if state is not None:
            current_state = {
                "status": state.status.value,
                "attempt_count": state.attempt_count,
                "last_strategy": state.last_strategy,
                "active_result_id": state.active_result_id,
                "version": state.version,
                "error_code": state.error_code,
                "error_message": state.error_message,
                "duration_ms": state.duration_ms,
                "started_at": state.started_at.isoformat() if state.started_at else None,
                "finished_at": state.finished_at.isoformat() if state.finished_at else None,
            }

        active_result = None
        position = None
        if state and state.active_result_id and self._position_repo is not None:
            # active_result_id may point at coverage / evidence; expose id only safely
            active_result = {"id": state.active_result_id}
            if self._coverage_repo is not None:
                try:
                    cov = self._coverage_repo.get_by_job_and_asset(
                        command.job_id, command.asset_id
                    )
                    if cov is not None and cov.position_id:
                        pos = self._position_repo.get_by_id(cov.position_id)
                        if pos is not None:
                            position = {
                                "id": pos.id,
                                "code": getattr(pos, "code", None),
                                "aisle_id": getattr(pos, "aisle_id", None),
                            }
                            active_result["position_id"] = pos.id
                except (AttributeError, TypeError, ValueError) as exc:
                    logger.debug(
                        "processing.detail_position_lookup_failed job_id=%s asset_id=%s err=%s",
                        command.job_id,
                        command.asset_id,
                        exc,
                    )

        return {
            "asset": asset_summary,
            "current_state": current_state or {},
            "active_result": active_result,
            "position": position,
            "attempts": attempts,
            "external_requests": external_requests,
            "profile_snapshot": _profile_snapshot(job),
            "events": events,
            "available_actions": actions.to_dict(),
            "historical_incomplete": historical_incomplete,
        }


__all__ = [
    "GetAssetProcessingDetailCommand",
    "GetAssetProcessingDetailUseCase",
    "ListAssetProcessingCommand",
    "ListAssetProcessingUseCase",
]
