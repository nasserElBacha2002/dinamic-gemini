"""Coordinate image evidence with durable physical-position materialization."""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum

import pyodbc

from src.application.dto.access_principal import AccessPrincipal
from src.application.dto.position_materialization import (
    MaterializePositionCommand,
    SafeRawCodeEvidence,
)
from src.application.errors import ImageProcessingRepositoryUnavailableError
from src.application.ports.clock import Clock
from src.application.ports.image_position_label_detection_repository import (
    ImagePositionLabelDetectionRepository,
)
from src.application.services.job_image_result_resolution import JobPhotoCoverageImage
from src.application.services.position_materialization.service import (
    MaterializePositionService,
)
from src.application.services.position_recognition.normalization import (
    PositionCodeNormalizationError,
    normalize_position_code,
)
from src.domain.image_processing.contracts import (
    RAW_EVIDENCE_HASH_ALGORITHM,
    VISION_POSITION_DETECTOR_VERSION,
    ImageProcessingResult,
    VisionPositionEvidence,
)
from src.domain.position_label_detection.entities import (
    ImagePositionLabelDetection,
    PositionLabelDetectionStatus,
    PositionLabelSignatureStatus,
)
from src.domain.position_materialization.errors import PositionMaterializationError
from src.domain.position_recognition.entities import (
    CanonicalPositionRecognition,
    PositionRecognitionSource,
    PositionSignatureEvidence,
    PositionSignatureVerification,
)
from src.observability.metrics.instruments import (
    PositionMaterializationMetricComponent,
    PositionMaterializationMetricMode,
    PositionMaterializationMetricOutcome,
    PositionMaterializationMetricReason,
    PositionMaterializationMetricSource,
    record_position_materialization,
)

logger = logging.getLogger(__name__)
POSITION_MATERIALIZER_ACTOR = "system:position-materializer"
_VALID_STATUSES = frozenset(
    {
        PositionLabelDetectionStatus.VALID,
        PositionLabelDetectionStatus.SIGNATURE_VALIDATION_SKIPPED,
    }
)


class PreparationStatus(str, Enum):
    READY = "READY"
    INVALID_EVIDENCE = "INVALID_EVIDENCE"
    TECHNICAL_RETRY = "TECHNICAL_RETRY"
    NOT_WIRED = "NOT_WIRED"
    MATERIALIZATION_FAILED = "MATERIALIZATION_FAILED"


@dataclass(frozen=True)
class PrepareMaterialization:
    result: ImageProcessingResult
    inventory_id: str
    aisle_id: str
    snapshot: JobPhotoCoverageImage


@dataclass(frozen=True)
class MaterializationAssociation:
    request_id: str
    location_id: str
    detection_id: str


@dataclass(frozen=True)
class PreparedMaterialization:
    status: PreparationStatus
    source: PositionRecognitionSource | None = None
    detections: tuple[ImagePositionLabelDetection, ...] = ()
    associations: tuple[MaterializationAssociation, ...] = ()
    idempotent_replay: bool = False
    technical_cause: Exception | None = field(default=None, compare=False, repr=False)

    @property
    def ready(self) -> bool:
        return self.status is PreparationStatus.READY

    @property
    def request_ids(self) -> tuple[str, ...]:
        return tuple(item.request_id for item in self.associations)


@dataclass(frozen=True)
class CompleteMaterialization:
    prepared: PreparedMaterialization
    success: bool
    error_code: str | None = None


@dataclass(frozen=True)
class RecoverMaterialization:
    result: ImageProcessingResult
    job_id: str
    asset_id: str
    inventory_id: str
    aisle_id: str


class PositionMaterializationCoordinator:
    """One materialization path for CODE_SCAN and validated Vision evidence."""

    def __init__(
        self,
        *,
        clock: Clock,
        detection_repo: ImagePositionLabelDetectionRepository | None,
        materializer: MaterializePositionService | None,
        enabled: bool,
    ) -> None:
        self._clock = clock
        self._detection_repo = detection_repo
        self._materializer = materializer
        self._enabled = enabled

    def prepare(self, command: PrepareMaterialization) -> PreparedMaterialization:
        result = command.result
        source = self._select_source(result)
        if not self._enabled:
            try:
                detections = self._list_valid(result.job_id, result.asset_id)
            except _PositionDetectionRepositoryRetryableError as exc:
                return self._technical_retry(source, exc.cause)
            return PreparedMaterialization(
                status=PreparationStatus.READY,
                source=source,
                detections=tuple(detections),
            )
        if self._detection_repo is None or self._materializer is None:
            self._record_outcome(
                source,
                PositionMaterializationMetricOutcome.TECHNICAL_RETRY,
                PositionMaterializationMetricReason.TECHNICAL_FAILURE,
            )
            return PreparedMaterialization(status=PreparationStatus.NOT_WIRED, source=source)

        typed_by_detection: dict[str, VisionPositionEvidence] = {}
        if source is PositionRecognitionSource.VISION:
            evidence = result.vision_position_evidence
            if not evidence:
                # Legacy dictionaries are projections only and fail closed.
                self._record_outcome(
                    source,
                    PositionMaterializationMetricOutcome.VALIDATION_REJECTED,
                    PositionMaterializationMetricReason.INVALID_REQUEST,
                )
                return PreparedMaterialization(
                    status=PreparationStatus.INVALID_EVIDENCE,
                    source=source,
                )
            try:
                detections, typed_by_detection = self._persist_vision_detections(command, evidence)
            except _PositionDetectionRepositoryRetryableError as exc:
                return self._technical_retry(source, exc.cause)
        else:
            try:
                detections = self._list_valid(
                    result.job_id,
                    result.asset_id,
                    source=PositionRecognitionSource.CODE_SCAN,
                )
            except _PositionDetectionRepositoryRetryableError as exc:
                return self._technical_retry(source, exc.cause)
        if not detections:
            self._record_outcome(
                source,
                PositionMaterializationMetricOutcome.VALIDATION_REJECTED,
                PositionMaterializationMetricReason.INVALID_REQUEST,
            )
            return PreparedMaterialization(
                status=PreparationStatus.INVALID_EVIDENCE,
                source=source,
            )

        associations: list[MaterializationAssociation] = []
        replayed = False
        for detection in detections:
            materialize = self._command_for_detection(
                detection=detection,
                source=source,
                job_id=result.job_id,
                asset_id=result.asset_id,
                inventory_id=command.inventory_id,
                aisle_id=command.aisle_id,
                vision_evidence=typed_by_detection.get(detection.id),
            )
            if materialize is None:
                self.complete(
                    CompleteMaterialization(
                        prepared=PreparedMaterialization(
                            status=PreparationStatus.READY,
                            source=source,
                            detections=tuple(detections),
                            associations=tuple(associations),
                        ),
                        success=False,
                        error_code="IMAGE_MATERIALIZATION_PARTIAL_FAILURE",
                    )
                )
                return PreparedMaterialization(
                    status=PreparationStatus.MATERIALIZATION_FAILED,
                    source=source,
                    detections=tuple(detections),
                )
            result_out = self._materializer.execute(materialize)
            if not result_out.accepted or not result_out.location_id or not result_out.request_id:
                self.complete(
                    CompleteMaterialization(
                        prepared=PreparedMaterialization(
                            status=PreparationStatus.READY,
                            source=source,
                            detections=tuple(detections),
                            associations=tuple(associations),
                        ),
                        success=False,
                        error_code="IMAGE_MATERIALIZATION_PARTIAL_FAILURE",
                    )
                )
                return PreparedMaterialization(
                    status=PreparationStatus.MATERIALIZATION_FAILED,
                    source=source,
                    detections=tuple(detections),
                )
            associations.append(
                MaterializationAssociation(
                    request_id=result_out.request_id,
                    location_id=result_out.location_id,
                    detection_id=detection.id,
                )
            )
            replayed = replayed or result_out.idempotent_replay
        return PreparedMaterialization(
            status=PreparationStatus.READY,
            source=source,
            detections=tuple(detections),
            associations=tuple(associations),
            idempotent_replay=replayed,
        )

    def _technical_retry(
        self,
        source: PositionRecognitionSource,
        cause: Exception,
    ) -> PreparedMaterialization:
        logger.warning(
            "position_detection_repository_retryable source=%s error_type=%s",
            source.value,
            type(cause).__name__,
        )
        self._record_outcome(
            source,
            PositionMaterializationMetricOutcome.TECHNICAL_RETRY,
            PositionMaterializationMetricReason.TECHNICAL_FAILURE,
        )
        return PreparedMaterialization(
            status=PreparationStatus.TECHNICAL_RETRY,
            source=source,
            technical_cause=cause,
        )

    def complete(self, command: CompleteMaterialization) -> None:
        if self._materializer is None:
            return
        if not command.success and command.prepared.source is not None:
            self._record_outcome(
                command.prepared.source,
                PositionMaterializationMetricOutcome.REQUIRES_REVIEW,
                PositionMaterializationMetricReason.DOWNSTREAM_REQUIRES_REVIEW,
            )
        for request_id in dict.fromkeys(command.prepared.request_ids):
            self._materializer.complete_association(
                request_id,
                success=command.success,
                error_code=command.error_code,
                now=self._clock.now(),
            )

    def recover(self, command: RecoverMaterialization) -> bool | None:
        if self._materializer is None:
            return None
        source = self._select_source(command.result)
        detections = self._list_valid(command.job_id, command.asset_id, source=source)
        vision_by_code = {
            item.recognition.normalized_code: item
            for item in command.result.vision_position_evidence
        }
        associations: list[MaterializationAssociation] = []
        replayed = False
        for detection in detections:
            materialize = self._command_for_detection(
                detection=detection,
                source=source,
                job_id=command.job_id,
                asset_id=command.asset_id,
                inventory_id=command.inventory_id,
                aisle_id=command.aisle_id,
                vision_evidence=vision_by_code.get((detection.public_identifier or "").strip()),
            )
            if materialize is None:
                return None
            try:
                existing = self._materializer.lookup_replay(materialize)
            except (PositionMaterializationError, TypeError, ValueError):
                return None
            if existing is None:
                continue
            if not existing.request_id or not existing.location_id:
                return None
            associations.append(
                MaterializationAssociation(
                    request_id=existing.request_id,
                    location_id=existing.location_id,
                    detection_id=detection.id,
                )
            )
            replayed = replayed or existing.idempotent_replay
        self.complete(
            CompleteMaterialization(
                prepared=PreparedMaterialization(
                    status=PreparationStatus.READY,
                    source=source,
                    detections=tuple(detections),
                    associations=tuple(associations),
                ),
                success=True,
            )
        )
        if associations:
            self._record_outcome(
                source,
                PositionMaterializationMetricOutcome.ASSOCIATION_RECOVERED,
                PositionMaterializationMetricReason.NONE,
            )
        return replayed

    @staticmethod
    def _record_outcome(
        source: PositionRecognitionSource,
        outcome: PositionMaterializationMetricOutcome,
        reason: PositionMaterializationMetricReason,
    ) -> None:
        record_position_materialization(
            component=PositionMaterializationMetricComponent.COORDINATOR,
            source=PositionMaterializationMetricSource(source.value),
            mode=PositionMaterializationMetricMode.DINAMIC,
            outcome=outcome,
            reason_code=reason,
        )

    @staticmethod
    def _select_source(result: ImageProcessingResult) -> PositionRecognitionSource:
        if result.vision_position_evidence:
            return PositionRecognitionSource.VISION
        legacy = result.evidence if isinstance(result.evidence, dict) else {}
        metadata = legacy.get("position_label_detection")
        if (
            isinstance(metadata, dict)
            and str(metadata.get("recognition_source", "")).upper() == "VISION"
        ):
            return PositionRecognitionSource.VISION
        return PositionRecognitionSource.CODE_SCAN

    def _list_valid(
        self,
        job_id: str,
        asset_id: str,
        *,
        source: PositionRecognitionSource | None = None,
    ) -> list[ImagePositionLabelDetection]:
        if self._detection_repo is None:
            return []
        try:
            rows = self._detection_repo.list_by_asset(job_id, asset_id)
        except (
            ImageProcessingRepositoryUnavailableError,
            TimeoutError,
            OSError,
            pyodbc.InterfaceError,
            pyodbc.OperationalError,
        ) as exc:
            raise _PositionDetectionRepositoryRetryableError(exc) from exc
        valid = [row for row in rows if row.detection_status in _VALID_STATUSES]
        if source is PositionRecognitionSource.VISION:
            return [
                row for row in valid if row.detector_version == VISION_POSITION_DETECTOR_VERSION
            ]
        if source is PositionRecognitionSource.CODE_SCAN:
            return [
                row for row in valid if row.detector_version != VISION_POSITION_DETECTOR_VERSION
            ]
        return valid

    def _persist_vision_detections(
        self,
        command: PrepareMaterialization,
        evidence: tuple[VisionPositionEvidence, ...],
    ) -> tuple[list[ImagePositionLabelDetection], dict[str, VisionPositionEvidence]]:
        assert self._detection_repo is not None
        rows: list[ImagePositionLabelDetection] = []
        by_id: dict[str, VisionPositionEvidence] = {}
        now = self._clock.now()
        for item in evidence:
            recognition = item.recognition
            detection_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    "dinamic:vision-position:"
                    f"{command.result.job_id}:{command.result.asset_id}:"
                    f"{recognition.normalized_code}",
                )
            )
            row = ImagePositionLabelDetection(
                id=detection_id,
                client_id=item.client_id,
                inventory_id=command.inventory_id,
                job_id=command.result.job_id,
                source_asset_id=command.result.asset_id,
                client_image_id=None,
                ordered_capture_session_id=None,
                sequence_number=command.snapshot.position_order + 1,
                position_label_id=None,
                public_identifier=recognition.normalized_code,
                position_name_snapshot=recognition.normalized_code,
                payload_version=None,
                signature_status=PositionLabelSignatureStatus.SKIPPED,
                detection_status=PositionLabelDetectionStatus.VALID,
                confidence=None,
                bounding_box_json=None,
                rotation_degrees=None,
                raw_payload_hash=item.raw_evidence.payload_hash,
                detector_name=item.detector_name,
                detector_version=item.detector_version,
                created_at=now,
                updated_at=now,
                metadata_json={
                    "recognition_source": PositionRecognitionSource.VISION.value,
                    "raw_payload_length": item.raw_evidence.utf8_length,
                    "raw_hash_algorithm": item.raw_evidence.hash_algorithm,
                    "client_supplier_id": recognition.client_supplier_id,
                    "profile_id": recognition.profile_id,
                    "profile_version": recognition.profile_version,
                    "pallet": recognition.pallet,
                    "side": recognition.side,
                    "level": recognition.level,
                    "marker_index": recognition.marker_index,
                    "marker_total": recognition.marker_total,
                },
            )
            rows.append(row)
            by_id[detection_id] = item
        try:
            persisted = list(
                self._detection_repo.replace_asset_detections_atomically(
                    job_id=command.result.job_id,
                    source_asset_id=command.result.asset_id,
                    detector_version=VISION_POSITION_DETECTOR_VERSION,
                    detections=rows,
                )
            )
        except (
            ImageProcessingRepositoryUnavailableError,
            TimeoutError,
            OSError,
            pyodbc.InterfaceError,
            pyodbc.OperationalError,
        ) as exc:
            raise _PositionDetectionRepositoryRetryableError(exc) from exc
        return persisted, by_id

    @staticmethod
    def _command_for_detection(
        *,
        detection: ImagePositionLabelDetection,
        source: PositionRecognitionSource,
        job_id: str,
        asset_id: str,
        inventory_id: str,
        aisle_id: str,
        vision_evidence: VisionPositionEvidence | None,
    ) -> MaterializePositionCommand | None:
        display_code = (detection.public_identifier or "").strip()
        if not display_code:
            return None
        metadata = detection.metadata_json or {}
        if source is PositionRecognitionSource.VISION:
            if vision_evidence is None:
                return None
            recognition = vision_evidence.recognition
            safe_raw = None
        else:
            try:
                normalized_code = normalize_position_code(display_code).normalized_code
            except PositionCodeNormalizationError:
                return None
            signature = PositionSignatureEvidence(
                present=detection.signature_status is PositionLabelSignatureStatus.VALID,
                verification=(
                    PositionSignatureVerification.VERIFIED
                    if detection.signature_status is PositionLabelSignatureStatus.VALID
                    else PositionSignatureVerification.UNVERIFIED
                ),
            )
            recognition = CanonicalPositionRecognition(
                raw_code=None,
                normalized_code=normalized_code,
                source=source,
                pallet=_text(metadata.get("pallet")),
                side=_text(metadata.get("side")),
                level=_integer(metadata.get("level"), minimum=0),
                marker_index=_integer(metadata.get("marker_index"), minimum=1),
                marker_total=_integer(metadata.get("marker_total"), minimum=1),
                profile_id=_text(
                    metadata.get("profile_id") or metadata.get("extraction_profile_id")
                ),
                profile_version=_integer(
                    metadata.get("profile_version") or metadata.get("extraction_profile_version"),
                    minimum=1,
                ),
                client_supplier_id=_text(metadata.get("client_supplier_id")),
                signature=signature,
                evidence={"detection_id": detection.id},
            )
            if not detection.raw_payload_hash:
                return None
            safe_raw = SafeRawCodeEvidence(
                payload_hash=detection.raw_payload_hash,
                display_code=display_code,
                utf8_length=_integer(metadata.get("raw_payload_length"), minimum=0),
                hash_algorithm=_text(metadata.get("raw_hash_algorithm"))
                or RAW_EVIDENCE_HASH_ALGORITHM,
            )
        identity = "\0".join((job_id, asset_id, source.value, recognition.normalized_code)).encode(
            "utf-8"
        )
        return MaterializePositionCommand(
            recognition=recognition,
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            principal=AccessPrincipal(
                actor_id=POSITION_MATERIALIZER_ACTOR,
                client_id=detection.client_id,
                roles=frozenset({"system"}),
                is_platform=False,
            ),
            idempotency_key=(
                f"position:{source.value.lower()}:{hashlib.sha256(identity).hexdigest()}"
            ),
            capture_id=asset_id,
            safe_raw_evidence=safe_raw,
        )


def _text(value: object) -> str | None:
    return str(value).strip() if value is not None and str(value).strip() else None


def _integer(value: object, *, minimum: int) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (str, int, float)):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= minimum else None


class _PositionDetectionRepositoryRetryableError(Exception):
    def __init__(self, cause: Exception) -> None:
        super().__init__(type(cause).__name__)
        self.cause = cause
