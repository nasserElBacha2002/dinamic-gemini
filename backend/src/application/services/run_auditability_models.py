"""Read model for per-job processing auditability (Phase H1) — no persistence changes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class RunAuditMetadataSources:
    """Which upstream sources contributed to :class:`RunAuditabilityView`."""

    job_row: bool = False
    result_json: bool = False
    aisle_join: bool = False
    inventory_join: bool = False
    hybrid_report: bool = False
    execution_log: bool = False


@dataclass
class RunAuditReferenceUsage:
    """Subset of visual reference usage derived from ``job.result_json`` (when present)."""

    resolved: bool = False
    resolved_count: int = 0
    provider_consumed: bool = False
    provider_consumed_count: int = 0
    reference_ids: list[str] = field(default_factory=list)
    resolution_error: str | None = None


@dataclass
class RunAuditabilityView:
    """Normalized audit metadata for one inventory job (aggregated read model)."""

    job_id: str
    status: str
    target_type: str
    target_id: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    inventory_id: str | None = None
    aisle_id: str | None = None
    client_id: str | None = None
    client_supplier_id: str | None = None

    provider_name: str | None = None
    model_name: str | None = None
    prompt_key: str | None = None
    prompt_version: str | None = None

    supplier_prompt_config_id: str | None = None
    supplier_prompt_config_version: str | None = None
    supplier_prompt_fallback_used: bool | None = None
    supplier_prompt_fallback_reason: str | None = None

    protected_prompt_contract_key: str | None = None
    protected_prompt_contract_version: str | None = None
    effective_prompt_hash: str | None = None
    prompt_composition_available: bool = False

    reference_usage: RunAuditReferenceUsage | None = None
    supplier_reference_images_used: bool | None = None
    inventory_visual_references_used: bool | None = None
    reference_source: str | None = None
    reference_image_count: int | None = None
    reference_ids: list[str] = field(default_factory=list)

    warnings: list[str] = field(default_factory=list)

    metadata_sources: RunAuditMetadataSources = field(default_factory=RunAuditMetadataSources)
    missing_metadata: list[str] = field(default_factory=list)
    legacy_mode: bool = False

    def to_jsonable(self) -> dict[str, Any]:
        """JSON-friendly dict for future API surfaces (H2)."""

        def _src(s: RunAuditMetadataSources) -> dict[str, bool]:
            return {
                "job_row": s.job_row,
                "result_json": s.result_json,
                "aisle_join": s.aisle_join,
                "inventory_join": s.inventory_join,
                "hybrid_report": s.hybrid_report,
                "execution_log": s.execution_log,
            }

        ru: dict[str, Any] | None = None
        if self.reference_usage is not None:
            ru = {
                "resolved": self.reference_usage.resolved,
                "resolved_count": self.reference_usage.resolved_count,
                "provider_consumed": self.reference_usage.provider_consumed,
                "provider_consumed_count": self.reference_usage.provider_consumed_count,
                "reference_ids": list(self.reference_usage.reference_ids),
                "resolution_error": self.reference_usage.resolution_error,
            }
        return {
            "job_id": self.job_id,
            "status": self.status,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "inventory_id": self.inventory_id,
            "aisle_id": self.aisle_id,
            "client_id": self.client_id,
            "client_supplier_id": self.client_supplier_id,
            "provider_name": self.provider_name,
            "model_name": self.model_name,
            "prompt_key": self.prompt_key,
            "prompt_version": self.prompt_version,
            "supplier_prompt_config_id": self.supplier_prompt_config_id,
            "supplier_prompt_config_version": self.supplier_prompt_config_version,
            "supplier_prompt_fallback_used": self.supplier_prompt_fallback_used,
            "supplier_prompt_fallback_reason": self.supplier_prompt_fallback_reason,
            "protected_prompt_contract_key": self.protected_prompt_contract_key,
            "protected_prompt_contract_version": self.protected_prompt_contract_version,
            "effective_prompt_hash": self.effective_prompt_hash,
            "prompt_composition_available": self.prompt_composition_available,
            "reference_usage": ru,
            "supplier_reference_images_used": self.supplier_reference_images_used,
            "inventory_visual_references_used": self.inventory_visual_references_used,
            "reference_source": self.reference_source,
            "reference_image_count": self.reference_image_count,
            "reference_ids": list(self.reference_ids),
            "warnings": list(self.warnings),
            "metadata_sources": _src(self.metadata_sources),
            "missing_metadata": list(self.missing_metadata),
            "legacy_mode": self.legacy_mode,
        }
