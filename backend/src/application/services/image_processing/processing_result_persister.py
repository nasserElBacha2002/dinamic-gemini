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
from dataclasses import dataclass
from enum import Enum

from src.application.errors import (
    ImageAlreadyHasResultsError,
    ManualResultAlreadyExistsError,
    ProductLabelClaimRepositoryUnavailableError,
)
from src.application.ports.clock import Clock
from src.application.ports.inventory_counted_product_label_repository import (
    InventoryCountedProductLabel,
)
from src.application.ports.job_source_asset_repository import JobSourceAssetRepository
from src.application.ports.manual_image_coverage_repository import ManualImageCoverageLink
from src.application.ports.manual_image_result_unit_of_work import (
    ManualImageResultUnitOfWork,
)
from src.application.ports.repositories import SourceAssetRepository
from src.application.services.job_image_result_resolution import (
    unique_photo_coverage_images,
)
from src.domain.evidence.entities import Evidence, EvidenceType
from src.domain.image_processing.contracts import ImageProcessingResult, ImageResultStatus
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


@dataclass(frozen=True)
class PersistOutcome:
    persisted: bool
    reconciled: bool = False
    position_id: str | None = None
    active_result_id: str | None = None
    skipped_reason: PersistSkipReason | None = None
    products_persisted: int = 0
    products_skipped_duplicate: int = 0


def _coerce_positive_int_quantity(quantity: object) -> int | None:
    if isinstance(quantity, bool):
        return None
    if isinstance(quantity, int):
        return quantity
    if isinstance(quantity, float) and quantity.is_integer():
        return int(quantity)
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
    if result.quantity is None:
        return [
            ProcessedProductLabel(
                label_id=None,
                internal_code=code,
                quantity=0,
                format_version=None,
                checksum=None,
                validation_status=ProductLabelOutcomeStatus.VALID,
                detail="legacy_missing_quantity",
            )
        ]
    qty = _coerce_positive_int_quantity(result.quantity)
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
    ) -> None:
        self._job_source_asset_repo = job_source_asset_repo
        self._source_asset_repo = source_asset_repo
        self._clock = clock
        self._uow_factory = unit_of_work_factory

    def persist(
        self,
        *,
        result: ImageProcessingResult,
        inventory_id: str,
        aisle_id: str,
    ) -> PersistOutcome:
        if (
            result.status is not ImageResultStatus.RESOLVED_INTERNAL
            and result.status is not ImageResultStatus.RESOLVED_EXTERNAL
        ):
            return PersistOutcome(
                persisted=False, skipped_reason=PersistSkipReason.NOT_RESOLVED_INTERNAL
            )

        specs = _product_specs_from_result(result)
        if not specs:
            return PersistOutcome(
                persisted=False, skipped_reason=PersistSkipReason.MISSING_CODE_OR_QUANTITY
            )

        job_id = result.job_id
        asset_id = result.asset_id

        links = self._job_source_asset_repo.list_for_job(job_id)
        photo_by_asset = {
            img.source_asset_id: img for img in unique_photo_coverage_images(links)
        }
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
        position_id = str(uuid.uuid4())
        evidence_id = str(uuid.uuid4())
        result_evidence_id = str(uuid.uuid4())
        coverage_id = str(uuid.uuid4())

        resolved_by = (result.resolved_by or CODE_SCAN_PROVIDER).strip()
        if (
            resolved_by.upper() == "EXTERNAL_PROVIDER"
            or resolved_by == EXTERNAL_PROVIDER
            or result.status is ImageResultStatus.RESOLVED_EXTERNAL
        ):
            provider = (result.provider_name or EXTERNAL_PROVIDER).strip() or EXTERNAL_PROVIDER
            qty_source = EXTERNAL_QTY_SOURCE
            entity_slug = "external"
        elif resolved_by.upper() == "INTERNAL_OCR" or resolved_by == INTERNAL_OCR_PROVIDER:
            provider = INTERNAL_OCR_PROVIDER
            qty_source = INTERNAL_OCR_QTY_SOURCE
            entity_slug = "internal_ocr"
        else:
            provider = CODE_SCAN_PROVIDER
            qty_source = CODE_SCAN_QTY_SOURCE
            entity_slug = "code_scan"

        primary = specs[0]
        needs_review = (primary.quantity or 0) == 0 and primary.detail == "legacy_missing_quantity"
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
            "qty_source": "unresolved" if needs_review else qty_source,
            "qty_parse_status": "null" if needs_review else "valid_positive",
            "resolved_by": provider,
            "product_count": len(specs),
            "product_label_ids": [s.label_id for s in specs if s.label_id],
        }
        if needs_review:
            summary["count_status"] = "NEEDS_REVIEW"
            summary["explicit_quantity_missing"] = True

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

        products_persisted = 0
        products_skipped_duplicate = 0

        try:
            with self._uow_factory() as uow:
                if hasattr(uow, "bind_lifecycle_scope"):
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
                    return PersistOutcome(
                        persisted=False,
                        reconciled=True,
                        position_id=existing.position_id,
                        active_result_id=existing.position_id,
                        skipped_reason=PersistSkipReason.ALREADY_PERSISTED,
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
                    if needs_review and int(spec.quantity or 0) == 0:
                        products_to_save.append(
                            ProductRecord(
                                id=product_id,
                                position_id=position_id,
                                sku=str(spec.internal_code),
                                description=None,
                                detected_quantity=0,
                                corrected_quantity=None,
                                confidence=1.0,
                                created_at=now,
                                updated_at=now,
                                qty_source="unresolved",
                                qty_inference_reason=None,
                                raw_qty=None,
                                qty_parse_status="null",
                                label_id=label_id,
                            )
                        )
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
                            continue

                    products_to_save.append(
                        ProductRecord(
                            id=product_id,
                            position_id=position_id,
                            sku=str(spec.internal_code),
                            description=None,
                            detected_quantity=int(spec.quantity or 0),
                            corrected_quantity=None,
                            confidence=1.0,
                            created_at=now,
                            updated_at=now,
                            qty_source=qty_source,
                            qty_inference_reason=None,
                            raw_qty=int(spec.quantity or 0),
                            qty_parse_status="valid_positive",
                            label_id=label_id,
                        )
                    )

                if not products_to_save and products_skipped_duplicate:
                    # All D1 labels already counted — do not create empty Position/coverage.
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
            position_id=position_id,
            active_result_id=position_id,
            products_persisted=products_persisted,
            products_skipped_duplicate=products_skipped_duplicate,
        )

    def _lookup_existing_coverage(self, job_id: str, asset_id: str):
        try:
            with self._uow_factory() as uow:
                return uow.repositories.manual_coverage_repo.get_by_job_and_asset(
                    job_id, asset_id
                )
        except Exception:
            logger.warning(
                "code_scan.persist_conflict_lookup_failed job_id=%s asset_id=%s",
                job_id,
                asset_id,
            )
            return None


__all__ = ["PersistOutcome", "PersistSkipReason", "ProcessingResultPersister"]
