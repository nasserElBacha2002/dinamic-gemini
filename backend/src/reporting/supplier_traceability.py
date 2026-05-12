"""Redacted supplier traceability block for hybrid_report.json (Phase E6)."""

from __future__ import annotations

from typing import Any

from src.application.services.supplier_prompt_resolver import SupplierPromptResolution
from src.pipeline.context.run_context import RunContext


def build_supplier_traceability_report_block(context: RunContext) -> dict[str, Any] | None:
    """Optional ``supplier_traceability`` subtree: no full supplier instruction bodies."""
    out: dict[str, Any] = {}
    spr = getattr(context, "supplier_prompt_resolution", None)
    if isinstance(spr, SupplierPromptResolution):
        out["supplier_prompt"] = {
            "resolution_status": spr.resolution_status,
            "fallback_used": spr.fallback_used,
            "fallback_reason": spr.fallback_reason,
            "supplier_prompt_config_id": spr.supplier_prompt_config_id,
            "supplier_prompt_config_version": spr.supplier_prompt_config_version,
        }
    ac = getattr(context, "analysis_context", None)
    meta = ac.metadata if ac is not None and ac.metadata is not None else None
    if isinstance(meta, dict) and meta.get("reference_source"):
        out["supplier_references"] = {
            "reference_source": meta.get("reference_source"),
            "client_supplier_id": meta.get("client_supplier_id"),
            "resolution_status": meta.get("supplier_reference_resolution_status"),
            "image_count": meta.get("supplier_reference_image_count"),
        }
    return out if out else None
