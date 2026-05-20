"""Match latest aisle code scan detections read-only against existing positions."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.application.ports.clock import Clock
from src.application.ports.code_scan_repository import CodeScanRepository
from src.application.ports.repositories import (
    JOB_ID_FILTER_UNSET,
    AisleRepository,
    PositionRepository,
    ProductRecordRepository,
)
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.application.services.code_scan_result_matcher import (
    build_position_lookup,
    match_detection_value,
)
from src.domain.code_scans.entities import CodeScanDetectionStatus
from src.domain.code_scans.matching import CodeScanMatchStatus

logger = logging.getLogger(__name__)

MATCHING_WARNING_MESSAGE = "No se pudieron evaluar coincidencias automáticamente."


@dataclass(frozen=True)
class MatchAisleCodeScanDetectionsCommand:
    inventory_id: str
    aisle_id: str
    run_id: str | None = None


@dataclass(frozen=True)
class MatchAisleCodeScanDetectionsResult:
    matched_count: int
    no_match_count: int
    multiple_candidates_count: int
    not_evaluated_count: int


class MatchAisleCodeScanDetectionsUseCase:
    def __init__(
        self,
        aisle_repo: AisleRepository,
        position_repo: PositionRepository,
        product_record_repo: ProductRecordRepository,
        code_scan_repo: CodeScanRepository,
        clock: Clock,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._position_repo = position_repo
        self._product_record_repo = product_record_repo
        self._code_scan_repo = code_scan_repo
        self._clock = clock

    def execute(
        self, command: MatchAisleCodeScanDetectionsCommand
    ) -> MatchAisleCodeScanDetectionsResult:
        require_aisle_scoped_to_inventory(
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
                return MatchAisleCodeScanDetectionsResult(0, 0, 0, 0)
            run_id = latest.id

        detections = list(self._code_scan_repo.list_detections_for_run(run_id))
        if not detections:
            return MatchAisleCodeScanDetectionsResult(0, 0, 0, 0)

        positions = list(
            self._position_repo.list_by_aisle(
                command.aisle_id,
                page=1,
                page_size=10_000,
                job_id=JOB_ID_FILTER_UNSET,
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
                detection.match_status = CodeScanMatchStatus.NOT_EVALUATED.value
                detection.match_type = None
                detection.match_confidence = None
                detection.matched_position_id = None
                detection.match_metadata_json = None
                detection.matched_at = None
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
        )
