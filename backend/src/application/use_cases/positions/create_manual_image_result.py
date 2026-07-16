"""Create a manual coverage position linked to a job photo (job_source_assets)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from src.application.errors import (
    AssetNotInJobSnapshotError,
    InventoryNotFoundError,
    JobDoesNotBelongToAisleError,
    JobNotFoundError,
    ManualResultAlreadyExistsError,
    ManualResultNotAllowedForAssetTypeError,
    PhotosJobRequiredError,
    SourceAssetNotFoundForAisleError,
)
from src.application.ports.clock import Clock
from src.application.ports.job_source_asset_repository import JobSourceAssetRepository
from src.application.ports.manual_image_coverage_repository import (
    ManualImageCoverageLink,
    ManualImageCoverageRepository,
)
from src.application.ports.repositories import (
    AisleRepository,
    EvidenceRepository,
    InventoryRepository,
    JobRepository,
    PositionRepository,
    ProductRecordRepository,
    ResultEvidenceRepository,
    ReviewActionRepository,
    SourceAssetRepository,
)
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.application.services.aisle_review_lifecycle_sync import AisleReviewLifecycleSync
from src.application.services.job_image_result_resolution import (
    is_photos_job_snapshot,
    unique_photo_coverage_images,
)
from src.domain.evidence.entities import Evidence, EvidenceType
from src.domain.positions.entities import (
    Position,
    PositionCreationSource,
    PositionStatus,
)
from src.domain.products.entities import ProductRecord
from src.domain.result_evidence.entities import (
    RESULT_EVIDENCE_KIND_ENTITY_TRACEABILITY,
    ResultEvidenceRecord,
    ResultEvidenceRole,
)
from src.domain.reviews.entities import ReviewAction, ReviewActionType
from src.domain.traceability import TraceabilityStatus


@dataclass
class CreateManualImageResultCommand:
    inventory_id: str
    aisle_id: str
    source_asset_id: str
    job_id: str
    sku: str
    quantity: int
    description: str | None = None
    position_code: str | None = None
    user_id: str | None = None


@dataclass(frozen=True)
class CreateManualImageResultOutcome:
    position: Position
    product: ProductRecord


class CreateManualImageResultUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        job_repo: JobRepository,
        job_source_asset_repo: JobSourceAssetRepository,
        source_asset_repo: SourceAssetRepository,
        position_repo: PositionRepository,
        product_record_repo: ProductRecordRepository,
        evidence_repo: EvidenceRepository,
        result_evidence_repo: ResultEvidenceRepository,
        review_repo: ReviewActionRepository,
        manual_coverage_repo: ManualImageCoverageRepository,
        clock: Clock,
        aisle_review_sync: AisleReviewLifecycleSync,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._job_repo = job_repo
        self._job_source_asset_repo = job_source_asset_repo
        self._source_asset_repo = source_asset_repo
        self._position_repo = position_repo
        self._product_record_repo = product_record_repo
        self._evidence_repo = evidence_repo
        self._result_evidence_repo = result_evidence_repo
        self._review_repo = review_repo
        self._manual_coverage_repo = manual_coverage_repo
        self._clock = clock
        self._aisle_review_sync = aisle_review_sync

    def execute(self, command: CreateManualImageResultCommand) -> CreateManualImageResultOutcome:
        inv = self._inventory_repo.get_by_id(command.inventory_id)
        if inv is None:
            raise InventoryNotFoundError(f"Inventory not found: {command.inventory_id}")
        require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            detail_style="strict",
        )

        job_id = (command.job_id or "").strip()
        if not job_id:
            raise ValueError("job_id is required")
        job = self._job_repo.get_by_id(job_id)
        if job is None:
            raise JobNotFoundError(f"Job not found: {job_id}")
        if job.target_type != "aisle" or job.target_id != command.aisle_id:
            raise JobDoesNotBelongToAisleError(
                f"Job {job_id} does not belong to aisle {command.aisle_id}"
            )

        sku = (command.sku or "").strip()
        if not sku:
            raise ValueError("sku is required")
        if command.quantity < 0:
            raise ValueError("quantity must be non-negative")

        description: str | None = None
        if command.description is not None:
            clean = command.description.strip()
            description = clean or None

        position_code: str | None = None
        if command.position_code is not None:
            clean_code = command.position_code.strip()
            position_code = clean_code or None

        asset_id = (command.source_asset_id or "").strip()
        if not asset_id:
            raise ValueError("source_asset_id is required")

        links = self._job_source_asset_repo.list_for_job(job_id)
        if not is_photos_job_snapshot(links, job):
            raise PhotosJobRequiredError(
                "Manual image results are only supported for photos jobs."
            )

        photo_images = unique_photo_coverage_images(links)
        photo_by_asset = {img.source_asset_id: img for img in photo_images}
        if asset_id not in photo_by_asset:
            # Distinguish "not in snapshot" vs "in snapshot but not a coverage photo"
            in_snapshot = any((link.source_asset_id or "").strip() == asset_id for link in links)
            if not in_snapshot:
                raise AssetNotInJobSnapshotError(
                    f"Source asset {asset_id} is not part of job {job_id} snapshot."
                )
            raise ManualResultNotAllowedForAssetTypeError(
                "Manual results are only allowed for primary photo assets in the job snapshot."
            )

        # Prefer live asset type check when the row still exists (Option B: may be gone).
        live = self._source_asset_repo.get_by_id(asset_id)
        if live is not None:
            if live.aisle_id != command.aisle_id:
                raise SourceAssetNotFoundForAisleError(
                    f"Source asset {asset_id} not found for aisle {command.aisle_id}"
                )
            type_value = getattr(live.type, "value", live.type)
            if str(type_value).strip().lower() == "video":
                raise ManualResultNotAllowedForAssetTypeError(
                    "Manual results are not allowed for video assets."
                )

        existing = self._manual_coverage_repo.get_by_job_and_asset(job_id, asset_id)
        if existing is not None:
            raise ManualResultAlreadyExistsError(
                "La imagen ya tiene un resultado manual asociado."
            )

        snap = photo_by_asset[asset_id]
        now = self._clock.now()
        position_id = str(uuid.uuid4())
        product_id = str(uuid.uuid4())
        evidence_id = str(uuid.uuid4())
        result_evidence_id = str(uuid.uuid4())
        coverage_id = str(uuid.uuid4())
        entity_uid = f"{job_id}_manual_{asset_id}"

        summary: dict = {
            "entity_uid": entity_uid,
            "entity_type": "PALLET",
            "internal_code": sku,
            "source_image_id": asset_id,
            "source_asset_id": asset_id,
            "source_image_original_filename": snap.original_filename,
            "source_image_sequence": snap.position_order + 1,
            "creation_source": PositionCreationSource.MANUAL.value,
            "qty_source": "manual_review",
            "qty_parse_status": "valid_positive" if command.quantity > 0 else "zero",
        }
        if position_code:
            summary["position_barcode"] = position_code
            summary["pallet_id"] = position_code

        storage_path = snap.storage_key or f"manual://{asset_id}"
        if live is not None:
            storage_path = live.storage_path or live.storage_key or storage_path

        position = Position(
            id=position_id,
            aisle_id=command.aisle_id,
            status=PositionStatus.CORRECTED,
            confidence=1.0,
            needs_review=False,
            primary_evidence_id=evidence_id,
            created_at=now,
            updated_at=now,
            review_resolution=None,
            detected_summary_json=summary,
            corrected_summary_json=None,
            corrected_position_code=position_code,
            job_id=job_id,
            creation_source=PositionCreationSource.MANUAL,
        )
        product = ProductRecord(
            id=product_id,
            position_id=position_id,
            sku=sku,
            description=description,
            detected_quantity=command.quantity,
            corrected_quantity=command.quantity,
            confidence=1.0,
            created_at=now,
            updated_at=now,
            qty_source="manual_review",
            qty_inference_reason=None,
            raw_qty=command.quantity,
            qty_parse_status="valid_positive" if command.quantity > 0 else "zero",
        )
        evidence = Evidence(
            id=evidence_id,
            entity_type="position",
            entity_id=position_id,
            type=EvidenceType.ORIGINAL_IMAGE,
            storage_path=storage_path,
            is_primary=True,
            source_asset_id=asset_id,
            content_type=snap.mime_type or (live.content_type if live else None),
            storage_key=snap.storage_key or (live.storage_key if live else None),
            file_size_bytes=live.file_size_bytes if live else None,
        )
        result_evidence = ResultEvidenceRecord(
            id=result_evidence_id,
            job_id=job_id,
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            position_id=position_id,
            entity_uid=entity_uid,
            model_entity_id=None,
            raw_manifest_entry_id=None,
            manifest_entry_id=None,
            raw_source_image_id=asset_id,
            resolved_manifest_entry_id=None,
            source_image_id=asset_id,
            source_asset_id=asset_id,
            traceability_status=TraceabilityStatus.VALID.value,
            traceability_warning=None,
            role=ResultEvidenceRole.PRIMARY_EVIDENCE,
            provider="manual",
            model_name=None,
            schema_version=None,
            manifest_version=None,
            has_valid_evidence=True,
            evidence_kind=RESULT_EVIDENCE_KIND_ENTITY_TRACEABILITY,
            created_at=now,
            updated_at=now,
        )
        coverage = ManualImageCoverageLink(
            id=coverage_id,
            job_id=job_id,
            source_asset_id=asset_id,
            position_id=position_id,
            aisle_id=command.aisle_id,
            inventory_id=command.inventory_id,
            created_by_user_id=command.user_id,
            created_at=now,
        )
        review = ReviewAction(
            id=str(uuid.uuid4()),
            position_id=position_id,
            action_type=ReviewActionType.CREATE_MANUAL_RESULT_FROM_IMAGE,
            before_json={},
            after_json={
                "inventory_id": command.inventory_id,
                "aisle_id": command.aisle_id,
                "job_id": job_id,
                "source_asset_id": asset_id,
                "image_id": snap.image_id,
                "position_id": position_id,
                "sku": sku,
                "quantity": command.quantity,
                "description": description,
                "position_code": position_code,
                "creation_source": PositionCreationSource.MANUAL.value,
            },
            created_at=now,
            user_id=command.user_id,
            comment=None,
            job_id=job_id,
        )

        # Persist order: position → product → evidence → coverage (unique) → result_evidence → review.
        # Coverage unique constraint is the concurrency gate.
        self._position_repo.save(position)
        self._product_record_repo.save(product)
        self._evidence_repo.save(evidence)
        try:
            self._manual_coverage_repo.save(coverage)
        except ManualResultAlreadyExistsError:
            raise
        self._result_evidence_repo.save_many([result_evidence])
        self._review_repo.save(review)
        self._aisle_review_sync.after_review_mutation(command.inventory_id, command.aisle_id)

        return CreateManualImageResultOutcome(position=position, product=product)


__all__ = [
    "CreateManualImageResultCommand",
    "CreateManualImageResultOutcome",
    "CreateManualImageResultUseCase",
]
