"""
Labels domain — v3.2.3.

Three-layer model: RawLabel (original observation) → NormalizedLabel (after merge) → FinalCountRecord (business output).
"""

from src.domain.labels.entities import (
    FinalCountRecord,
    NormalizedLabel,
    RawLabel,
)
from src.domain.labels.merge import MergeDecision, MergeRule, MergeRuleEngine

__all__ = [
    "FinalCountRecord",
    "MergeDecision",
    "MergeRule",
    "MergeRuleEngine",
    "NormalizedLabel",
    "RawLabel",
]
