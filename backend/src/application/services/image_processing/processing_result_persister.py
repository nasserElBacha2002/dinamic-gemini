"""Phase 3+ — persist RESOLVED code-scan results as one Position with 0..N ProductRecords.

Reuses the manual image-result unit of work (atomic, lock + coverage uniqueness) so that a
code-scan run and an operator manual result can never both create a position for the same
``(job_id, source_asset_id)``.

Physical shelf association remains via sequential reconciliation (forward-fill).
Physical product stickers (D1 ``label_id``) are aisle-deduped via
``inventory_counted_product_labels`` UNIQUE(aisle_id, label_id).

Idempotent: existing coverage for ``(job_id, source_asset_id)`` → reconcile no-op.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum
from typing import Protocol, cast

from src.application.errors import (
    ImageAlreadyHasResultsError,
    ManualResultAlreadyExistsError,
    ProductLabelClaimRepositoryUnavailableError,
)
from src.application.ports.clock import Clock
from src.application.ports.image_position_label_detection_repository import (
    ImagePositionLabelDetectionRepository,
)
from src.application.ports.inventory_counted_product_label_repository import (
    InventoryCountedProductLabel,
)
from src.application.ports.job_source_asset_repository import JobSourceAssetRepository
from src.application.ports.manual_image_coverage_repository import ManualImageCoverageLink
from src.application.ports.manual_image_result_unit_of_work import (
    ManualImageResultUnitOfWork,
)
from src.application.ports.repositories import SourceAssetRepository
from src.application.services.image_processing.processing_result_kind import (
    get_result_kind,
    requires_product_persistence,
    validate_position_only_evidence,
)
from src.application.services.job_image_result_resolution import (
    JobPhotoCoverageImage,
    unique_photo_coverage_images,
)
from src.application.services.label_validation.integer_quantity import (
    coerce_positive_int_quantity,
)
from src.application.services.position_materialization import (
    CompleteMaterialization,
    MaterializePositionService,
    PositionMaterializationCoordinator,
    PreparationStatus,
    PrepareMaterialization,
    RecoverMaterialization,
)
from src.domain.evidence.entities import Evidence, EvidenceType
from src.domain.image_processing.contracts import (
    VISION_POSITION_DETECTOR_VERSION,
    ImageProcessingResult,
    ImageResultStatus,
)
from src.domain.position_materialization.entities import (
    PositionMaterializationAssociationReceipt,
)
from src.domain.positions.entities import (
    Position,
    PositionCreationSource,
    PositionStatus,
)
from src.domain.product_labels.processed import (
    ProcessedProductLabel,
    ProductLabelOutcomeStatus,
)
from src.domain.products.entities import ProductRecord
from src.domain.result_evidence.entities import (
    RESULT_EVIDENCE_KIND_ENTITY_TRACEABILITY,
    ResultEvidenceRecord,
    ResultEvidenceRole,
)
from src.domain.traceability import TraceabilityStatus

logger = logging.getLogger(__name__)

CODE_SCAN_PROVIDER = "code_scan"
CODE_SCAN_QTY_SOURCE = "label_explicit"
INTERNAL_OCR_PROVIDER = "internal_ocr"
INTERNAL_OCR_QTY_SOURCE = "ocr_extracted"
EXTERNAL_PROVIDER = "external_provider"
EXTERNAL_QTY_SOURCE = "external_provider"


class _LiveSourceAsset(Protocol):
    storage_path: str
    storage_key: str | None
    content_type: str | None
    file_size_bytes: int | None


class PersistSkipReason(str, Enum):
    ALREADY_PERSISTED = "ALREADY_PERSISTED"
    MANUAL_RESULT_EXISTS = "MANUAL_RESULT_EXISTS"
    ASSET_NOT_IN_SNAPSHOT = "ASSET_NOT_IN_SNAPSHOT"
    MISSING_CODE_OR_QUANTITY = "MISSING_CODE_OR_QUANTITY"
    CONCURRENCY_CONFLICT = "CONCURRENCY_CONFLICT"
    PERSISTENCE_ERROR = "PERSISTENCE_ERROR"
    NOT_RESOLVED_INTERNAL = "NOT_RESOLVED_INTERNAL"
    NON_POSITIVE_QUANTITY = "NON_POSITIVE_QUANTITY"
    ALL_LABELS_DUPLICATE = "ALL_LABELS_DUPLICATE"
    POSITION_MATERIALIZATION_FAILED = "POSITION_MATERIALIZATION_FAILED"


class PersistenceMode(str, Enum):
    SKIPPED = "SKIPPED"
    PRODUCTIVE = "PRODUCTIVE"
    IDENTITY_REVIEW = "IDENTITY_REVIEW"


@dataclass(frozen=True)
class PersistOutcome:
    persisted: bool
    reconciled: bool = False
    position_id: str | None = None
    active_result_id: str | None = None
    skipped_reason: PersistSkipReason | None = None
    products_persisted: int = 0
    products_skipped_duplicate: int = 0
    positions_persisted: int = 0
    idempotent_replay: bool = False
    retryable: bool = False
    persistence_mode: PersistenceMode | None = None

    def __post_init__(self) -> None:
        if self.persisted and self.skipped_reason is not None:
            raise ValueError("persisted=True cannot coexist with skipped_reason")
        mode = self.persistence_mode
        if mode is None:
            mode = PersistenceMode.PRODUCTIVE if self.persisted else PersistenceMode.SKIPPED
            object.__setattr__(self, "persistence_mode", mode)
        if self.persisted and mode is PersistenceMode.SKIPPED:
            raise ValueError("persisted=True cannot use persistence_mode=SKIPPED")
        if not self.persisted and mode is not PersistenceMode.SKIPPED:
            raise ValueError("persisted=False requires persistence_mode=SKIPPED")


@dataclass(frozen=True)
class _AutomaticPositionBundle:
    position: Position
    evidence: Evidence
    result_evidence: ResultEvidenceRecord
    coverage: ManualImageCoverageLink
    position_id: str
    provider: str
    entity_slug: str
    entity_uid: str
    qty_source: str


def _resolve_result_provider(result: ImageProcessingResult) -> tuple[str, str, str]:
    resolved_by = (result.resolved_by or CODE_SCAN_PROVIDER).strip()
    if (
        resolved_by.upper() == "EXTERNAL_PROVIDER"
        or resolved_by == EXTERNAL_PROVIDER
        or result.status is ImageResultStatus.RESOLVED_EXTERNAL
    ):
        provider = (result.provider_name or EXTERNAL_PROVIDER).strip() or EXTERNAL_PROVIDER
        return provider, EXTERNAL_QTY_SOURCE, "external"
    if resolved_by.upper() == "INTERNAL_OCR" or resolved_by == INTERNAL_OCR_PROVIDER:
        return INTERNAL_OCR_PROVIDER, INTERNAL_OCR_QTY_SOURCE, "internal_ocr"
    return CODE_SCAN_PROVIDER, CODE_SCAN_QTY_SOURCE, "code_scan"


def _build_automatic_position_bundle(
    *,
    result: ImageProcessingResult,
    inventory_id: str,
    aisle_id: str,
    snap: JobPhotoCoverageImage,
    live: _LiveSourceAsset | None,
    now,
    needs_review: bool,
    summary: dict,
    qty_source: str,
    provider: str,
    entity_slug: str,
    entity_uid: str,
) -> _AutomaticPositionBundle:
    position_id = str(uuid.uuid4())
    evidence_id = str(uuid.uuid4())
    result_evidence_id = str(uuid.uuid4())
    coverage_id = str(uuid.uuid4())
    job_id = result.job_id
    asset_id = result.asset_id
    storage_path = snap.storage_key or f"{entity_slug}://{asset_id}"
    if live is not None:
        storage_path = live.storage_path or live.storage_key or storage_path
    position = Position(
        id=position_id,
        aisle_id=aisle_id,
        status=PositionStatus.DETECTED,
        confidence=1.0,
        needs_review=needs_review,
        primary_evidence_id=evidence_id,
        created_at=now,
        updated_at=now,
        review_resolution=None,
        detected_summary_json=summary,
        corrected_summary_json=None,
        corrected_position_code=None,
        job_id=job_id,
        creation_source=PositionCreationSource.AUTOMATIC,
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
        inventory_id=inventory_id,
        aisle_id=aisle_id,
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
        provider=provider,
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
        aisle_id=aisle_id,
        inventory_id=inventory_id,
        created_by_user_id=None,
        created_at=now,
    )
    return _AutomaticPositionBundle(
        position=position,
        evidence=evidence,
        result_evidence=result_evidence,
        coverage=coverage,
        position_id=position_id,
        provider=provider,
        entity_slug=entity_slug,
        entity_uid=entity_uid,
        qty_source=qty_source,
    )


def _identity_code_from_result(result: ImageProcessingResult) -> str | None:
    code = (result.internal_code or "").strip()
    if code:
        return code
    for item in result.product_results or []:
        if isinstance(item, dict):
            from src.domain.product_labels.processed import ProcessedProductLabel

            item = ProcessedProductLabel.from_dict(item)
        label_id = (getattr(item, "label_id", None) or "").strip()
        internal = (getattr(item, "internal_code", None) or "").strip()
        logistic = (getattr(item, "logistic_unit_id", None) or "").strip()
        found = internal or label_id or logistic
        if found:
            return found
    return None


def _label_id_from_result(result: ImageProcessingResult) -> str | None:
    for item in result.product_results or []:
        if isinstance(item, dict):
            from src.domain.product_labels.processed import ProcessedProductLabel

            item = ProcessedProductLabel.from_dict(item)
        label_id = (getattr(item, "label_id", None) or "").strip()
        if label_id:
            return label_id
    return None


def _product_specs_from_result(result: ImageProcessingResult) -> list[ProcessedProductLabel]:
    specs: list[ProcessedProductLabel] = []
    for item in result.product_results or []:
        if isinstance(item, ProcessedProductLabel):
            label = item
        elif isinstance(item, dict):
            label = ProcessedProductLabel.from_dict(item)
        else:
            continue
        if label.validation_status is not ProductLabelOutcomeStatus.VALID:
            continue
        code = (label.internal_code or "").strip()
        qty = label.quantity
        if not code or qty is None or qty <= 0:
            continue
        specs.append(label)
    if specs:
        return specs
    code = (result.internal_code or "").strip()
    if not code:
        return []
    # Never invent quantity=0 from absence.
    if result.quantity is None:
        return []
    qty = coerce_positive_int_quantity(result.quantity)
    if qty is None or qty <= 0:
        return []
    return [
        ProcessedProductLabel(
            label_id=None,
            internal_code=code,
            quantity=qty,
            format_version=None,
            checksum=None,
            validation_status=ProductLabelOutcomeStatus.VALID,
        )
    ]


class ProcessingResultPersister:
    def __init__(
        self,
        *,
        job_source_asset_repo: JobSourceAssetRepository,
        source_asset_repo: SourceAssetRepository,
        clock: Clock,
        unit_of_work_factory: Callable[[], ManualImageResultUnitOfWork],
        position_detection_repo: ImagePositionLabelDetectionRepository | None = None,
        position_materializer: MaterializePositionService | None = None,
        position_auto_materialization_enabled: bool = False,
        flexible_validation_enabled: bool = False,
        flexible_code_scan_enabled: bool = False,
        flexible_vision_enabled: bool = False,
    ) -> None:
        self._job_source_asset_repo = job_source_asset_repo
        self._source_asset_repo = source_asset_repo
        self._clock = clock
        self._uow_factory = unit_of_work_factory
        self._position_detection_repo = position_detection_repo
        self._position_materializer = position_materializer
        self._position_auto_materialization_enabled = position_auto_materialization_enabled
        self._flexible_validation_enabled = bool(flexible_validation_enabled)
        self._flexible_code_scan_enabled = bool(flexible_code_scan_enabled)
        self._flexible_vision_enabled = bool(flexible_vision_enabled)

    def persist(
        self,
        *,
        result: ImageProcessingResult,
        inventory_id: str,
        aisle_id: str,
    ) -> PersistOutcome:
        identity_valid = False
        if isinstance(result.evidence, dict):
            identity_valid = bool(result.evidence.get("identity_valid"))
        has_identity = bool(_identity_code_from_result(result)) or identity_valid

        allowed_statuses = {
            ImageResultStatus.RESOLVED_INTERNAL,
            ImageResultStatus.RESOLVED_EXTERNAL,
        }
        # Identity-confirmed incomplete results must not disappear: allow review persist.
        if result.status is ImageResultStatus.PENDING_MANUAL_REVIEW and has_identity:
            allowed_statuses.add(ImageResultStatus.PENDING_MANUAL_REVIEW)

        if result.status not in allowed_statuses:
            return PersistOutcome(
                persisted=False, skipped_reason=PersistSkipReason.NOT_RESOLVED_INTERNAL
            )

        job_id = result.job_id
        asset_id = result.asset_id

        if not requires_product_persistence(result):
            return self._persist_position_only(
                result=result,
                inventory_id=inventory_id,
                aisle_id=aisle_id,
            )

        specs = _product_specs_from_result(result)
        if not specs:
            if has_identity:
                return self._persist_incomplete_identity_review(
                    result=result,
                    inventory_id=inventory_id,
                    aisle_id=aisle_id,
                )
            return PersistOutcome(
                persisted=False, skipped_reason=PersistSkipReason.MISSING_CODE_OR_QUANTITY
            )

        links = self._job_source_asset_repo.list_for_job(job_id)
        photo_by_asset = {img.source_asset_id: img for img in unique_photo_coverage_images(links)}
        snap = photo_by_asset.get(asset_id)
        if snap is None or not (snap.job_source_asset_id or "").strip():
            logger.warning(
                "code_scan.persist_skip_no_snapshot job_id=%s asset_id=%s",
                job_id,
                asset_id,
            )
            return PersistOutcome(
                persisted=False, skipped_reason=PersistSkipReason.ASSET_NOT_IN_SNAPSHOT
            )

        live = self._source_asset_repo.get_by_id(asset_id)
        now = self._clock.now()

        # Vision positions on product photos: persist detections + materialize before products.
        if result.vision_position_evidence:
            vision_block = self._persist_vision_positions_alongside_products(
                result=result,
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                snap=snap,
            )
            if vision_block is not None:
                return vision_block

        provider, qty_source, entity_slug = _resolve_result_provider(result)
        primary = specs[0]
        needs_review = False
        entity_uid = f"{job_id}_{entity_slug}_{asset_id}"

        summary: dict = {
            "entity_uid": entity_uid,
            "entity_type": "PALLET",
            "internal_code": primary.internal_code,
            "source_image_id": asset_id,
            "source_asset_id": asset_id,
            "source_image_original_filename": snap.original_filename,
            "source_image_sequence": snap.position_order + 1,
            "creation_source": PositionCreationSource.AUTOMATIC.value,
            "qty_source": qty_source,
            "qty_parse_status": "valid_positive",
            "quantity_status": "PRESENT",
            "resolved_by": provider,
            "product_count": len(specs),
            "product_label_ids": [s.label_id for s in specs if s.label_id],
        }
        bundle = _build_automatic_position_bundle(
            result=result,
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            snap=snap,
            live=live,
            now=now,
            needs_review=needs_review,
            summary=summary,
            qty_source=qty_source,
            provider=provider,
            entity_slug=entity_slug,
            entity_uid=entity_uid,
        )
        position = bundle.position
        evidence = bundle.evidence
        result_evidence = bundle.result_evidence
        coverage = bundle.coverage
        position_id = bundle.position_id


        products_persisted = 0
        products_skipped_duplicate = 0

        try:
            with self._uow_factory() as uow:
                uow.bind_lifecycle_scope(inventory_id=inventory_id, aisle_id=aisle_id)
                repos = uow.repositories
                uow.acquire_image_result_lock(job_id=job_id, source_asset_id=asset_id)

                existing = repos.manual_coverage_repo.get_by_job_and_asset(job_id, asset_id)
                if existing is not None:
                    if (existing.created_by_user_id or "").strip():
                        return PersistOutcome(
                            persisted=False,
                            reconciled=False,
                            position_id=existing.position_id,
                            skipped_reason=PersistSkipReason.MANUAL_RESULT_EXISTS,
                        )
                    linked = repos.position_repo.get_by_id(existing.position_id)
                    linked_job = (linked.job_id or "").strip() if linked is not None else ""
                    if linked is not None and linked_job == job_id:
                        return PersistOutcome(
                            persisted=False,
                            reconciled=True,
                            position_id=existing.position_id,
                            active_result_id=existing.position_id,
                            skipped_reason=PersistSkipReason.ALREADY_PERSISTED,
                        )
                    # Coverage points at a prior-job Position — heal by cloning under
                    # this job so Posiciones / has_result see a matching job_id.
                    logger.warning(
                        "code_scan.coverage_cross_job_heal job_id=%s asset_id=%s "
                        "coverage_position_id=%s linked_job_id=%s",
                        job_id,
                        asset_id,
                        existing.position_id,
                        linked_job or None,
                    )
                    return self._persist_same_asset_label_replay(
                        repos=repos,
                        uow=uow,
                        job_id=job_id,
                        asset_id=asset_id,
                        prior_position_id=existing.position_id,
                        skipped_duplicate=0,
                        position=position,
                        evidence=evidence,
                        coverage=coverage,
                        result_evidence=result_evidence,
                        specs=specs,
                        needs_review=needs_review,
                        qty_source=qty_source,
                        now=now,
                    )
                if repos.image_coverage_repo.has_results_for_asset(
                    job_id=job_id, aisle_id=aisle_id, source_asset_id=asset_id
                ):
                    return PersistOutcome(
                        persisted=False,
                        reconciled=True,
                        skipped_reason=PersistSkipReason.ALREADY_PERSISTED,
                    )

                counted_repo = repos.counted_product_label_repo
                products_to_save: list[ProductRecord] = []
                for spec in specs:
                    product_id = str(uuid.uuid4())
                    label_id = (spec.label_id or "").strip().upper() or None
                    qty = coerce_positive_int_quantity(spec.quantity)
                    if qty is None:
                        continue

                    if label_id:
                        if counted_repo is None:
                            raise ProductLabelClaimRepositoryUnavailableError(
                                "counted_product_label_repo required for D1 label_id persist"
                            )
                        claimed = counted_repo.try_claim(
                            InventoryCountedProductLabel(
                                id=str(uuid.uuid4()),
                                inventory_id=inventory_id,
                                aisle_id=aisle_id,
                                label_id=str(label_id),
                                first_product_record_id=product_id,
                                first_source_asset_id=asset_id,
                                first_job_id=job_id,
                                first_position_id=position_id,
                                created_at=now,
                            )
                        )
                        if not claimed:
                            products_skipped_duplicate += 1
                            logger.info(
                                "counted_product_label_duplicate_skip aisle_id=%s "
                                "label_id=%s job_id=%s asset_id=%s "
                                "ingestion_source=%s",
                                aisle_id,
                                label_id,
                                job_id,
                                asset_id,
                                (result.additional_fields or {}).get("ingestion_source"),
                            )
                            continue

                    products_to_save.append(
                        ProductRecord(
                            id=product_id,
                            position_id=position_id,
                            sku=str(spec.internal_code),
                            description=None,
                            detected_quantity=qty,
                            corrected_quantity=None,
                            confidence=1.0,
                            created_at=now,
                            updated_at=now,
                            qty_source=qty_source,
                            qty_inference_reason=None,
                            raw_qty=qty,
                            qty_parse_status="valid_positive",
                            label_id=label_id,
                        )
                    )

                if not products_to_save and products_skipped_duplicate:
                    # Same photos reprocessed: labels already claimed for this asset.
                    # Clone a Position under the current job so job-scoped coverage /
                    # Posiciones list / has_result (p.job_id match) all succeed.
                    replay = self._same_asset_duplicate_label_replay(
                        counted_repo=counted_repo,
                        specs=specs,
                        aisle_id=aisle_id,
                        asset_id=asset_id,
                    )
                    if replay is not None:
                        prior_position_id, skipped = replay
                        return self._persist_same_asset_label_replay(
                            repos=repos,
                            uow=uow,
                            job_id=job_id,
                            asset_id=asset_id,
                            prior_position_id=prior_position_id,
                            skipped_duplicate=skipped,
                            position=position,
                            evidence=evidence,
                            coverage=coverage,
                            result_evidence=result_evidence,
                            specs=specs,
                            needs_review=needs_review,
                            qty_source=qty_source,
                            now=now,
                        )
                    # Different asset already owns these labels — skip empty Position.
                    return PersistOutcome(
                        persisted=False,
                        skipped_reason=PersistSkipReason.ALL_LABELS_DUPLICATE,
                        products_skipped_duplicate=products_skipped_duplicate,
                    )

                if not products_to_save and not products_skipped_duplicate:
                    return PersistOutcome(
                        persisted=False,
                        skipped_reason=PersistSkipReason.MISSING_CODE_OR_QUANTITY,
                    )

                repos.position_repo.save(position)
                for product in products_to_save:
                    repos.product_record_repo.save(product)
                    products_persisted += 1
                repos.evidence_repo.save(evidence)
                repos.manual_coverage_repo.save(coverage)
                repos.result_evidence_repo.save_many([result_evidence])
                uow.commit()
        except (ManualResultAlreadyExistsError, ImageAlreadyHasResultsError):
            existing = self._lookup_existing_coverage(job_id, asset_id)
            if existing is not None:
                return PersistOutcome(
                    persisted=False,
                    reconciled=True,
                    position_id=existing.position_id,
                    active_result_id=existing.position_id,
                    skipped_reason=PersistSkipReason.CONCURRENCY_CONFLICT,
                )
            return PersistOutcome(
                persisted=False,
                reconciled=False,
                skipped_reason=PersistSkipReason.CONCURRENCY_CONFLICT,
            )

        logger.info(
            "code_scan.persisted_position job_id=%s asset_id=%s position_id=%s "
            "products_persisted=%s products_skipped_duplicate=%s",
            job_id,
            asset_id,
            position_id,
            products_persisted,
            products_skipped_duplicate,
        )
        return PersistOutcome(
            persisted=True,
            persistence_mode=PersistenceMode.PRODUCTIVE,
            position_id=position_id,
            active_result_id=position_id,
            products_persisted=products_persisted,
            products_skipped_duplicate=products_skipped_duplicate,
        )

    def _persist_incomplete_identity_review(
        self,
        *,
        result: ImageProcessingResult,
        inventory_id: str,
        aisle_id: str,
    ) -> PersistOutcome:
        """Persist identity + evidence + needs_review without inventing quantity=0.

        Productive ProductRecord is omitted until persistence_complete fields exist.
        Coverage uniqueness makes this idempotent on retry.
        """
        job_id = result.job_id
        asset_id = result.asset_id
        identity_code = _identity_code_from_result(result)
        if not identity_code:
            return PersistOutcome(
                persisted=False, skipped_reason=PersistSkipReason.MISSING_CODE_OR_QUANTITY
            )

        links = self._job_source_asset_repo.list_for_job(job_id)
        photo_by_asset = {img.source_asset_id: img for img in unique_photo_coverage_images(links)}
        snap = photo_by_asset.get(asset_id)
        if snap is None or not (snap.job_source_asset_id or "").strip():
            return PersistOutcome(
                persisted=False, skipped_reason=PersistSkipReason.ASSET_NOT_IN_SNAPSHOT
            )

        live = self._source_asset_repo.get_by_id(asset_id)
        now = self._clock.now()
        provider, _qty_source, entity_slug = _resolve_result_provider(result)
        entity_uid = f"{job_id}_{entity_slug}_{asset_id}"
        evidence_bag = result.evidence if isinstance(result.evidence, dict) else {}
        missing_fields = evidence_bag.get("missing_fields") or ["quantity"]
        label_id = _label_id_from_result(result)
        summary: dict = {
            "entity_uid": entity_uid,
            "entity_type": "PALLET",
            "internal_code": identity_code,
            "label_id": label_id,
            "source_image_id": asset_id,
            "source_asset_id": asset_id,
            "source_image_original_filename": snap.original_filename,
            "source_image_sequence": snap.position_order + 1,
            "creation_source": PositionCreationSource.AUTOMATIC.value,
            "qty_source": "unresolved",
            "qty_parse_status": "null",
            "quantity_status": "MISSING",
            "explicit_quantity_missing": True,
            "count_status": "NEEDS_REVIEW",
            "missing_fields": list(missing_fields),
            "identity_valid": True,
            "enrichment_complete": False,
            "error_code": result.error_code or "MISSING_QUANTITY",
            "resolved_by": provider,
            "product_count": 0,
            "product_label_ids": [label_id] if label_id else [],
        }
        bundle = _build_automatic_position_bundle(
            result=result,
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            snap=snap,
            live=live,
            now=now,
            needs_review=True,
            summary=summary,
            qty_source="unresolved",
            provider=provider,
            entity_slug=entity_slug,
            entity_uid=entity_uid,
        )
        position = bundle.position
        evidence = bundle.evidence
        result_evidence = bundle.result_evidence
        coverage = bundle.coverage
        position_id = bundle.position_id

        try:
            with self._uow_factory() as uow:
                uow.bind_lifecycle_scope(inventory_id=inventory_id, aisle_id=aisle_id)
                repos = uow.repositories
                uow.acquire_image_result_lock(job_id=job_id, source_asset_id=asset_id)

                existing = repos.manual_coverage_repo.get_by_job_and_asset(job_id, asset_id)
                if existing is not None:
                    if (existing.created_by_user_id or "").strip():
                        return PersistOutcome(
                            persisted=False,
                            reconciled=False,
                            position_id=existing.position_id,
                            skipped_reason=PersistSkipReason.MANUAL_RESULT_EXISTS,
                        )
                    linked = repos.position_repo.get_by_id(existing.position_id)
                    linked_job = (linked.job_id or "").strip() if linked is not None else ""
                    if linked is not None and linked_job == job_id:
                        return PersistOutcome(
                            persisted=True,
                            persistence_mode=PersistenceMode.IDENTITY_REVIEW,
                            reconciled=True,
                            position_id=existing.position_id,
                            active_result_id=existing.position_id,
                            idempotent_replay=True,
                            products_persisted=0,
                        )
                    return PersistOutcome(
                        persisted=False,
                        position_id=existing.position_id,
                        skipped_reason=PersistSkipReason.ALREADY_PERSISTED,
                    )

                repos.position_repo.save(position)
                repos.evidence_repo.save(evidence)
                repos.result_evidence_repo.save_many([result_evidence])
                repos.manual_coverage_repo.save(coverage)
                uow.commit()
        except ManualResultAlreadyExistsError:
            return PersistOutcome(
                persisted=False, skipped_reason=PersistSkipReason.MANUAL_RESULT_EXISTS
            )
        except ImageAlreadyHasResultsError:
            return PersistOutcome(
                persisted=False, skipped_reason=PersistSkipReason.ALREADY_PERSISTED
            )

        logger.info(
            "code_scan.identity_review_persisted job_id=%s asset_id=%s position_id=%s "
            "internal_code=%s quantity_status=MISSING",
            job_id,
            asset_id,
            position_id,
            identity_code,
        )
        return PersistOutcome(
            persisted=True,
            persistence_mode=PersistenceMode.IDENTITY_REVIEW,
            position_id=position_id,
            active_result_id=position_id,
            products_persisted=0,
        )

    def _persist_position_only(
        self,
        *,
        result: ImageProcessingResult,
        inventory_id: str,
        aisle_id: str,
    ) -> PersistOutcome:
        """Persist POSITION_ONLY evidence and optionally materialize canonical locations."""
        job_id = result.job_id
        asset_id = result.asset_id
        result_kind = get_result_kind(result)

        ok, detail = validate_position_only_evidence(result)
        if not ok:
            logger.warning(
                "code_scan.position_only_validation_failed job_id=%s asset_id=%s "
                "result_kind=%s detail=%s",
                job_id,
                asset_id,
                result_kind,
                detail,
            )
            return PersistOutcome(
                persisted=False,
                skipped_reason=PersistSkipReason.POSITION_MATERIALIZATION_FAILED,
            )

        links = self._job_source_asset_repo.list_for_job(job_id)
        photo_by_asset = {img.source_asset_id: img for img in unique_photo_coverage_images(links)}
        snap = photo_by_asset.get(asset_id)
        if snap is None or not (snap.job_source_asset_id or "").strip():
            logger.warning(
                "code_scan.position_only_skip_no_snapshot job_id=%s asset_id=%s",
                job_id,
                asset_id,
            )
            return PersistOutcome(
                persisted=False, skipped_reason=PersistSkipReason.ASSET_NOT_IN_SNAPSHOT
            )

        materialize_enabled = self._channel_materialization_enabled(result)
        coordinator = PositionMaterializationCoordinator(
            clock=self._clock,
            detection_repo=self._position_detection_repo,
            materializer=self._position_materializer,
            enabled=materialize_enabled,
        )
        if materialize_enabled:
            conflict = self._preflight_position_only_conflict(
                job_id=job_id,
                asset_id=asset_id,
                inventory_id=inventory_id,
                aisle_id=aisle_id,
            )
            if conflict is not None:
                if conflict.skipped_reason is PersistSkipReason.ALREADY_PERSISTED:
                    recovered_replay = coordinator.recover(
                        RecoverMaterialization(
                            result=result,
                            job_id=job_id,
                            asset_id=asset_id,
                            inventory_id=inventory_id,
                            aisle_id=aisle_id,
                        )
                    )
                    if recovered_replay is not None:
                        conflict = replace(
                            conflict,
                            idempotent_replay=recovered_replay,
                        )
                return conflict
        prepared = coordinator.prepare(
            PrepareMaterialization(
                result=result,
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                snapshot=snap,
            )
        )
        if not prepared.ready:
            if prepared.status is PreparationStatus.TECHNICAL_RETRY:
                return PersistOutcome(
                    persisted=False,
                    skipped_reason=PersistSkipReason.POSITION_MATERIALIZATION_FAILED,
                    retryable=True,
                )
            # Do not fail the asset when location materialization rejects — still persist
            # position-label evidence so operational sequence stays coherent.
            logger.warning(
                "code_scan.position_only_materialization_degraded job_id=%s asset_id=%s "
                "prep_status=%s",
                job_id,
                asset_id,
                prepared.status.value,
            )
            coordinator = PositionMaterializationCoordinator(
                clock=self._clock,
                detection_repo=self._position_detection_repo,
                materializer=self._position_materializer,
                enabled=False,
            )
            prepared = coordinator.prepare(
                PrepareMaterialization(
                    result=result,
                    inventory_id=inventory_id,
                    aisle_id=aisle_id,
                    snapshot=snap,
                )
            )
            if not prepared.ready:
                return PersistOutcome(
                    persisted=False,
                    skipped_reason=PersistSkipReason.POSITION_MATERIALIZATION_FAILED,
                )
        valid_detections = list(prepared.detections)
        if self._position_detection_repo is not None and not valid_detections:
            return PersistOutcome(
                persisted=False,
                skipped_reason=PersistSkipReason.POSITION_MATERIALIZATION_FAILED,
            )
        materialization_replayed = prepared.idempotent_replay
        positions_count = len(valid_detections) if valid_detections else 1
        anchor_id = valid_detections[0].id if valid_detections else None
        now = self._clock.now()
        result_evidence_id = str(uuid.uuid4())
        entity_uid = f"{job_id}_position_only_{asset_id}"

        try:
            with self._uow_factory() as uow:
                uow.bind_lifecycle_scope(inventory_id=inventory_id, aisle_id=aisle_id)
                repos = uow.repositories
                uow.acquire_image_result_lock(job_id=job_id, source_asset_id=asset_id)

                existing = repos.manual_coverage_repo.get_by_job_and_asset(job_id, asset_id)
                if existing is not None:
                    if (existing.created_by_user_id or "").strip():
                        coordinator.complete(
                            CompleteMaterialization(
                                prepared=prepared,
                                success=False,
                                error_code="IMAGE_MANUAL_RESULT_CONFLICT",
                            )
                        )
                        return PersistOutcome(
                            persisted=False,
                            reconciled=False,
                            position_id=existing.position_id,
                            skipped_reason=PersistSkipReason.MANUAL_RESULT_EXISTS,
                        )
                    coordinator.complete(CompleteMaterialization(prepared=prepared, success=True))
                    return PersistOutcome(
                        persisted=False,
                        reconciled=True,
                        position_id=existing.position_id,
                        active_result_id=existing.position_id,
                        skipped_reason=PersistSkipReason.ALREADY_PERSISTED,
                        positions_persisted=positions_count,
                        idempotent_replay=materialization_replayed,
                    )

                existing_evidence = self._find_result_evidence_for_asset(
                    repos.result_evidence_repo, job_id, asset_id
                )
                if existing_evidence is not None and existing_evidence.has_valid_evidence:
                    coordinator.complete(CompleteMaterialization(prepared=prepared, success=True))
                    return PersistOutcome(
                        persisted=False,
                        reconciled=True,
                        position_id=existing_evidence.position_id or anchor_id,
                        active_result_id=existing_evidence.position_id or anchor_id,
                        skipped_reason=PersistSkipReason.ALREADY_PERSISTED,
                        positions_persisted=positions_count,
                        idempotent_replay=materialization_replayed,
                    )

                result_evidence = ResultEvidenceRecord(
                    id=result_evidence_id,
                    job_id=job_id,
                    inventory_id=inventory_id,
                    aisle_id=aisle_id,
                    position_id=anchor_id,
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
                    provider=CODE_SCAN_PROVIDER,
                    model_name=None,
                    schema_version=None,
                    manifest_version=None,
                    has_valid_evidence=True,
                    evidence_kind=RESULT_EVIDENCE_KIND_ENTITY_TRACEABILITY,
                    created_at=now,
                    updated_at=now,
                )
                repos.result_evidence_repo.save_many([result_evidence])
                if prepared.associations:
                    if repos.materialization_receipt_repo is None:
                        raise RuntimeError(
                            "Materialization receipt repository is required when auto-materialization is active"
                        )
                    for association in prepared.associations:
                        repos.materialization_receipt_repo.save(
                            PositionMaterializationAssociationReceipt(
                                request_id=association.request_id,
                                target_type="IMAGE_RESULT",
                                target_id=result_evidence_id,
                                created_at=now,
                                source_detection_id=association.detection_id,
                            )
                        )
                uow.commit()
        except (ManualResultAlreadyExistsError, ImageAlreadyHasResultsError):
            coordinator.complete(
                CompleteMaterialization(
                    prepared=prepared,
                    success=False,
                    error_code="IMAGE_RESULT_CONCURRENCY_CONFLICT",
                )
            )
            existing = self._lookup_existing_coverage(job_id, asset_id)
            if existing is not None:
                return PersistOutcome(
                    persisted=False,
                    reconciled=True,
                    position_id=existing.position_id,
                    active_result_id=existing.position_id,
                    skipped_reason=PersistSkipReason.CONCURRENCY_CONFLICT,
                    positions_persisted=positions_count,
                )
            return PersistOutcome(
                persisted=False,
                reconciled=False,
                skipped_reason=PersistSkipReason.CONCURRENCY_CONFLICT,
            )

        coordinator.complete(CompleteMaterialization(prepared=prepared, success=True))
        logger.info(
            "code_scan.position_only_persisted job_id=%s asset_id=%s result_kind=%s "
            "positions_persisted=%s anchor_detection_id=%s",
            job_id,
            asset_id,
            result_kind,
            positions_count,
            anchor_id,
        )
        return PersistOutcome(
            persisted=True,
            reconciled=True,
            position_id=anchor_id,
            active_result_id=anchor_id,
            products_persisted=0,
            positions_persisted=positions_count,
            idempotent_replay=materialization_replayed,
        )

    def _preflight_position_only_conflict(
        self,
        *,
        job_id: str,
        asset_id: str,
        inventory_id: str,
        aisle_id: str,
    ) -> PersistOutcome | None:
        """Check image ownership under the manual-result lock before materialization."""
        try:
            with self._uow_factory() as uow:
                uow.bind_lifecycle_scope(
                    inventory_id=inventory_id,
                    aisle_id=aisle_id,
                )
                repos = uow.repositories
                uow.acquire_image_result_lock(
                    job_id=job_id,
                    source_asset_id=asset_id,
                )
                existing = repos.manual_coverage_repo.get_by_job_and_asset(
                    job_id,
                    asset_id,
                )
                if existing is not None:
                    if (existing.created_by_user_id or "").strip():
                        return PersistOutcome(
                            persisted=False,
                            position_id=existing.position_id,
                            skipped_reason=PersistSkipReason.MANUAL_RESULT_EXISTS,
                        )
                    return PersistOutcome(
                        persisted=False,
                        reconciled=True,
                        position_id=existing.position_id,
                        active_result_id=existing.position_id,
                        skipped_reason=PersistSkipReason.ALREADY_PERSISTED,
                    )
                if repos.image_coverage_repo.has_results_for_asset(
                    job_id=job_id,
                    aisle_id=aisle_id,
                    source_asset_id=asset_id,
                ):
                    return PersistOutcome(
                        persisted=False,
                        reconciled=True,
                        skipped_reason=PersistSkipReason.ALREADY_PERSISTED,
                    )
                existing_evidence = self._find_result_evidence_for_asset(
                    repos.result_evidence_repo,
                    job_id,
                    asset_id,
                )
                if existing_evidence is not None and existing_evidence.has_valid_evidence:
                    return PersistOutcome(
                        persisted=False,
                        reconciled=True,
                        position_id=existing_evidence.position_id,
                        active_result_id=existing_evidence.position_id,
                        skipped_reason=PersistSkipReason.ALREADY_PERSISTED,
                    )
        except (ManualResultAlreadyExistsError, ImageAlreadyHasResultsError):
            return PersistOutcome(
                persisted=False,
                skipped_reason=PersistSkipReason.CONCURRENCY_CONFLICT,
            )
        return None

    def _persist_vision_positions_alongside_products(
        self,
        *,
        result: ImageProcessingResult,
        inventory_id: str,
        aisle_id: str,
        snap: JobPhotoCoverageImage,
    ) -> PersistOutcome | None:
        """Persist + materialize vision position detections before product rows.

        Returns a retryable failure outcome when materialization must abort the
        asset; otherwise returns ``None`` so product persistence continues.
        """
        job_id = result.job_id
        asset_id = result.asset_id
        materialize_enabled = self._channel_materialization_enabled(result)
        coordinator = PositionMaterializationCoordinator(
            clock=self._clock,
            detection_repo=self._position_detection_repo,
            materializer=self._position_materializer,
            enabled=materialize_enabled,
        )
        prepared = coordinator.prepare(
            PrepareMaterialization(
                result=result,
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                snapshot=snap,
            )
        )
        if not prepared.ready:
            if prepared.status is PreparationStatus.TECHNICAL_RETRY:
                return PersistOutcome(
                    persisted=False,
                    skipped_reason=PersistSkipReason.POSITION_MATERIALIZATION_FAILED,
                    retryable=True,
                )
            logger.warning(
                "code_scan.vision_alongside_products_materialization_degraded "
                "job_id=%s asset_id=%s prep_status=%s",
                job_id,
                asset_id,
                prepared.status.value,
            )
            # Detections may already be persisted from the failed attempt; listing
            # them with materialization off keeps product persistence unblocked.
            coordinator = PositionMaterializationCoordinator(
                clock=self._clock,
                detection_repo=self._position_detection_repo,
                materializer=self._position_materializer,
                enabled=False,
            )
            prepared = coordinator.prepare(
                PrepareMaterialization(
                    result=result,
                    inventory_id=inventory_id,
                    aisle_id=aisle_id,
                    snapshot=snap,
                )
            )
            if not prepared.ready:
                return PersistOutcome(
                    persisted=False,
                    skipped_reason=PersistSkipReason.POSITION_MATERIALIZATION_FAILED,
                    retryable=prepared.status is PreparationStatus.TECHNICAL_RETRY,
                )
        coordinator.complete(CompleteMaterialization(prepared=prepared, success=True))
        if prepared.associations:
            try:
                with self._uow_factory() as uow:
                    uow.bind_lifecycle_scope(inventory_id=inventory_id, aisle_id=aisle_id)
                    repos = uow.repositories
                    if repos.materialization_receipt_repo is not None:
                        now = self._clock.now()
                        for association in prepared.associations:
                            repos.materialization_receipt_repo.save(
                                PositionMaterializationAssociationReceipt(
                                    request_id=association.request_id,
                                    target_type="IMAGE_RESULT",
                                    target_id=association.detection_id,
                                    created_at=now,
                                    source_detection_id=association.detection_id,
                                )
                            )
                        uow.commit()
            except Exception:
                logger.warning(
                    "code_scan.vision_alongside_products_receipt_save_failed "
                    "job_id=%s asset_id=%s",
                    job_id,
                    asset_id,
                    exc_info=True,
                )
        logger.info(
            "code_scan.vision_alongside_products_ready job_id=%s asset_id=%s "
            "detections=%s associations=%s",
            job_id,
            asset_id,
            len(prepared.detections),
            len(prepared.associations),
        )
        return None

    def _persist_same_asset_label_replay(
        self,
        *,
        repos,
        uow,
        job_id: str,
        asset_id: str,
        prior_position_id: str,
        skipped_duplicate: int,
        position: Position,
        evidence: Evidence,
        coverage: ManualImageCoverageLink,
        result_evidence: ResultEvidenceRecord,
        specs: list[ProcessedProductLabel],
        needs_review: bool,
        qty_source: str,
        now,
    ) -> PersistOutcome:
        """Reprocess same photos: ensure a Position exists under the current job_id.

        Job-scoped Posiciones lists and ``has_result`` require ``positions.job_id`` to
        match the active job. Linking coverage to a prior-job Position leaves the
        table empty and the image uncounted.
        """
        prior = repos.position_repo.get_by_id(prior_position_id)
        prior_job = (prior.job_id or "").strip() if prior is not None else ""
        existing_cov: ManualImageCoverageLink | None = (
            repos.manual_coverage_repo.get_by_job_and_asset(job_id, asset_id)
        )
        existing_re: ResultEvidenceRecord | None = self._find_result_evidence_for_asset(
            repos.result_evidence_repo, job_id, asset_id
        )

        def _coverage_for(target_position_id: str) -> ManualImageCoverageLink:
            if existing_cov is not None:
                return replace(existing_cov, position_id=target_position_id)
            return replace(coverage, position_id=target_position_id)

        def _result_evidence_for(target_position_id: str) -> ResultEvidenceRecord:
            if existing_re is not None:
                return replace(existing_re, position_id=target_position_id, updated_at=now)
            return replace(result_evidence, position_id=target_position_id)

        if prior is not None and prior_job == job_id:
            coverage_same = _coverage_for(prior_position_id)
            evidence_same = replace(evidence, entity_id=prior_position_id)
            result_evidence_same = _result_evidence_for(prior_position_id)
            repos.evidence_repo.save(evidence_same)
            repos.manual_coverage_repo.save(coverage_same)
            repos.result_evidence_repo.save_many([result_evidence_same])
            uow.commit()
            logger.info(
                "code_scan.persisted_duplicate_label_replay_same_job job_id=%s "
                "asset_id=%s position_id=%s products_skipped_duplicate=%s",
                job_id,
                asset_id,
                prior_position_id,
                skipped_duplicate,
            )
            return PersistOutcome(
                persisted=True,
                position_id=prior_position_id,
                active_result_id=prior_position_id,
                products_persisted=0,
                products_skipped_duplicate=skipped_duplicate,
                idempotent_replay=True,
            )

        cloned_products: list[ProductRecord] = []
        prior_products = (
            list(repos.product_record_repo.list_by_position(prior_position_id))
            if prior is not None
            else []
        )
        if prior_products:
            for product in prior_products:
                cloned_products.append(
                    replace(
                        product,
                        id=str(uuid.uuid4()),
                        position_id=position.id,
                        created_at=now,
                        updated_at=now,
                    )
                )
        else:
            for spec in specs:
                label_id = (spec.label_id or "").strip().upper() or None
                qty = coerce_positive_int_quantity(spec.quantity)
                if qty is None:
                    continue
                cloned_products.append(
                    ProductRecord(
                        id=str(uuid.uuid4()),
                        position_id=position.id,
                        sku=str(spec.internal_code),
                        description=None,
                        detected_quantity=qty,
                        corrected_quantity=None,
                        confidence=1.0,
                        created_at=now,
                        updated_at=now,
                        qty_source=qty_source,
                        qty_inference_reason=None,
                        raw_qty=qty,
                        qty_parse_status="valid_positive",
                        label_id=label_id,
                    )
                )

        coverage_clone = _coverage_for(position.id)
        result_evidence_clone = _result_evidence_for(position.id)
        repos.position_repo.save(position)
        for product in cloned_products:
            repos.product_record_repo.save(product)
        repos.evidence_repo.save(evidence)
        repos.manual_coverage_repo.save(coverage_clone)
        repos.result_evidence_repo.save_many([result_evidence_clone])
        uow.commit()
        logger.info(
            "code_scan.persisted_duplicate_label_replay_clone job_id=%s asset_id=%s "
            "position_id=%s prior_position_id=%s products_persisted=%s "
            "products_skipped_duplicate=%s",
            job_id,
            asset_id,
            position.id,
            prior_position_id,
            len(cloned_products),
            skipped_duplicate,
        )
        return PersistOutcome(
            persisted=True,
            position_id=position.id,
            active_result_id=position.id,
            products_persisted=len(cloned_products),
            products_skipped_duplicate=skipped_duplicate,
            idempotent_replay=True,
        )

    @staticmethod
    def _same_asset_duplicate_label_replay(
        *,
        counted_repo,
        specs: list[ProcessedProductLabel],
        aisle_id: str,
        asset_id: str,
    ) -> tuple[str, int] | None:
        """If every D1 label was first claimed on this asset, return prior position_id.

        Reprocess of the same photos must not leave the job without coverage.
        Cross-asset duplicates (true aisle dedupe) return None.
        """
        if counted_repo is None:
            return None
        position_ids: set[str] = set()
        skipped = 0
        for spec in specs:
            label_id = (spec.label_id or "").strip().upper() or None
            if not label_id:
                return None
            claim = counted_repo.get(aisle_id, label_id)
            if claim is None:
                return None
            if (claim.first_source_asset_id or "").strip() != (asset_id or "").strip():
                return None
            pid = (claim.first_position_id or "").strip()
            if not pid:
                return None
            position_ids.add(pid)
            skipped += 1
        if len(position_ids) != 1 or skipped == 0:
            return None
        return next(iter(position_ids)), skipped

    @staticmethod
    def _find_result_evidence_for_asset(
        result_evidence_repo, job_id: str, asset_id: str
    ) -> ResultEvidenceRecord | None:
        if result_evidence_repo is None:
            return None
        try:
            rows = result_evidence_repo.list_by_job_id(job_id)
        except Exception:
            return None
        for row in rows:
            if (row.source_asset_id or "").strip() == asset_id:
                return cast(ResultEvidenceRecord, row)
        return None

    def _lookup_existing_coverage(self, job_id: str, asset_id: str):
        try:
            with self._uow_factory() as uow:
                return uow.repositories.manual_coverage_repo.get_by_job_and_asset(job_id, asset_id)
        except Exception:
            logger.warning(
                "code_scan.persist_conflict_lookup_failed job_id=%s asset_id=%s",
                job_id,
                asset_id,
            )
            return None

    def _channel_materialization_enabled(self, result: ImageProcessingResult) -> bool:
        """Gate auto-materialization; keep CODE_SCAN vs VISION independent when flexible.

        Phase 3: ``position_auto_materialization_enabled`` alone enables materialization of
        already-validated detections (legacy preexistence path).

        Phase 5: when the flexible master is on, each channel must also be enabled —
        Vision ON must not enable CODE_SCAN materialization and vice versa.
        """
        if not self._position_auto_materialization_enabled:
            return False
        if not self._flexible_validation_enabled:
            return True
        if result.vision_position_evidence:
            return self._flexible_vision_enabled
        return self._flexible_code_scan_enabled


__all__ = [
    "VISION_POSITION_DETECTOR_VERSION",
    "PersistOutcome",
    "PersistSkipReason",
    "PersistenceMode",
    "ProcessingResultPersister",
]
