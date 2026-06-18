"""Phase 4.8 — read models for structural result_evidence and traceability artifacts."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.application.ports.artifact_manifest_store import ArtifactManifestStore
from src.application.ports.repositories import ResultEvidenceRepository, SourceAssetRepository
from src.domain.jobs.artifact_manifest import ArtifactManifestStatus
from src.domain.jobs.artifact_policy import ARTIFACT_KIND_TRACEABILITY_MANIFEST
from src.domain.positions.entities import Position
from src.domain.result_evidence.display import (
    EVIDENCE_IMAGE_URL_UNAVAILABLE_WARNING,
    STRUCTURAL_EVIDENCE_UNAVAILABLE_WARNING,
    TRACEABILITY_ARTIFACT_UNAVAILABLE_WARNING,
    api_traceability_status_for_row,
    compute_structural_api_displayable,
    detect_source_asset_mismatch,
    resolve_source_asset_id,
)
from src.domain.result_evidence.entities import ResultEvidenceRecord, ResultEvidenceRole
from src.domain.traceability import TraceabilityStatus, normalize_traceability_status

logger = logging.getLogger(__name__)

_LOCAL_PATH_RE = re.compile(r"(?:^/[A-Za-z]:?/|/Users/|/home/|\\)")


@dataclass(frozen=True)
class TraceabilityArtifactReadModel:
    kind: str
    published: bool
    required: bool
    status: str
    storage_key: str | None
    content_hash: str | None
    size_bytes: int | None
    published_at: datetime | None


@dataclass(frozen=True)
class ResultEvidenceViewModel:
    displayable: bool
    traceability_status: str
    traceability_warning: str | None
    role: str | None
    source_image_id: str | None
    source_asset_id: str | None
    resolved_manifest_entry_id: str | None
    raw_manifest_entry_id: str | None
    raw_source_image_id: str | None
    image_url: str | None
    thumbnail_url: str | None
    image_access_status: str | None
    source_kind: str
    provider: str | None
    model_name: str | None


@dataclass(frozen=True)
class JobTraceabilityReadModel:
    job_id: str
    inventory_id: str
    aisle_id: str
    traceability_status: str
    artifact: TraceabilityArtifactReadModel | None
    summary: dict[str, int]
    entities: list[dict[str, Any]]


class ResultEvidenceQueryService:
    """Build fail-closed evidence read models from structural persistence."""

    def __init__(
        self,
        *,
        result_evidence_repo: ResultEvidenceRepository,
        source_asset_repo: SourceAssetRepository,
        manifest_store: ArtifactManifestStore | None,
        artifact_store: Any | None,
        image_url_resolver: Any | None = None,
    ) -> None:
        self._result_evidence_repo = result_evidence_repo
        self._source_asset_repo = source_asset_repo
        self._manifest_store = manifest_store
        self._artifact_store = artifact_store
        self._image_url_resolver = image_url_resolver

    def _assets_by_id(self, aisle_id: str) -> dict[str, object]:
        return {asset.id: asset for asset in self._source_asset_repo.list_by_aisle(aisle_id)}

    def _match_row(
        self,
        rows: list[ResultEvidenceRecord],
        *,
        position: Position,
    ) -> ResultEvidenceRecord | None:
        for row in rows:
            if row.position_id == position.id:
                return row
        summary = position.detected_summary_json if isinstance(position.detected_summary_json, dict) else {}
        entity_uid = summary.get("entity_uid")
        if isinstance(entity_uid, str) and entity_uid.strip():
            for row in rows:
                if row.entity_uid == entity_uid:
                    return row
        return None

    def _resolve_image_url(
        self,
        *,
        asset: object | None,
        inventory_id: str,
        aisle_id: str,
        asset_id: str,
    ) -> tuple[str | None, str | None]:
        if asset is None or self._image_url_resolver is None:
            return None, "url_unavailable"
        try:
            image_url, requires_fetch = self._image_url_resolver(
                asset,
                artifact_store=self._artifact_store,
            )
        except Exception as exc:
            logger.debug(
                "evidence_image_url_unavailable inventory_id=%s aisle_id=%s asset_id=%s err=%s",
                inventory_id,
                aisle_id,
                asset_id,
                type(exc).__name__,
            )
            return None, "url_unavailable"
        if image_url and _LOCAL_PATH_RE.search(str(image_url)):
            return None, "url_unavailable"
        if image_url and str(image_url).startswith(("http://", "https://")):
            return str(image_url), "available"
        if requires_fetch:
            return (
                f"/api/v3/inventories/{inventory_id}/aisles/{aisle_id}/assets/{asset_id}/file",
                "available",
            )
        return None, "url_unavailable"

    def _artifact_blocks_display(self, job_id: str | None) -> tuple[bool, str | None]:
        """True when durable traceability_manifest is required but not published."""
        if not job_id or self._manifest_store is None:
            return False, None
        artifact = self._artifact_read_model(job_id)
        if artifact is None:
            return False, None
        if artifact.required and not artifact.published:
            return True, TRACEABILITY_ARTIFACT_UNAVAILABLE_WARNING
        return False, None

    def get_traceability_artifact(self, job_id: str | None) -> TraceabilityArtifactReadModel | None:
        if not job_id:
            return None
        return self._artifact_read_model(job_id)

    def build_evidence_view(
        self,
        record: ResultEvidenceRecord | None,
        *,
        inventory_id: str,
        aisle_id: str,
        assets_by_id: dict[str, object],
        job_id: str | None = None,
    ) -> ResultEvidenceViewModel:
        if record is None:
            return ResultEvidenceViewModel(
                displayable=False,
                traceability_status="legacy_unavailable",
                traceability_warning=STRUCTURAL_EVIDENCE_UNAVAILABLE_WARNING,
                role=None,
                source_image_id=None,
                source_asset_id=None,
                resolved_manifest_entry_id=None,
                raw_manifest_entry_id=None,
                raw_source_image_id=None,
                image_url=None,
                thumbnail_url=None,
                image_access_status="not_allowed",
                source_kind="unavailable",
                provider=None,
                model_name=None,
            )

        resolved_asset_id = resolve_source_asset_id(record, assets_by_id=assets_by_id)
        mismatch_warning = detect_source_asset_mismatch(
            record,
            resolved_source_asset_id=resolved_asset_id,
        )
        displayable = False
        traceability_warning = record.traceability_warning
        if mismatch_warning:
            traceability_warning = mismatch_warning
        else:
            displayable = compute_structural_api_displayable(
                record,
                resolved_source_asset_id=resolved_asset_id,
            )

        artifact_blocks, artifact_warning = self._artifact_blocks_display(job_id)
        if artifact_blocks:
            displayable = False
            traceability_warning = artifact_warning

        image_url: str | None = None
        image_access_status: str | None = "not_allowed"
        if mismatch_warning:
            image_access_status = "not_allowed"
        elif artifact_blocks:
            image_access_status = "not_allowed"
        elif displayable and resolved_asset_id:
            asset = assets_by_id.get(resolved_asset_id)
            image_url, image_access_status = self._resolve_image_url(
                asset=asset,
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                asset_id=resolved_asset_id,
            )
            if image_access_status == "url_unavailable":
                displayable = False
                traceability_warning = EVIDENCE_IMAGE_URL_UNAVAILABLE_WARNING

        traceability_status = api_traceability_status_for_row(
            record,
            displayable=displayable,
            image_access_status=image_access_status,
        )
        if artifact_blocks:
            traceability_status = "artifact_unavailable"
        elif mismatch_warning:
            traceability_status = TraceabilityStatus.INVALID.value
        role_value = record.role.value if record.role is not None else None
        if record.role == ResultEvidenceRole.REFERENCE_IMAGE and not displayable:
            traceability_status = TraceabilityStatus.INVALID.value

        return ResultEvidenceViewModel(
            displayable=displayable,
            traceability_status=traceability_status,
            traceability_warning=traceability_warning,
            role=role_value,
            source_image_id=record.source_image_id,
            source_asset_id=resolved_asset_id,
            resolved_manifest_entry_id=record.resolved_manifest_entry_id,
            raw_manifest_entry_id=record.raw_manifest_entry_id or record.manifest_entry_id,
            raw_source_image_id=record.raw_source_image_id,
            image_url=image_url if displayable else None,
            thumbnail_url=image_url if displayable else None,
            image_access_status=image_access_status,
            source_kind="structural_result_evidence",
            provider=record.provider,
            model_name=record.model_name,
        )

    def get_position_evidence_view(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        position: Position,
        job_id: str | None,
    ) -> ResultEvidenceViewModel:
        if not job_id:
            return self.build_evidence_view(
                None,
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                assets_by_id=self._assets_by_id(aisle_id),
            )
        rows = list(
            self._result_evidence_repo.list_for_scope(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                job_id=job_id,
            )
        )
        matched = self._match_row(rows, position=position)
        assets_by_id = self._assets_by_id(aisle_id)
        return self.build_evidence_view(
            matched,
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            assets_by_id=assets_by_id,
            job_id=job_id,
        )

    def _artifact_read_model(self, job_id: str) -> TraceabilityArtifactReadModel | None:
        if self._manifest_store is None:
            return None
        entry = self._manifest_store.get_entry(job_id, ARTIFACT_KIND_TRACEABILITY_MANIFEST)
        if entry is None:
            return None
        return TraceabilityArtifactReadModel(
            kind=entry.artifact_kind,
            published=entry.status == ArtifactManifestStatus.PUBLISHED,
            required=entry.required,
            status=entry.status.value,
            storage_key=entry.storage_key,
            content_hash=entry.content_hash or entry.source_sha256,
            size_bytes=entry.size_bytes,
            published_at=entry.published_at,
        )

    def _summary_from_rows(
        self,
        views: list[ResultEvidenceViewModel],
        *,
        artifact: TraceabilityArtifactReadModel | None = None,
    ) -> dict[str, int]:
        summary = {
            "total_evidence_rows": len(views),
            "valid": 0,
            "invalid": 0,
            "missing": 0,
            "unvalidated": 0,
            "displayable": 0,
            "not_displayable": 0,
            "reference_rejected": 0,
            "unknown_identifier": 0,
            "conflicting_identifier": 0,
            "malformed_identifier": 0,
            "manifest_unavailable": 0,
            "manifest_invalid": 0,
            "unvalidated_unknown": 0,
            "artifact_required": 0,
            "artifact_published": 0,
        }
        for view in views:
            if view.displayable:
                summary["displayable"] += 1
            else:
                summary["not_displayable"] += 1
            status = normalize_traceability_status(view.traceability_status)
            warning = (view.traceability_warning or "").lower()
            if status == TraceabilityStatus.VALID.value:
                summary["valid"] += 1
            elif status == TraceabilityStatus.INVALID.value:
                summary["invalid"] += 1
                if "conflicting" in warning:
                    summary["conflicting_identifier"] += 1
                elif "unknown" in warning:
                    summary["unknown_identifier"] += 1
                elif "malformed" in warning:
                    summary["malformed_identifier"] += 1
            elif status == TraceabilityStatus.MISSING.value:
                summary["missing"] += 1
            elif status == TraceabilityStatus.UNVALIDATED.value:
                summary["unvalidated"] += 1
                if "manifest was invalid" in warning or "manifest invalid" in warning:
                    summary["manifest_invalid"] += 1
                elif "manifest was unavailable" in warning or "manifest unavailable" in warning:
                    summary["manifest_unavailable"] += 1
                else:
                    summary["unvalidated_unknown"] += 1
            if view.role == ResultEvidenceRole.REFERENCE_IMAGE.value or "reference" in warning:
                summary["reference_rejected"] += 1
        if artifact is not None:
            if artifact.required:
                summary["artifact_required"] = 1
            summary["artifact_published"] = 1 if artifact.published else 0
        return summary

    def get_job_traceability(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        job_id: str,
    ) -> JobTraceabilityReadModel:
        rows = list(
            self._result_evidence_repo.list_for_scope(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                job_id=job_id,
            )
        )
        assets_by_id = self._assets_by_id(aisle_id)
        views = [
            self.build_evidence_view(
                row,
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                assets_by_id=assets_by_id,
                job_id=job_id,
            )
            for row in rows
        ]
        artifact = self._artifact_read_model(job_id)
        traceability_status = "available"
        if artifact is None:
            traceability_status = "artifact_unavailable"
        elif artifact.required and not artifact.published:
            traceability_status = "artifact_unavailable"

        entities: list[dict[str, Any]] = []
        for row, view in zip(rows, views):
            entities.append(
                {
                    "position_id": row.position_id,
                    "entity_uid": row.entity_uid,
                    "model_entity_id": row.model_entity_id,
                    "evidence": view,
                }
            )

        summary = self._summary_from_rows(views, artifact=artifact)

        return JobTraceabilityReadModel(
            job_id=job_id,
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            traceability_status=traceability_status,
            artifact=artifact,
            summary=summary,
            entities=entities,
        )
