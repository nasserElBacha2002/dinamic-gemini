"""In-memory ManualImageCoverageRepository."""

from __future__ import annotations

from src.application.errors import ManualResultAlreadyExistsError
from src.application.ports.manual_image_coverage_repository import ManualImageCoverageLink


class MemoryManualImageCoverageRepository:
    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str], ManualImageCoverageLink] = {}
        self._by_id: dict[str, ManualImageCoverageLink] = {}

    def get_by_job_and_asset(
        self, job_id: str, source_asset_id: str
    ) -> ManualImageCoverageLink | None:
        return self._by_key.get((job_id, source_asset_id))

    def save(self, link: ManualImageCoverageLink) -> None:
        key = (link.job_id, link.source_asset_id)
        existing = self._by_key.get(key)
        if existing is not None and existing.id != link.id:
            raise ManualResultAlreadyExistsError(
                "La imagen ya tiene un resultado manual asociado."
            )
        self._by_key[key] = link
        self._by_id[link.id] = link

    def list_by_job(self, job_id: str) -> list[ManualImageCoverageLink]:
        return sorted(
            (link for link in self._by_key.values() if link.job_id == job_id),
            key=lambda x: (x.created_at, x.id),
        )

    def delete_by_job_and_asset(self, job_id: str, source_asset_id: str) -> None:
        key = (job_id, source_asset_id)
        existing = self._by_key.pop(key, None)
        if existing is not None:
            self._by_id.pop(existing.id, None)
