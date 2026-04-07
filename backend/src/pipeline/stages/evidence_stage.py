"""
EvidenceStage — generate evidence pack using current logic (v2.3.C).

Preserves current artifact layout and evidence paths; does not integrate ArtifactStorage yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from src.domain.entity import Entity
from src.evidence.evidence_pack import generate_evidence_pack
from src.pipeline.context.run_context import RunContext


@dataclass
class EvidenceStageInput:
    """Input for EvidenceStage: resolved entities plus frames/metadata from acquisition (orchestrator assembles)."""

    entities: List[Entity]
    frames_nd: List[np.ndarray]
    metadata: Dict[str, Any]
    #: Aligned with ``frames_nd`` (same length); image_id per photo or video frame ref — required for photo traceability.
    frame_refs: List[str] = field(default_factory=list)


@dataclass
class EvidenceArtifacts:
    """Output of EvidenceStage: evidence written; entities mutated with evidence_path/evidence_localization."""

    evidence_index: Dict[str, Any]


class EvidenceStage:
    """Stage: generate evidence pack (overview + crops); write run_dir/evidence/ and evidence_index.json."""

    def run(self, context: RunContext, data: EvidenceStageInput) -> EvidenceArtifacts:
        """Call generate_evidence_pack; preserve current artifact layout and paths."""
        job_id = context.job_id
        run_dir = context.run_dir
        refs: Optional[List[str]] = data.frame_refs if data.frame_refs else None
        if refs is not None and len(refs) != len(data.frames_nd):
            context.logger.warning(
                "EvidenceStage: frame_refs length %d != frames_nd %d; ignoring refs for evidence scoping",
                len(refs),
                len(data.frames_nd),
            )
            refs = None
        result = generate_evidence_pack(
            job_id=job_id,
            run_dir=run_dir,
            frames=data.frames_nd,
            metadata=data.metadata,
            entities=data.entities,
            frame_refs=refs,
        )
        return EvidenceArtifacts(evidence_index=result)
