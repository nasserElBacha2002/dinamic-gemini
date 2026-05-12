"""Build compact ``run_audit_snapshot`` for ``job.result_json`` (Phase H4).

Only allowlisted / structural metadata is included. Full prompt text, protected prompt bodies,
and LLM request payloads must never be written here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.application.services.run_auditability_execution_log import merge_effective_prompt_fields
from src.application.services.supplier_prompt_resolver import SupplierPromptResolution
from src.pipeline.run_metadata import (
    RUN_METADATA_KEY_PROMPT_COMPOSITION,
    RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT,
)

RUN_AUDIT_SNAPSHOT_SCHEMA_VERSION = "h4.v1"

_WARNINGS_CAP = 50


def _strip(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _append_warnings_unique(out: list[str], seen: set[str], raw: Any) -> None:
    if raw is None:
        return
    if isinstance(raw, str):
        w = _strip(raw)
        if w and w not in seen:
            seen.add(w)
            out.append(w)
        return
    if not isinstance(raw, list):
        return
    for item in raw:
        w = _strip(item) if isinstance(item, str) else None
        if w and w not in seen:
            seen.add(w)
            out.append(w)
            if len(out) >= _WARNINGS_CAP:
                return


def build_run_audit_snapshot(
    *,
    run_metadata: Mapping[str, Any],
    inventory_id: str | None,
    aisle_id: str | None,
    client_id: str | None,
    client_supplier_id: str | None,
    provider_name: str | None,
    model_name: str | None,
    supplier_prompt_resolution: SupplierPromptResolution | None,
    analysis_context_available: bool,
    created_at_iso: str,
) -> dict[str, Any]:
    """Return a JSON-serializable snapshot dict (``schema_version`` = ``h4.v1``)."""
    prompt_comp = run_metadata.get(RUN_METADATA_KEY_PROMPT_COMPOSITION)
    prompt_comp = prompt_comp if isinstance(prompt_comp, dict) else None
    eff = merge_effective_prompt_fields(prompt_comp)

    cid = _strip(client_id)
    csid = _strip(client_supplier_id)
    if supplier_prompt_resolution is not None:
        cid = cid or _strip(supplier_prompt_resolution.client_id)
        csid = csid or _strip(supplier_prompt_resolution.client_supplier_id)

    sp_id = _strip(eff.get("supplier_prompt_config_id"))
    sp_ver_raw = eff.get("supplier_prompt_config_version")
    sp_ver: str | None = None
    if sp_ver_raw is not None:
        sp_ver = _strip(str(sp_ver_raw))
    if supplier_prompt_resolution is not None:
        if sp_id is None and supplier_prompt_resolution.supplier_prompt_config_id:
            sp_id = str(supplier_prompt_resolution.supplier_prompt_config_id).strip() or None
        if sp_ver is None and supplier_prompt_resolution.supplier_prompt_config_version is not None:
            sp_ver = str(supplier_prompt_resolution.supplier_prompt_config_version)

    fb_used: bool | None
    raw_fb = eff.get("fallback_used")
    if isinstance(raw_fb, bool):
        fb_used = raw_fb
    elif supplier_prompt_resolution is not None:
        fb_used = supplier_prompt_resolution.fallback_used
    else:
        fb_used = None

    fb_reason = _strip(eff.get("fallback_reason"))
    if fb_reason is None and supplier_prompt_resolution is not None:
        fb_reason = _strip(supplier_prompt_resolution.fallback_reason)

    protected_k = _strip(eff.get("protected_prompt_contract_key"))
    protected_v = _strip(eff.get("protected_prompt_contract_version"))
    eff_hash = _strip(eff.get("effective_prompt_hash"))

    ref_src = _strip(eff.get("reference_source"))
    ref_ids: list[str] = []
    raw_img_ids = eff.get("reference_image_ids")
    if isinstance(raw_img_ids, list):
        for x in raw_img_ids:
            s = _strip(x)
            if s:
                ref_ids.append(s)

    vrc = run_metadata.get(RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT)
    vrc = vrc if isinstance(vrc, dict) else None
    if vrc is not None and not ref_ids:
        vids = vrc.get("reference_ids")
        if isinstance(vids, list):
            for x in vids:
                s = _strip(x)
                if s:
                    ref_ids.append(s)
        if ref_src is None:
            ref_src = _strip(vrc.get("reference_source"))

    ref_count: int | None = len(ref_ids) if ref_ids else None
    if ref_count is None and vrc is not None:
        rc = vrc.get("resolved_count")
        if isinstance(rc, int):
            ref_count = rc

    supplier_ref_used: bool | None = None
    if ref_src == "supplier_reference_images":
        if ref_count is not None:
            supplier_ref_used = ref_count > 0
        elif vrc is not None:
            supplier_ref_used = bool(vrc.get("resolved")) and int(vrc.get("resolved_count") or 0) > 0

    warnings: list[str] = []
    seen: set[str] = set()
    _append_warnings_unique(warnings, seen, eff.get("warnings"))
    if supplier_prompt_resolution is not None:
        for w in supplier_prompt_resolution.warnings:
            _append_warnings_unique(warnings, seen, w)
            if len(warnings) >= _WARNINGS_CAP:
                break

    model_resolved = _strip(model_name) or _strip(prompt_comp.get("model_name") if prompt_comp else None)
    pk = _strip(run_metadata.get("prompt_key"))
    pv = _strip(run_metadata.get("prompt_version"))

    return {
        "schema_version": RUN_AUDIT_SNAPSHOT_SCHEMA_VERSION,
        "client_id": cid,
        "inventory_id": _strip(inventory_id),
        "aisle_id": _strip(aisle_id),
        "client_supplier_id": csid,
        "provider_name": _strip(provider_name),
        "model_name": model_resolved,
        "prompt_key": pk,
        "prompt_version": pv,
        "supplier_prompt_config_id": sp_id,
        "supplier_prompt_config_version": sp_ver,
        "supplier_prompt_fallback_used": fb_used,
        "supplier_prompt_fallback_reason": fb_reason,
        "protected_prompt_contract_key": protected_k,
        "protected_prompt_contract_version": protected_v,
        "effective_prompt_hash": eff_hash,
        "prompt_composition_available": bool(prompt_comp),
        "reference_source": ref_src,
        "reference_image_count": ref_count,
        "reference_ids": ref_ids,
        "supplier_reference_images_used": supplier_ref_used,
        "inventory_visual_references_used": None,
        "warnings": warnings,
        "metadata_sources": {
            "run_metadata": True,
            "prompt_composition": prompt_comp is not None,
            "analysis_context": bool(analysis_context_available),
            "supplier_prompt_resolution": supplier_prompt_resolution is not None,
            "visual_reference_context": RUN_METADATA_KEY_VISUAL_REFERENCE_CONTEXT in run_metadata,
        },
        "created_at": created_at_iso,
    }
