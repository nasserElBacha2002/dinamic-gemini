"""
EvidenceStage — generate evidence pack using current logic (v2.3.C).

Preserves current artifact layout and evidence paths; does not integrate ArtifactStorage yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

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
        result = generate_evidence_pack(
            job_id=job_id,
            run_dir=run_dir,
            frames=data.frames_nd,
            metadata=data.metadata,
            entities=data.entities,
        )
        return EvidenceArtifacts(evidence_index=result)
