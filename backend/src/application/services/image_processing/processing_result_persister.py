"""Phase 3 — persist a RESOLVED_INTERNAL code-scan result as one automatic position.

Reuses the manual image-result unit of work (atomic, lock + coverage uniqueness) so that a
code-scan run and an operator manual result can never both create a position for the same
``(job_id, source_asset_id)``. Physical rule: ONE image → at most ONE position.

Idempotent: if a position/coverage already exists for this ``(job_id, source_asset_id)`` the
persist is a no-op (reconcile) rather than a duplicate insert. Two *different* assets that
carry the same internal code produce two positions (no dedupe by code).
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
)
from src.application.ports.clock import Clock
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


class PersistSkipReason(str, Enum):
    ALREADY_PERSISTED = "ALREADY_PERSISTED"
    MANUAL_RESULT_EXISTS = "MANUAL_RESULT_EXISTS"
    ASSET_NOT_IN_SNAPSHOT = "ASSET_NOT_IN_SNAPSHOT"
    MISSING_CODE_OR_QUANTITY = "MISSING_CODE_OR_QUANTITY"
    CONCURRENCY_CONFLICT = "CONCURRENCY_CONFLICT"
    PERSISTENCE_ERROR = "PERSISTENCE_ERROR"
    NOT_RESOLVED_INTERNAL = "NOT_RESOLVED_INTERNAL"
    NON_POSITIVE_QUANTITY = "NON_POSITIVE_QUANTITY"


@dataclass(frozen=True)
class PersistOutcome:
    """Outcome of one persist attempt for a RESOLVED_INTERNAL code-scan result.

    - ``persisted``: a new position was written by this call.
    - ``reconciled``: a position already exists for ``(job_id, source_asset_id)`` created by a
      prior code-scan run (or won by a concurrent code-scan worker); the asset is still
      legitimately RESOLVED and callers must NOT downgrade it. ``persisted=False`` +
      ``reconciled=False`` means the caller must NOT finalize as RESOLVED.
    """

    persisted: bool
    reconciled: bool = False
    position_id: str | None = None
    active_result_id: str | None = None
    skipped_reason: PersistSkipReason | None = None


def _coerce_positive_int_quantity(quantity: object) -> int | None:
    """Return a positive int quantity, or ``None`` when the value is not a whole number.

    Never truncates a real decimal (2.7 → rejected, not 2). Booleans are rejected (``bool`` is
    an ``int`` subclass but is never a valid quantity).
    """
    if isinstance(quantity, bool):
        return None
    if isinstance(quantity, int):
        return quantity
    if isinstance(quantity, float) and quantity.is_integer():
        return int(quantity)
    return None


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
        if result.status is not ImageResultStatus.RESOLVED_INTERNAL:
            return PersistOutcome(
                persisted=False, skipped_reason=PersistSkipReason.NOT_RESOLVED_INTERNAL
            )
        code = (result.internal_code or "").strip()
        if not code or result.quantity is None:
            return PersistOutcome(
                persisted=False, skipped_reason=PersistSkipReason.MISSING_CODE_OR_QUANTITY
            )
        quantity = _coerce_positive_int_quantity(result.quantity)
        if quantity is None:
            # Non-integer decimal (or otherwise non-whole) quantity is never truncated; the
            # caller routes this to manual review rather than silently changing the count.
            logger.warning(
                "code_scan.persist_reject_non_integer_quantity job_id=%s asset_id=%s quantity=%r",
                result.job_id,
                result.asset_id,
                result.quantity,
            )
            return PersistOutcome(
                persisted=False, skipped_reason=PersistSkipReason.MISSING_CODE_OR_QUANTITY
            )
        if quantity <= 0:
            return PersistOutcome(
                persisted=False, skipped_reason=PersistSkipReason.NON_POSITIVE_QUANTITY
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
        product_id = str(uuid.uuid4())
        evidence_id = str(uuid.uuid4())
        result_evidence_id = str(uuid.uuid4())
        coverage_id = str(uuid.uuid4())
        entity_uid = f"{job_id}_code_scan_{asset_id}"

        summary: dict = {
            "entity_uid": entity_uid,
            "entity_type": "PALLET",
            "internal_code": code,
            "source_image_id": asset_id,
            "source_asset_id": asset_id,
            "source_image_original_filename": snap.original_filename,
            "source_image_sequence": snap.position_order + 1,
            "creation_source": PositionCreationSource.AUTOMATIC.value,
            "qty_source": CODE_SCAN_QTY_SOURCE,
            "qty_parse_status": "valid_positive",
            "resolved_by": CODE_SCAN_PROVIDER,
        }

        storage_path = snap.storage_key or f"code_scan://{asset_id}"
        if live is not None:
            storage_path = live.storage_path or live.storage_key or storage_path

        position = Position(
            id=position_id,
            aisle_id=aisle_id,
            status=PositionStatus.DETECTED,
            confidence=1.0,
            needs_review=False,
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
        product = ProductRecord(
            id=product_id,
            position_id=position_id,
            sku=code,
            description=None,
            detected_quantity=quantity,
            corrected_quantity=None,
            confidence=1.0,
            created_at=now,
            updated_at=now,
            qty_source=CODE_SCAN_QTY_SOURCE,
            qty_inference_reason=None,
            raw_qty=quantity,
            qty_parse_status="valid_positive",
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
            provider=CODE_SCAN_PROVIDER,
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

        try:
            with self._uow_factory() as uow:
                if hasattr(uow, "bind_lifecycle_scope"):
                    uow.bind_lifecycle_scope(inventory_id=inventory_id, aisle_id=aisle_id)
                repos = uow.repositories
                uow.acquire_image_result_lock(job_id=job_id, source_asset_id=asset_id)

                existing = repos.manual_coverage_repo.get_by_job_and_asset(job_id, asset_id)
                if existing is not None:
                    # A coverage link created by an operator (created_by_user_id set) means a
                    # manual result already owns this image — code scan must NOT keep RESOLVED.
                    # A link with no user id is a prior code-scan position → idempotent reconcile.
                    if (existing.created_by_user_id or "").strip():
                        logger.info(
                            "code_scan.persist_skip_manual_result_exists job_id=%s asset_id=%s "
                            "position_id=%s",
                            job_id,
                            asset_id,
                            existing.position_id,
                        )
                        return PersistOutcome(
                            persisted=False,
                            reconciled=False,
                            position_id=existing.position_id,
                            skipped_reason=PersistSkipReason.MANUAL_RESULT_EXISTS,
                        )
                    logger.info(
                        "code_scan.persist_idempotent_existing_coverage job_id=%s asset_id=%s "
                        "position_id=%s",
                        job_id,
                        asset_id,
                        existing.position_id,
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
                    logger.info(
                        "code_scan.persist_idempotent_existing_result job_id=%s asset_id=%s",
                        job_id,
                        asset_id,
                    )
                    return PersistOutcome(
                        persisted=False,
                        reconciled=True,
                        skipped_reason=PersistSkipReason.ALREADY_PERSISTED,
                    )

                repos.position_repo.save(position)
                repos.product_record_repo.save(product)
                repos.evidence_repo.save(evidence)
                repos.manual_coverage_repo.save(coverage)
                repos.result_evidence_repo.save_many([result_evidence])
                uow.commit()
        except (ManualResultAlreadyExistsError, ImageAlreadyHasResultsError):
            # Lost a race with a concurrent writer for the same (job, asset). Best-effort
            # re-read the winner's coverage so we can reconcile (keep RESOLVED) rather than
            # blindly downgrade a legitimately-covered asset.
            existing = self._lookup_existing_coverage(job_id, asset_id)
            if existing is not None:
                logger.info(
                    "code_scan.persist_conflict_reconciled job_id=%s asset_id=%s position_id=%s",
                    job_id,
                    asset_id,
                    existing.position_id,
                )
                return PersistOutcome(
                    persisted=False,
                    reconciled=True,
                    position_id=existing.position_id,
                    active_result_id=existing.position_id,
                    skipped_reason=PersistSkipReason.CONCURRENCY_CONFLICT,
                )
            logger.info(
                "code_scan.persist_conflict_unreconciled job_id=%s asset_id=%s", job_id, asset_id
            )
            return PersistOutcome(
                persisted=False,
                reconciled=False,
                skipped_reason=PersistSkipReason.CONCURRENCY_CONFLICT,
            )

        logger.info(
            "code_scan.persisted_position job_id=%s asset_id=%s position_id=%s quantity=%s",
            job_id,
            asset_id,
            position_id,
            quantity,
        )
        return PersistOutcome(
            persisted=True, position_id=position_id, active_result_id=position_id
        )

    def _lookup_existing_coverage(self, job_id: str, asset_id: str):
        """Best-effort read of an existing coverage link outside the failed write transaction."""
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
