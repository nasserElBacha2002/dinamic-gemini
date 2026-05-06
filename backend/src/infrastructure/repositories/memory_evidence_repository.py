"""
In-memory implementation of EvidenceRepository — v3.0 Épica 6.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.application.ports.repositories import EvidenceRepository
from src.domain.evidence.entities import Evidence


class MemoryEvidenceRepository(EvidenceRepository):
    def __init__(self) -> None:
        self._store: dict[str, Evidence] = {}

    def save(self, evidence: Evidence) -> None:
        self._store[evidence.id] = evidence

    def get_by_id(self, evidence_id: str) -> Evidence | None:
        return self._store.get(evidence_id)

    def list_by_entity(self, entity_type: str, entity_id: str) -> Sequence[Evidence]:
        return [
            e
            for e in self._store.values()
            if e.entity_type == entity_type and e.entity_id == entity_id
        ]
