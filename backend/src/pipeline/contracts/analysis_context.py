"""Shared analysis context for providers — v3.2.4.

Provider-agnostic representation of primary evidence and optional inventory
visual references. Strategies can later decide how to consume it.
Phase 4 corrective: resolved_path on VisualReferenceContext; analysis_context_from_dict for deserialization.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, cast


@dataclass
class AnalysisImage:
    """Image used as primary evidence for analysis."""

    id: str
    source_path: str
    mime_type: str
    role: str = "primary_evidence"


@dataclass
class VisualReferenceContext:
    """Provider-agnostic representation of an inventory visual reference."""

    reference_id: str
    source_path: str
    mime_type: str
    role: str = "inventory_reference"
    created_at: Optional[datetime] = None
    # Phase 4: when set, provider uses this path instead of reconstructing from storage layout.
    resolved_path: Optional[str] = None


@dataclass
class AnalysisContext:
    """Common analysis context shared across providers."""

    primary_evidence: List[AnalysisImage]
    visual_references: List[VisualReferenceContext]
    instructions: List[str]
    metadata: Optional[Mapping[str, Any]] = None


def _parse_datetime(value: Any) -> Optional[datetime]:
    """Parse datetime from string (ISO) or return None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
    return None


def analysis_context_from_dict(data: Optional[Dict[str, Any]]) -> Optional[AnalysisContext]:
    """Deserialize AnalysisContext from dict (e.g. JobInput.metadata['analysis_context']). Single source of truth."""
    if not data or not isinstance(data, dict):
        return None
    primary_raw = data.get("primary_evidence")
    primary: List[AnalysisImage] = []
    if isinstance(primary_raw, list):
        for p in primary_raw:
            if isinstance(p, dict) and p.get("id") is not None:
                primary.append(
                    AnalysisImage(
                        id=str(p["id"]),
                        source_path=str(p.get("source_path", "")),
                        mime_type=str(p.get("mime_type", "")),
                        role=str(p.get("role", "primary_evidence")),
                    )
                )
    refs_raw = data.get("visual_references")
    visual_references: List[VisualReferenceContext] = []
    if isinstance(refs_raw, list):
        for r in refs_raw:
            if isinstance(r, dict) and r.get("reference_id") is not None:
                visual_references.append(
                    VisualReferenceContext(
                        reference_id=str(r["reference_id"]),
                        source_path=str(r.get("source_path", "")),
                        mime_type=str(r.get("mime_type", "")),
                        role=str(r.get("role", "inventory_reference")),
                        created_at=_parse_datetime(r.get("created_at")),
                        resolved_path=str(r["resolved_path"]) if r.get("resolved_path") else None,
                    )
                )
    instructions_raw = data.get("instructions")
    instructions: List[str] = []
    if isinstance(instructions_raw, list):
        for s in instructions_raw:
            if s is not None and isinstance(s, str) and s.strip():
                instructions.append(s.strip())
    return AnalysisContext(
        primary_evidence=primary,
        visual_references=visual_references,
        instructions=instructions,
        metadata=data.get("metadata") if isinstance(data.get("metadata"), (dict, type(None))) else None,
    )


def analysis_context_to_dict(ctx: AnalysisContext) -> Dict[str, Any]:
    """Convert AnalysisContext to a JSON-serializable dict for JobInput.metadata."""

    def _serialize(obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat()
        if hasattr(obj, "__dict__") or isinstance(obj, (AnalysisImage, VisualReferenceContext, AnalysisContext)):
            return {k: _serialize(v) for k, v in asdict(obj).items()}
        if isinstance(obj, list):
            return [_serialize(v) for v in obj]
        if isinstance(obj, dict):
            return {k: _serialize(v) for k, v in obj.items()}
        return obj

    return cast(Dict[str, Any], _serialize(ctx))

