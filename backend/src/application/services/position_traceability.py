"""
Best-effort traceability enrichment for v3 positions from ``hybrid_report.json``.

Used by :mod:`src.application.mappers.position_canonical_view` when summary fields are incomplete.
Keeps hybrid-report loading and in-process caching out of HTTP route modules.
"""

from __future__ import annotations

import json
import logging
from typing import Dict, Optional, Set, Tuple

from src.domain.positions.entities import Position

logger = logging.getLogger(__name__)

_TRACEABILITY_CACHE: Dict[str, Tuple[Optional[str], Optional[str], Optional[str]]] = {}
_TRACEABILITY_REPORTS_LOADED: Set[str] = set()
_MAX_TRACEABILITY_JOBS = 128
_MAX_TRACEABILITY_ENTITIES = 4096


def _maybe_evict_traceability_cache() -> None:
    if (
        len(_TRACEABILITY_REPORTS_LOADED) > _MAX_TRACEABILITY_JOBS
        or len(_TRACEABILITY_CACHE) > _MAX_TRACEABILITY_ENTITIES
    ):
        _TRACEABILITY_CACHE.clear()
        _TRACEABILITY_REPORTS_LOADED.clear()


def _load_hybrid_report_for_traceability(job_id: str) -> Optional[Dict[str, object]]:
    from src.api.services.v3_stored_artifact_access import load_hybrid_report_json_for_job
    from src.runtime.v3_deps import get_artifact_store, get_job_repo

    return load_hybrid_report_json_for_job(
        job_id,
        job_repo=get_job_repo(),
        artifact_store=get_artifact_store(),
    )


def enrich_position_traceability_from_report(
    p: Position,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Return ``(source_image_id, traceability_status, source_image_original_filename)`` from the report.

    Assumes ``hybrid_report.json`` is immutable for the process lifetime. Missing reports or entities
    yield ``(None, None, None)``. Uses an in-process cache keyed by ``entity_uid``.
    """
    summary = p.detected_summary_json if isinstance(p.detected_summary_json, dict) else {}
    entity_uid = summary.get("entity_uid") if isinstance(summary.get("entity_uid"), str) else None
    if not entity_uid or "_" not in entity_uid:
        return None, None, None
    cached = _TRACEABILITY_CACHE.get(entity_uid)
    if cached is not None:
        return cached
    parts = entity_uid.rsplit("_", 1)
    if len(parts) != 2:
        return None, None, None
    job_id, _ = parts
    if job_id in _TRACEABILITY_REPORTS_LOADED:
        return None, None, None
    try:
        report = _load_hybrid_report_for_traceability(job_id)
        if report is None:
            return None, None, None
        entities = report.get("entities") or []
        for ent in entities:
            if not isinstance(ent, dict):
                continue
            ent_uid = ent.get("entity_uid")
            if not ent_uid or not isinstance(ent_uid, str):
                continue
            sid = ent.get("source_image_id")
            ts = ent.get("traceability_status")
            sof = ent.get("source_image_original_filename")
            normalized: Tuple[Optional[str], Optional[str], Optional[str]] = (
                str(sid).strip() if sid is not None and str(sid).strip() else None,
                str(ts).strip() if ts is not None and str(ts).strip() else None,
                str(sof).strip() if sof is not None and str(sof).strip() else None,
            )
            _TRACEABILITY_CACHE[ent_uid] = normalized
        _TRACEABILITY_REPORTS_LOADED.add(job_id)
        _maybe_evict_traceability_cache()
        return _TRACEABILITY_CACHE.get(entity_uid, (None, None, None))
    except Exception as e:
        logger.debug("Enrich position traceability from report failed (entity_uid=%s): %s", entity_uid, e)
        return None, None, None


def reset_traceability_cache_for_tests() -> None:
    """Clear caches (tests / isolation only)."""
    _TRACEABILITY_CACHE.clear()
    _TRACEABILITY_REPORTS_LOADED.clear()
