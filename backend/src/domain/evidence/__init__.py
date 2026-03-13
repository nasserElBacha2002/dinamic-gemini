"""
V3.0 Evidence entity (Documento técnico §7.6).

Domain model: Evidence represents visual evidence linked to an entity (e.g. position).
For evidence pack generation (pipeline: crops, overview frames), see src.evidence.
"""

from src.domain.evidence.entities import Evidence, EvidenceType

__all__ = ["Evidence", "EvidenceType"]
