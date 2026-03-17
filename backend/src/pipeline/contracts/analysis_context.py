"""Shared analysis context for providers — v3.2.4.

Provider-agnostic representation of primary evidence and optional inventory
visual references. Strategies can later decide how to consume it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional


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


@dataclass
class AnalysisContext:
    """Common analysis context shared across providers."""

    primary_evidence: List[AnalysisImage]
    visual_references: List[VisualReferenceContext]
    instructions: List[str]
    metadata: Optional[Mapping[str, Any]] = None


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

    return _serialize(ctx)

