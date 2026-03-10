"""
Evidence pack generation — pipeline infrastructure (Stage 2.1.D).

Overview frames and localized label crops (when bbox present);
UNLOCALIZED (overview only) when bbox missing.
For the v3.0 domain entity Evidence (business concept), see src.domain.evidence.
"""

from src.evidence.evidence_pack import generate_evidence_pack
from src.evidence.paths import entity_evidence_path, slug
from src.evidence.scoring import dedupe_by_hash, dedupe_indexed_by_hash, score_frame_sharpness

__all__ = [
    "generate_evidence_pack",
    "entity_evidence_path",
    "slug",
    "score_frame_sharpness",
    "dedupe_by_hash",
    "dedupe_indexed_by_hash",
]
