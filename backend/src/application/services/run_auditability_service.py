"""Aggregate persisted job audit metadata for Phase H1 (read-only, no pipeline changes)."""

from __future__ import annotations

import logging
from typing import Any

from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    JobRepository,
)
from src.application.ports.run_audit_execution_log_loader import RunAuditExecutionLogLoader
from src.application.ports.stored_artifact_reader import StoredArtifactReader
from src.application.services.reference_usage_from_job_result import (
    parse_reference_usage_from_result_json,
)
from src.application.services.run_auditability_execution_log import (
    extract_prompt_composition_from_analysis_request,
    find_last_analysis_request_prepared_event,
    merge_effective_prompt_fields,
)
from src.application.services.run_auditability_models import (
    RunAuditabilityView,
    RunAuditMetadataSources,
    RunAuditReferenceUsage,
)
from src.domain.jobs.entities import Job
from src.pipeline.run_metadata import RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT

logger = logging.getLogger(__name__)

AISLE_TARGET = "aisle"


def _strip_str(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _coerce_warnings(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    if isinstance(raw, list):
        out: list[str] = []
        for item in raw:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
        return out
    return []


def _merge_supplier_prompt_from_hybrid(
    hybrid: dict[str, Any] | None,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not hybrid or not isinstance(hybrid, dict):
        return out
    trace = hybrid.get("supplier_traceability")
    if not isinstance(trace, dict):
        return out
    sp = trace.get("supplier_prompt")
    if isinstance(sp, dict):
        for k in (
            "supplier_prompt_config_id",
            "supplier_prompt_config_version",
            "fallback_used",
            "fallback_reason",
        ):
            if k in sp:
                out[k] = sp[k]
    sr = trace.get("supplier_references")
    if isinstance(sr, dict):
        if "client_supplier_id" in sr:
            out["trace_client_supplier_id"] = sr.get("client_supplier_id")
        if "image_count" in sr:
            out["trace_image_count"] = sr.get("image_count")
        if "reference_source" in sr:
            out["trace_reference_source"] = sr.get("reference_source")
    return out


class RunAuditabilityService:
    """Build :class:`RunAuditabilityView` from job row, joins, ``result_json``, hybrid report, execution log."""

    def __init__(
        self,
        *,
        job_repo: JobRepository,
        aisle_repo: AisleRepository,
        inventory_repo: InventoryRepository,
        stored_artifact_reader: StoredArtifactReader,
        execution_log_loader: RunAuditExecutionLogLoader,
    ) -> None:
        self._job_repo = job_repo
        self._aisle_repo = aisle_repo
        self._inventory_repo = inventory_repo
        self._stored_artifact_reader = stored_artifact_reader
        self._execution_log_loader = execution_log_loader

    def build(self, job_id: str) -> RunAuditabilityView | None:
        job = self._job_repo.get_by_id(job_id)
        if job is None:
            return None
        try:
            return self._build_for_job(job)
        except Exception:
            logger.exception("run_auditability_build_failed job_id=%s", job_id)
            return self._minimal_fallback_view(job)

    def _minimal_fallback_view(self, job: Job) -> RunAuditabilityView:
        """Last-resort partial view if aggregation raises unexpectedly."""
        return RunAuditabilityView(
            job_id=job.id,
            status=job.status.value,
            target_type=job.target_type,
            target_id=job.target_id,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            provider_name=job.provider_name,
            model_name=job.model_name,
            prompt_key=job.prompt_key,
            prompt_version=job.prompt_version,
            metadata_sources=RunAuditMetadataSources(job_row=True),
            missing_metadata=["auditability_aggregate_error"],
            legacy_mode=True,
        )

    def _build_for_job(self, job: Job) -> RunAuditabilityView:
        sources = RunAuditMetadataSources(job_row=True)
        result_json: dict[str, Any] = job.result_json if isinstance(job.result_json, dict) else {}
        if result_json:
            sources.result_json = True

        aisle_id: str | None = None
        inventory_id: str | None = None
        client_supplier_id: str | None = None
        client_id: str | None = None

        if job.target_type == AISLE_TARGET and job.target_id:
            aisle_id = str(job.target_id).strip() or None
            aisle = self._aisle_repo.get_by_id(aisle_id) if aisle_id else None
            if aisle is not None:
                sources.aisle_join = True
                inventory_id = aisle.inventory_id
                client_supplier_id = _strip_str(getattr(aisle, "client_supplier_id", None))
            inv = self._inventory_repo.get_by_id(inventory_id) if inventory_id else None
            if inv is not None:
                sources.inventory_join = True
                client_id = _strip_str(getattr(inv, "client_id", None))

        hybrid_report: dict[str, Any] | None = self._stored_artifact_reader.load_hybrid_report_json_for_job(
            job.id
        )
        if hybrid_report:
            sources.hybrid_report = True

        exec_events = self._execution_log_loader.try_load_events_for_job(job)
        if exec_events:
            sources.execution_log = True

        hybrid_supplier = _merge_supplier_prompt_from_hybrid(hybrid_report)
        analysis_payload = find_last_analysis_request_prepared_event(exec_events or [])
        prompt_comp = extract_prompt_composition_from_analysis_request(analysis_payload)
        eff_fields = merge_effective_prompt_fields(prompt_comp)
        prompt_composition_available = bool(prompt_comp)

        supplier_prompt_config_id = _strip_str(eff_fields.get("supplier_prompt_config_id"))
        if supplier_prompt_config_id is None:
            supplier_prompt_config_id = _strip_str(hybrid_supplier.get("supplier_prompt_config_id"))

        supplier_prompt_config_version = _strip_str(eff_fields.get("supplier_prompt_config_version"))
        if supplier_prompt_config_version is None:
            supplier_prompt_config_version = _strip_str(hybrid_supplier.get("supplier_prompt_config_version"))

        fb_used = eff_fields.get("fallback_used")
        if fb_used is None and "fallback_used" in hybrid_supplier:
            fb_used = hybrid_supplier.get("fallback_used")
        supplier_prompt_fallback_used: bool | None
        if isinstance(fb_used, bool):
            supplier_prompt_fallback_used = fb_used
        else:
            supplier_prompt_fallback_used = None

        fb_reason = _strip_str(eff_fields.get("fallback_reason"))
        if fb_reason is None:
            fb_reason = _strip_str(hybrid_supplier.get("fallback_reason"))

        protected_key = _strip_str(eff_fields.get("protected_prompt_contract_key"))
        protected_ver = _strip_str(eff_fields.get("protected_prompt_contract_version"))
        effective_hash = _strip_str(eff_fields.get("effective_prompt_hash"))

        warnings = _coerce_warnings(eff_fields.get("warnings"))

        trace_cs = _strip_str(hybrid_supplier.get("trace_client_supplier_id"))
        if client_supplier_id is None and trace_cs:
            client_supplier_id = trace_cs

        ref_source = _strip_str(eff_fields.get("reference_source"))
        if ref_source is None:
            ref_source = _strip_str(hybrid_supplier.get("trace_reference_source"))

        trace_img_count = hybrid_supplier.get("trace_image_count")
        reference_image_count: int | None
        if isinstance(trace_img_count, int):
            reference_image_count = trace_img_count
        elif isinstance(trace_img_count, str) and trace_img_count.strip().isdigit():
            reference_image_count = int(trace_img_count.strip())
        else:
            reference_image_count = None

        ref_usage_fields = parse_reference_usage_from_result_json(job.result_json)
        reference_usage: RunAuditReferenceUsage | None = None
        if ref_usage_fields is not None:
            reference_usage = RunAuditReferenceUsage(
                resolved=ref_usage_fields.resolved,
                resolved_count=ref_usage_fields.resolved_count,
                provider_consumed=ref_usage_fields.provider_consumed,
                provider_consumed_count=ref_usage_fields.provider_consumed_count,
                reference_ids=list(ref_usage_fields.reference_ids),
                resolution_error=ref_usage_fields.resolution_error,
            )

        vrc = result_json.get(RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT)
        if isinstance(vrc, dict):
            if ref_source is None:
                ref_source = _strip_str(vrc.get("reference_source"))
            if reference_image_count is None:
                rc = vrc.get("resolved_count")
                if isinstance(rc, int):
                    reference_image_count = rc

        ref_ids: list[str] = []
        if ref_usage_fields is not None and ref_usage_fields.reference_ids:
            ref_ids = list(ref_usage_fields.reference_ids)
        elif isinstance(eff_fields.get("reference_image_ids"), list):
            for x in eff_fields["reference_image_ids"]:
                if isinstance(x, str) and x.strip():
                    ref_ids.append(x.strip())

        supplier_reference_images_used: bool | None = None
        if ref_source == "supplier_reference_images":
            if reference_image_count is not None:
                supplier_reference_images_used = reference_image_count > 0
            elif ref_usage_fields is not None:
                supplier_reference_images_used = ref_usage_fields.resolved_count > 0
        elif ref_source is not None:
            supplier_reference_images_used = False

        provider_name = _strip_str(job.provider_name) or _strip_str(result_json.get("provider"))
        model_name = _strip_str(job.model_name)
        prompt_key = _strip_str(job.prompt_key) or _strip_str(result_json.get("prompt_key"))
        prompt_version = _strip_str(job.prompt_version) or _strip_str(result_json.get("prompt_version"))

        legacy_mode = not bool(client_id) and not bool(client_supplier_id)

        view = RunAuditabilityView(
            job_id=job.id,
            status=job.status.value,
            target_type=job.target_type,
            target_id=job.target_id,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            client_id=client_id,
            client_supplier_id=client_supplier_id,
            provider_name=provider_name,
            model_name=model_name,
            prompt_key=prompt_key,
            prompt_version=prompt_version,
            supplier_prompt_config_id=supplier_prompt_config_id,
            supplier_prompt_config_version=supplier_prompt_config_version,
            supplier_prompt_fallback_used=supplier_prompt_fallback_used,
            supplier_prompt_fallback_reason=fb_reason,
            protected_prompt_contract_key=protected_key,
            protected_prompt_contract_version=protected_ver,
            effective_prompt_hash=effective_hash,
            prompt_composition_available=prompt_composition_available,
            reference_usage=reference_usage,
            supplier_reference_images_used=supplier_reference_images_used,
            inventory_visual_references_used=None,
            reference_source=ref_source,
            reference_image_count=reference_image_count,
            reference_ids=ref_ids,
            warnings=warnings,
            metadata_sources=sources,
            missing_metadata=[],
            legacy_mode=legacy_mode,
        )
        view.missing_metadata = self._compute_missing_metadata(view, sources)
        return view

    def _compute_missing_metadata(
        self,
        view: RunAuditabilityView,
        sources: RunAuditMetadataSources,
    ) -> list[str]:
        missing: list[str] = []
        if not sources.hybrid_report:
            missing.append("hybrid_report")
        if not sources.execution_log:
            missing.append("execution_log")
        if view.client_id is None:
            missing.append("client_id")
        if view.client_supplier_id is None:
            missing.append("client_supplier_id")
        if view.supplier_prompt_config_id is None:
            missing.append("supplier_prompt_config_id")
        if view.supplier_prompt_config_version is None:
            missing.append("supplier_prompt_config_version")
        if view.effective_prompt_hash is None:
            missing.append("effective_prompt_hash")
        if view.supplier_prompt_fallback_used is None and view.status == "succeeded":
            missing.append("supplier_prompt_fallback_used")
        if not view.prompt_composition_available:
            missing.append("prompt_composition_summary")
        return missing
