"""In-memory ResultEvidenceRepository — Phase 4.6."""

from __future__ import annotations

from collections.abc import Sequence

from src.application.ports.repositories import ResultEvidenceRepository
from src.domain.result_evidence.entities import ResultEvidenceRecord


class MemoryResultEvidenceRepository(ResultEvidenceRepository):
    def __init__(self) -> None:
        self._store: dict[str, ResultEvidenceRecord] = {}

    def save_many(self, records: list) -> None:
        for record in records:
            if not isinstance(record, ResultEvidenceRecord):
                raise TypeError(f"Expected ResultEvidenceRecord, got {type(record)!r}")
            self._store[record.id] = record

    def delete_by_job_id(self, job_id: str) -> int:
        to_remove = [rid for rid, row in self._store.items() if row.job_id == job_id]
        for rid in to_remove:
            del self._store[rid]
        return len(to_remove)

    def list_by_job_id(self, job_id: str) -> Sequence[ResultEvidenceRecord]:
        return [row for row in self._store.values() if row.job_id == job_id]

    def list_valid_by_job_id(self, job_id: str) -> Sequence[ResultEvidenceRecord]:
        return [
            row
            for row in self._store.values()
            if row.job_id == job_id and row.has_valid_evidence is True
        ]
