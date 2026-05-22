"""Match latest aisle code scan detections read-only against existing positions."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from src.application.ports.clock import Clock
from src.application.ports.code_scan_repository import CodeScanRepository
from src.application.ports.repositories import (
    JOB_ID_FILTER_UNSET,
    AisleRepository,
    JobRepository,
    PositionRepository,
    ProductRecordRepository,
)
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.application.services.code_scan_matching_metadata import (
    matching_metadata_completed,
    matching_metadata_skipped,
)
from src.application.services.code_scan_result_matcher import (
    build_position_lookup,
    match_detection_value,
)
from src.application.services.result_context_resolver import ResultContextResolver
from src.domain.code_scans.entities import CodeScanDetection, CodeScanDetectionStatus
from src.domain.code_scans.matching import CodeScanMatchStatus, validate_detection_match_fields

logger = logging.getLogger(__name__)

MATCHING_WARNING_MESSAGE = "No se pudieron evaluar coincidencias automáticamente."
MISSING_RESULT_CONTEXT_WARNING = (
    "No se evaluaron coincidencias porque no se pudo determinar el contexto de resultados."
)


@dataclass(frozen=True)
class MatchAisleCodeScanDetectionsCommand:
    inventory_id: str
    aisle_id: str
    run_id: str | None = None
    job_id: str | None = None


@dataclass(frozen=True)
class MatchAisleCodeScanDetectionsResult:
    matched_count: int
    no_match_count: int
    multiple_candidates_count: int
    not_evaluated_count: int
    matching_metadata: dict[str, Any]
    warning_message: str | None = None


class MatchAisleCodeScanDetectionsUseCase:
    def __init__(
        self,
        aisle_repo: AisleRepository,
        job_repo: JobRepository,
        position_repo: PositionRepository,
        product_record_repo: ProductRecordRepository,
        code_scan_repo: CodeScanRepository,
        clock: Clock,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._context_resolver = ResultContextResolver(job_repo)
        self._position_repo = position_repo
        self._product_record_repo = product_record_repo
        self._code_scan_repo = code_scan_repo
        self._clock = clock

    def execute(
        self, command: MatchAisleCodeScanDetectionsCommand
    ) -> MatchAisleCodeScanDetectionsResult:
        aisle = require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            detail_style="strict",
        )
        run_id = command.run_id
        if run_id is None:
            latest = self._code_scan_repo.get_latest_run_by_aisle(
                inventory_id=command.inventory_id,
                aisle_id=command.aisle_id,
            )
            if latest is None:
                return MatchAisleCodeScanDetectionsResult(
                    0, 0, 0, 0, matching_metadata_skipped(reason="no_run")
                )
            run_id = latest.id

        detections = list(self._code_scan_repo.list_detections_for_run(run_id))
        if not detections:
            return MatchAisleCodeScanDetectionsResult(
                0, 0, 0, 0, matching_metadata_skipped(reason="no_detections")
            )

        explicit_job_id = (command.job_id or "").strip() or None
        if self._should_skip_matching_for_missing_context(aisle, explicit_job_id):
            return self._mark_skipped_missing_context(detections)

        resolved = self._context_resolver.resolve(aisle=aisle, explicit_job_id=explicit_job_id)
        job_filter = resolved.job_id_for_slice
        scope = "job" if resolved.source in ("explicit", "operational") else "legacy"

        positions = list(
            self._position_repo.list_by_aisle(
                command.aisle_id,
                page=1,
                page_size=10_000,
                job_id=job_filter,
            )
        )
        position_ids = [p.id for p in positions]
        products = (
            list(self._product_record_repo.list_by_position_ids(position_ids))
            if position_ids
            else []
        )
        products_by_position: dict[str, list] = {}
        for product in products:
            products_by_position.setdefault(product.position_id, []).append(product)

        lookup = build_position_lookup(positions, products_by_position)
        now = self._clock.now()
        matched = no_match = multiple = not_evaluated = 0

        for detection in detections:
            if detection.detection_status != CodeScanDetectionStatus.DETECTED:
                detection.matched_position_id = None
                detection.match_status = CodeScanMatchStatus.NOT_EVALUATED.value
                detection.match_type = None
                detection.match_confidence = None
                detection.match_metadata_json = None
                detection.matched_at = now
                validate_detection_match_fields(
                    match_status=detection.match_status,
                    match_type=detection.match_type,
                )
                not_evaluated += 1
                continue

            outcome = match_detection_value(
                normalized_code_value=detection.normalized_code_value,
                code_value=detection.code_value,
                lookup=lookup,
            )
            detection.matched_position_id = outcome.matched_position_id
            detection.match_status = outcome.match_status.value
            detection.match_type = outcome.match_type
            detection.match_confidence = outcome.match_confidence
            detection.match_metadata_json = outcome.match_metadata_json
            detection.matched_at = now
            validate_detection_match_fields(
                match_status=detection.match_status,
                match_type=detection.match_type,
            )

            if outcome.match_status == CodeScanMatchStatus.MATCHED:
                matched += 1
            elif outcome.match_status == CodeScanMatchStatus.NO_MATCH:
                no_match += 1
            elif outcome.match_status == CodeScanMatchStatus.MULTIPLE_CANDIDATES:
                multiple += 1
            else:
                not_evaluated += 1

        self._code_scan_repo.update_detection_matches(detections)
        return MatchAisleCodeScanDetectionsResult(
            matched_count=matched,
            no_match_count=no_match,
            multiple_candidates_count=multiple,
            not_evaluated_count=not_evaluated,
            matching_metadata=matching_metadata_completed(
                scope=scope,
                source=resolved.source,
                job_id=resolved.job_id_for_slice,
                matched_count=matched,
                no_match_count=no_match,
                multiple_candidates_count=multiple,
                not_evaluated_count=not_evaluated,
            ),
        )

    def _should_skip_matching_for_missing_context(self, aisle, explicit_job_id: str | None) -> bool:
        if explicit_job_id:
            return False
        if aisle.operational_job_id:
            return False
        legacy_rows = self._position_repo.list_by_aisle(
            aisle.id, page=1, page_size=1, job_id=None
        )
        if legacy_rows:
            return False
        for row in self._position_repo.list_by_aisle(
            aisle.id, page=1, page_size=50, job_id=JOB_ID_FILTER_UNSET
        ):
            if row.job_id:
                return True
        return False

    def _mark_skipped_missing_context(
        self, detections: list[CodeScanDetection]
    ) -> MatchAisleCodeScanDetectionsResult:
        now = self._clock.now()
        for detection in detections:
            detection.matched_position_id = None
            detection.match_status = CodeScanMatchStatus.NOT_EVALUATED.value
            detection.match_type = None
            detection.match_confidence = None
            detection.match_metadata_json = None
            detection.matched_at = now
            validate_detection_match_fields(
                match_status=detection.match_status,
                match_type=detection.match_type,
            )
        self._code_scan_repo.update_detection_matches(detections)
        return MatchAisleCodeScanDetectionsResult(
            matched_count=0,
            no_match_count=0,
            multiple_candidates_count=0,
            not_evaluated_count=len(detections),
            matching_metadata=matching_metadata_skipped(reason="missing_result_context"),
            warning_message=MISSING_RESULT_CONTEXT_WARNING,
        )
