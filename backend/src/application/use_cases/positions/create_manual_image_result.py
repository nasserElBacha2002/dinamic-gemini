"""Create a manual coverage position linked to a job photo (job_source_assets)."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from src.application.errors import (
    AssetNotInJobSnapshotError,
    ImageAlreadyHasResultsError,
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
from src.application.ports.manual_image_coverage_repository import ManualImageCoverageLink
from src.application.ports.manual_image_result_unit_of_work import (
    ManualImageResultUnitOfWork,
)
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    JobRepository,
    SourceAssetRepository,
)
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.application.services.job_image_result_resolution import (
    is_photos_job_snapshot,
    unique_photo_coverage_images,
)
from src.application.services.manual_image_result_input import (
    build_manual_product_record_fields,
    validate_manual_image_result_input,
)
from src.domain.evidence.entities import Evidence, EvidenceType
from src.domain.positions.entities import (
    Position,
    PositionCreationSource,
    PositionReviewResolution,
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

logger = logging.getLogger(__name__)


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
        clock: Clock,
        unit_of_work_factory: Callable[[], ManualImageResultUnitOfWork],
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._job_repo = job_repo
        self._job_source_asset_repo = job_source_asset_repo
        self._source_asset_repo = source_asset_repo
        self._clock = clock
        self._unit_of_work_factory = unit_of_work_factory

    def execute(self, command: CreateManualImageResultCommand) -> CreateManualImageResultOutcome:
        total_started = time.perf_counter()
        timing: dict[str, float] = {}

        started = time.perf_counter()
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

        validated = validate_manual_image_result_input(
            sku=command.sku,
            quantity=command.quantity,
            description=command.description,
            position_code=command.position_code,
        )

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
            in_snapshot = any((link.source_asset_id or "").strip() == asset_id for link in links)
            if not in_snapshot:
                raise AssetNotInJobSnapshotError(
                    f"Source asset {asset_id} is not part of job {job_id} snapshot."
                )
            raise ManualResultNotAllowedForAssetTypeError(
                "Manual results are only allowed for primary photo assets in the job snapshot."
            )

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
        timing["scope_validation_ms"] = (time.perf_counter() - started) * 1000.0

        snap = photo_by_asset[asset_id]
        if not (snap.job_source_asset_id or "").strip():
            raise ValueError("job_source_asset_id is required for manual coverage")

        now = self._clock.now()
        position_id = str(uuid.uuid4())
        product_id = str(uuid.uuid4())
        evidence_id = str(uuid.uuid4())
        result_evidence_id = str(uuid.uuid4())
        coverage_id = str(uuid.uuid4())
        entity_uid = f"{job_id}_manual_{asset_id}"
        product_fields = build_manual_product_record_fields(validated.quantity)

        summary: dict = {
            "entity_uid": entity_uid,
            "entity_type": "PALLET",
            "internal_code": validated.sku,
            "source_image_id": asset_id,
            "source_asset_id": asset_id,
            "source_image_original_filename": snap.original_filename,
            "source_image_sequence": snap.position_order + 1,
            "creation_source": PositionCreationSource.MANUAL.value,
            "qty_source": product_fields["qty_source"],
            "qty_parse_status": product_fields["qty_parse_status"],
        }
        if validated.position_code:
            summary["position_barcode"] = validated.position_code
            summary["pallet_id"] = validated.position_code

        storage_path = snap.storage_key or f"manual://{asset_id}"
        if live is not None:
            storage_path = live.storage_path or live.storage_key or storage_path

        position = Position(
            id=position_id,
            aisle_id=command.aisle_id,
            status=PositionStatus.REVIEWED,
            confidence=1.0,
            needs_review=False,
            primary_evidence_id=evidence_id,
            created_at=now,
            updated_at=now,
            review_resolution=PositionReviewResolution.MANUAL_CREATED,
            detected_summary_json=summary,
            corrected_summary_json=None,
            corrected_position_code=validated.position_code,
            job_id=job_id,
            creation_source=PositionCreationSource.MANUAL,
        )
        product = ProductRecord(
            id=product_id,
            position_id=position_id,
            sku=validated.sku,
            description=validated.description,
            detected_quantity=validated.quantity,
            corrected_quantity=validated.quantity,
            confidence=1.0,
            created_at=now,
            updated_at=now,
            qty_source=str(product_fields["qty_source"]),
            qty_inference_reason=None,
            raw_qty=validated.quantity,
            qty_parse_status=str(product_fields["qty_parse_status"]),
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
            job_source_asset_id=snap.job_source_asset_id,
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
                "job_source_asset_id": snap.job_source_asset_id,
                "position_id": position_id,
                "sku": validated.sku,
                "quantity": validated.quantity,
                "description": validated.description,
                "position_code": validated.position_code,
                "creation_source": PositionCreationSource.MANUAL.value,
                "review_resolution": PositionReviewResolution.MANUAL_CREATED.value,
            },
            created_at=now,
            user_id=command.user_id,
            comment=None,
            job_id=job_id,
        )

        outcome_status = "success"
        try:
            with self._unit_of_work_factory() as uow:
                if hasattr(uow, "bind_lifecycle_scope"):
                    uow.bind_lifecycle_scope(
                        inventory_id=command.inventory_id,
                        aisle_id=command.aisle_id,
                    )
                repos = uow.repositories

                uow.acquire_image_result_lock(job_id=job_id, source_asset_id=asset_id)

                started = time.perf_counter()
                existing_manual = repos.manual_coverage_repo.get_by_job_and_asset(job_id, asset_id)
                if existing_manual is not None:
                    raise ManualResultAlreadyExistsError(
                        "La imagen ya tiene un resultado manual asociado."
                    )
                if repos.image_coverage_repo.has_results_for_asset(
                    job_id=job_id,
                    aisle_id=command.aisle_id,
                    source_asset_id=asset_id,
                ):
                    raise ImageAlreadyHasResultsError(
                        "La imagen ya tiene uno o más resultados asociados."
                    )
                timing["existing_result_check_ms"] = (time.perf_counter() - started) * 1000.0

                started = time.perf_counter()
                repos.position_repo.save(position)
                timing["position_insert_ms"] = (time.perf_counter() - started) * 1000.0

                started = time.perf_counter()
                repos.product_record_repo.save(product)
                timing["product_insert_ms"] = (time.perf_counter() - started) * 1000.0

                started = time.perf_counter()
                repos.evidence_repo.save(evidence)
                timing["evidence_insert_ms"] = (time.perf_counter() - started) * 1000.0

                started = time.perf_counter()
                repos.manual_coverage_repo.save(coverage)
                timing["manual_coverage_insert_ms"] = (time.perf_counter() - started) * 1000.0

                started = time.perf_counter()
                repos.result_evidence_repo.save_many([result_evidence])
                timing["result_evidence_insert_ms"] = (time.perf_counter() - started) * 1000.0

                started = time.perf_counter()
                repos.review_repo.save(review)
                timing["review_action_insert_ms"] = (time.perf_counter() - started) * 1000.0

                uow.commit()
                if uow.timing_ms:
                    timing.update(uow.timing_ms)
        except (ManualResultAlreadyExistsError, ImageAlreadyHasResultsError):
            outcome_status = "conflict"
            raise
        except Exception:
            outcome_status = "error"
            raise
        finally:
            timing["total_ms"] = (time.perf_counter() - total_started) * 1000.0
            logger.info(
                "manual_image_result_timing inventory_id=%s aisle_id=%s job_id=%s "
                "source_asset_id=%s status=%s timing=%s",
                command.inventory_id,
                command.aisle_id,
                job_id,
                asset_id,
                outcome_status,
                {k: round(v, 2) for k, v in timing.items()},
            )

        return CreateManualImageResultOutcome(position=position, product=product)


__all__ = [
    "CreateManualImageResultCommand",
    "CreateManualImageResultOutcome",
    "CreateManualImageResultUseCase",
]
