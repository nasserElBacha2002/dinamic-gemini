"""Idempotent image position-label detection from already-decoded codes (Phase 3)."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from src.application.ports.clock import Clock
from src.application.ports.image_position_label_detection_repository import (
    ImagePositionLabelDetectionRepository,
)
from src.application.services.position_label_detection.code_classifier import CodeClassifier
from src.application.services.position_label_detection.payload_parser import (
    ParsedPositionLabelPayload,
    PositionLabelPayloadParser,
)
from src.application.services.position_label_detection.resolver import PositionLabelResolver
from src.application.services.position_label_detection.validation_service import (
    PositionLabelValidationService,
)
from src.domain.client_position_label.entities import ClientPositionLabelSignatureStatus
from src.domain.position_label_detection.entities import (
    DETECTOR_NAME,
    DETECTOR_VERSION,
    DetectedCode,
    ImageCodeKind,
    ImagePositionLabelDetection,
    PositionLabelDetectionStatus,
    PositionLabelSignatureStatus,
)

logger = logging.getLogger(__name__)


def _payload_hierarchy_meta(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Safe subset of DINAMIC_POSITION hierarchy fields for detection metadata (no HMAC)."""
    if not isinstance(payload, dict):
        return {}
    out: dict[str, Any] = {}
    for key in ("pallet", "side", "level", "marker_index", "marker_total"):
        if key in payload:
            out[key] = payload[key]
    return out


@dataclass(frozen=True)
class ImagePositionDetectionCommand:
    client_id: str
    inventory_id: str
    job_id: str
    source_asset_id: str
    codes: Sequence[DetectedCode]
    client_image_id: str | None = None
    ordered_capture_session_id: str | None = None
    sequence_number: int | None = None
    correlation_id: str | None = None


@dataclass(frozen=True)
class ImagePositionDetectionResult:
    detections: tuple[ImagePositionLabelDetection, ...]
    item_codes: tuple[DetectedCode, ...]
    position_candidate_indexes: tuple[int, ...]
    ambiguous: bool
    disabled: bool = False
    context_invalid: bool = False


class ImagePositionDetectionUseCase:
    """Classify decoded symbols and persist position-label detections.

    Does not decode images. Callers must pass codes from a shared CODE_SCAN pass.

    ``POSITION_LABEL_MAX_CODES_PER_IMAGE`` limits how many POSITION candidates are
    validated/persisted. Classification still runs on all codes so item candidates
    are never dropped from the consolidator path.
    """

    def __init__(
        self,
        *,
        classifier: CodeClassifier,
        parser: PositionLabelPayloadParser,
        validator: PositionLabelValidationService,
        resolver: PositionLabelResolver,
        repo: ImagePositionLabelDetectionRepository,
        clock: Clock,
        detection_enabled: bool,
        persistence_enabled: bool,
        max_codes_per_image: int,
        persist_no_label: bool = False,
        detector_name: str = DETECTOR_NAME,
        detector_version: str = DETECTOR_VERSION,
    ) -> None:
        self._classifier = classifier
        self._parser = parser
        self._validator = validator
        self._resolver = resolver
        self._repo = repo
        self._clock = clock
        self._detection_enabled = bool(detection_enabled)
        self._persistence_enabled = bool(persistence_enabled)
        self._max_codes = max(1, int(max_codes_per_image))
        self._persist_no_label = bool(persist_no_label)
        self._detector_name = detector_name
        self._detector_version = detector_version

    def execute(self, command: ImagePositionDetectionCommand) -> ImagePositionDetectionResult:
        if not self._detection_enabled:
            logger.info(
                "position_label_detection_completed client_id=%s inventory_id=%s job_id=%s "
                "asset_id=%s detection_status=%s detector_version=%s correlation_id=%s",
                command.client_id,
                command.inventory_id,
                command.job_id,
                command.source_asset_id,
                PositionLabelDetectionStatus.FEATURE_DISABLED.value,
                self._detector_version,
                command.correlation_id,
            )
            return ImagePositionDetectionResult(
                detections=(),
                item_codes=tuple(command.codes),
                position_candidate_indexes=(),
                ambiguous=False,
                disabled=True,
            )

        client_id = (command.client_id or "").strip()
        if not client_id:
            logger.info(
                "position_label_detection_completed client_id=%s inventory_id=%s job_id=%s "
                "asset_id=%s detection_status=%s detector_version=%s correlation_id=%s",
                "",
                command.inventory_id,
                command.job_id,
                command.source_asset_id,
                PositionLabelDetectionStatus.DETECTION_CONTEXT_INVALID.value,
                self._detector_version,
                command.correlation_id,
            )
            return ImagePositionDetectionResult(
                detections=(),
                item_codes=tuple(command.codes),
                position_candidate_indexes=(),
                ambiguous=False,
                context_invalid=True,
            )

        logger.info(
            "position_label_detection_started client_id=%s inventory_id=%s job_id=%s "
            "asset_id=%s client_image_id=%s sequence_number=%s detector_version=%s "
            "correlation_id=%s",
            client_id,
            command.inventory_id,
            command.job_id,
            command.source_asset_id,
            command.client_image_id,
            command.sequence_number,
            self._detector_version,
            command.correlation_id,
        )

        # Classify every decoded symbol — never drop item candidates via max_codes.
        item_codes: list[DetectedCode] = []
        position_codes: list[DetectedCode] = []
        position_indexes: list[int] = []
        for index, code in enumerate(command.codes):
            indexed = DetectedCode(
                symbology=code.symbology,
                raw_value=code.raw_value,
                normalized_value=code.normalized_value,
                bounding_box=code.bounding_box,
                confidence=code.confidence,
                rotation_degrees=code.rotation_degrees,
                candidate_index=code.candidate_index if code.candidate_index is not None else index,
            )
            kind = self._classifier.classify(indexed)
            if kind is ImageCodeKind.POSITION:
                position_codes.append(indexed)
                position_indexes.append(index)
                logger.info(
                    "position_label_code_detected client_id=%s job_id=%s asset_id=%s "
                    "symbology=%s candidate_index=%s detector_version=%s correlation_id=%s",
                    client_id,
                    command.job_id,
                    command.source_asset_id,
                    indexed.symbology,
                    indexed.candidate_index,
                    self._detector_version,
                    command.correlation_id,
                )
            elif kind is ImageCodeKind.ITEM:
                item_codes.append(indexed)

        now = self._clock.now()
        if isinstance(now, datetime) and now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        # Work on a command snapshot with required client_id.
        scoped = ImagePositionDetectionCommand(
            client_id=client_id,
            inventory_id=command.inventory_id,
            job_id=command.job_id,
            source_asset_id=command.source_asset_id,
            codes=command.codes,
            client_image_id=command.client_image_id,
            ordered_capture_session_id=command.ordered_capture_session_id,
            sequence_number=command.sequence_number,
            correlation_id=command.correlation_id,
        )

        if not position_codes:
            detections: list[ImagePositionLabelDetection] = []
            if self._persist_no_label:
                empty = self._build_row(
                    scoped,
                    now=now,
                    status=PositionLabelDetectionStatus.NO_LABEL,
                    signature_status=PositionLabelSignatureStatus.MISSING,
                    payload_hash=None,
                )
                detections = list(self._persist_many([empty]))
            logger.info(
                "position_label_detection_completed client_id=%s job_id=%s asset_id=%s "
                "detection_status=%s detector_version=%s correlation_id=%s",
                client_id,
                command.job_id,
                command.source_asset_id,
                PositionLabelDetectionStatus.NO_LABEL.value,
                self._detector_version,
                command.correlation_id,
            )
            return ImagePositionDetectionResult(
                detections=tuple(detections),
                item_codes=tuple(item_codes),
                position_candidate_indexes=tuple(position_indexes),
                ambiguous=False,
            )

        # Defensive cap applies only to POSITION evaluation, never to item_codes.
        to_evaluate = position_codes[: self._max_codes]
        candidate_rows: list[ImagePositionLabelDetection] = []
        for code in to_evaluate:
            candidate_rows.append(self._evaluate_position_code(scoped, code, now=now))

        valid_label_ids = {
            (r.public_identifier or "").strip()
            for r in candidate_rows
            if r.detection_status is PositionLabelDetectionStatus.VALID
            and (r.public_identifier or "").strip()
        }

        ambiguous = False
        if len(valid_label_ids) > 1:
            ambiguous = True
            logger.info(
                "position_label_ambiguous client_id=%s job_id=%s asset_id=%s "
                "label_count=%s detector_version=%s correlation_id=%s",
                client_id,
                command.job_id,
                command.source_asset_id,
                len(valid_label_ids),
                self._detector_version,
                command.correlation_id,
            )
            kept = [
                r
                for r in candidate_rows
                if r.detection_status is not PositionLabelDetectionStatus.VALID
            ]
            boxes = [r.bounding_box_json for r in candidate_rows if r.bounding_box_json]
            kept.append(
                self._build_row(
                    scoped,
                    now=now,
                    status=PositionLabelDetectionStatus.AMBIGUOUS_POSITION_DETECTION,
                    signature_status=PositionLabelSignatureStatus.VALID,
                    payload_hash=None,
                    bounding_box_json={"candidates": boxes} if boxes else None,
                    metadata={"distinct_label_ids": sorted(valid_label_ids)},
                )
            )
            candidate_rows = kept
        elif len(valid_label_ids) == 1:
            label_id = next(iter(valid_label_ids))
            valids = [
                r
                for r in candidate_rows
                if r.detection_status is PositionLabelDetectionStatus.VALID
                and (r.public_identifier or "").strip() == label_id
            ]
            others = [
                r
                for r in candidate_rows
                if not (
                    r.detection_status is PositionLabelDetectionStatus.VALID
                    and (r.public_identifier or "").strip() == label_id
                )
            ]
            primary = valids[0]
            if len(valids) > 1:
                boxes = [v.bounding_box_json for v in valids if v.bounding_box_json]
                primary.bounding_box_json = (
                    {"instances": boxes} if boxes else primary.bounding_box_json
                )
                primary.metadata_json = {
                    **(primary.metadata_json or {}),
                    "duplicate_code_count": len(valids),
                    "detection_note": PositionLabelDetectionStatus.DUPLICATE_POSITION_CODES.value,
                }
            candidate_rows = [primary, *others]

        if len(position_codes) > self._max_codes:
            for row in candidate_rows:
                row.metadata_json = {
                    **(row.metadata_json or {}),
                    "position_codes_truncated": True,
                    "position_codes_total": len(position_codes),
                    "position_codes_evaluated": len(to_evaluate),
                }

        saved = self._persist_many(candidate_rows)
        status_summary = ",".join(sorted({d.detection_status.value for d in saved})) or "NONE"
        logger.info(
            "position_label_detection_completed client_id=%s job_id=%s asset_id=%s "
            "detection_status=%s detector_version=%s correlation_id=%s",
            client_id,
            command.job_id,
            command.source_asset_id,
            status_summary,
            self._detector_version,
            command.correlation_id,
        )
        return ImagePositionDetectionResult(
            detections=tuple(saved),
            item_codes=tuple(item_codes),
            position_candidate_indexes=tuple(position_indexes),
            ambiguous=ambiguous,
        )

    def _evaluate_position_code(
        self,
        command: ImagePositionDetectionCommand,
        code: DetectedCode,
        *,
        now: datetime,
    ) -> ImagePositionLabelDetection:
        parsed = self._parser.parse(code.raw_value)
        if parsed.status is PositionLabelDetectionStatus.MISSING_SIGNATURE and parsed.label_id:
            # Accept catalog UNSIGNED labels (v1 or v2) that were issued while HMAC was
            # unconfigured. Signed labels missing a QR signature stay MISSING_SIGNATURE.
            unsigned = self._try_resolve_unsigned_label(
                command=command,
                code=code,
                parsed=parsed,
                now=now,
            )
            if unsigned is not None:
                return unsigned
        if parsed.status is not PositionLabelDetectionStatus.VALID:
            logger.info(
                "position_label_validation_failed client_id=%s job_id=%s asset_id=%s "
                "label_id=%s detection_status=%s detector_version=%s correlation_id=%s",
                command.client_id,
                command.job_id,
                command.source_asset_id,
                parsed.label_id,
                parsed.status.value,
                self._detector_version,
                command.correlation_id,
            )
            # MISSING only when the payload truly lacks a signature field.
            if parsed.status is PositionLabelDetectionStatus.MISSING_SIGNATURE or not parsed.signature:
                signature_status = PositionLabelSignatureStatus.MISSING
            else:
                signature_status = PositionLabelSignatureStatus.INVALID
            return self._build_row(
                command,
                now=now,
                status=parsed.status,
                signature_status=signature_status,
                payload_hash=parsed.payload_hash,
                public_identifier=parsed.label_id,
                payload_version=parsed.version,
                bounding_box_json=code.bounding_box,
                rotation_degrees=code.rotation_degrees,
                confidence=code.confidence,
                detail=parsed.detail,
                metadata=_payload_hierarchy_meta(parsed.payload),
            )

        validated = self._validator.validate(parsed)
        if validated.detection_status is not PositionLabelDetectionStatus.VALID:
            logger.info(
                "position_label_validation_failed client_id=%s job_id=%s asset_id=%s "
                "label_id=%s detection_status=%s detector_version=%s correlation_id=%s",
                command.client_id,
                command.job_id,
                command.source_asset_id,
                parsed.label_id,
                validated.detection_status.value,
                self._detector_version,
                command.correlation_id,
            )
            return self._build_row(
                command,
                now=now,
                status=validated.detection_status,
                signature_status=validated.signature_status,
                payload_hash=parsed.payload_hash,
                public_identifier=parsed.label_id,
                payload_version=parsed.version,
                bounding_box_json=code.bounding_box,
                rotation_degrees=code.rotation_degrees,
                confidence=code.confidence,
                detail=validated.detail,
            )

        assert parsed.label_id is not None
        resolved = self._resolver.resolve(
            public_label_id=parsed.label_id,
            expected_client_id=command.client_id,
        )
        if resolved.detection_status is PositionLabelDetectionStatus.CLIENT_MISMATCH:
            logger.info(
                "position_label_client_mismatch client_id=%s job_id=%s asset_id=%s "
                "label_id=%s detector_version=%s correlation_id=%s",
                command.client_id,
                command.job_id,
                command.source_asset_id,
                parsed.label_id,
                self._detector_version,
                command.correlation_id,
            )
            return self._build_row(
                command,
                now=now,
                status=PositionLabelDetectionStatus.CLIENT_MISMATCH,
                signature_status=validated.signature_status,
                payload_hash=parsed.payload_hash,
                public_identifier=None,
                payload_version=parsed.version,
                bounding_box_json=code.bounding_box,
                rotation_degrees=code.rotation_degrees,
                confidence=code.confidence,
                detail=resolved.detail,
            )
        if resolved.detection_status is not PositionLabelDetectionStatus.VALID:
            return self._build_row(
                command,
                now=now,
                status=resolved.detection_status,
                signature_status=validated.signature_status,
                payload_hash=parsed.payload_hash,
                public_identifier=parsed.label_id,
                position_label_id=resolved.label.id if resolved.label else None,
                position_name_snapshot=resolved.label.name if resolved.label else None,
                payload_version=parsed.version,
                bounding_box_json=code.bounding_box,
                rotation_degrees=code.rotation_degrees,
                confidence=code.confidence,
                detail=resolved.detail,
            )

        assert resolved.label is not None
        logger.info(
            "position_label_resolved client_id=%s job_id=%s asset_id=%s label_id=%s "
            "detection_status=%s detector_version=%s correlation_id=%s",
            command.client_id,
            command.job_id,
            command.source_asset_id,
            resolved.label.public_identifier,
            PositionLabelDetectionStatus.VALID.value,
            self._detector_version,
            command.correlation_id,
        )
        return self._build_row(
            command,
            now=now,
            status=PositionLabelDetectionStatus.VALID,
            signature_status=validated.signature_status,
            payload_hash=parsed.payload_hash,
            public_identifier=resolved.label.public_identifier,
            position_label_id=resolved.label.id,
            position_name_snapshot=resolved.label.name,
            payload_version=parsed.version,
            bounding_box_json=code.bounding_box,
            rotation_degrees=code.rotation_degrees,
            confidence=code.confidence,
            metadata=_payload_hierarchy_meta(parsed.payload),
        )

    def _try_resolve_unsigned_label(
        self,
        *,
        command: ImagePositionDetectionCommand,
        code: DetectedCode,
        parsed: ParsedPositionLabelPayload,
        now: datetime,
    ) -> ImagePositionLabelDetection | None:
        assert parsed.label_id is not None
        resolved = self._resolver.resolve(
            public_label_id=parsed.label_id,
            expected_client_id=command.client_id,
        )
        if resolved.detection_status is not PositionLabelDetectionStatus.VALID:
            return None
        assert resolved.label is not None
        label = resolved.label
        if label.signature_status is not ClientPositionLabelSignatureStatus.UNSIGNED:
            return None
        # Stored unsigned payloads are {type, version, label_id} — match QR content.
        stored = label.canonical_payload or {}
        if stored.get("signature"):
            return None
        if (stored.get("type") or "").strip() != "DINAMIC_POSITION":
            return None
        if (stored.get("label_id") or "").strip() != parsed.label_id.strip():
            return None
        logger.info(
            "position_label_resolved_unsigned client_id=%s job_id=%s asset_id=%s label_id=%s "
            "detection_status=%s detector_version=%s correlation_id=%s",
            command.client_id,
            command.job_id,
            command.source_asset_id,
            label.public_identifier,
            PositionLabelDetectionStatus.LEGACY_UNSIGNED_REQUIRES_REVIEW.value,
            self._detector_version,
            command.correlation_id,
        )
        return self._build_row(
            command,
            now=now,
            status=PositionLabelDetectionStatus.LEGACY_UNSIGNED_REQUIRES_REVIEW,
            signature_status=PositionLabelSignatureStatus.MISSING,
            payload_hash=parsed.payload_hash or label.payload_hash,
            public_identifier=label.public_identifier,
            position_label_id=label.id,
            position_name_snapshot=label.name,
            payload_version=parsed.version or label.payload_version,
            bounding_box_json=code.bounding_box,
            rotation_degrees=code.rotation_degrees,
            confidence=code.confidence,
            detail="unsigned_label_accepted",
            metadata={
                "unsigned_acceptance": True,
                **_payload_hierarchy_meta(parsed.payload),
            },
        )

    def _persist_many(
        self, rows: list[ImagePositionLabelDetection]
    ) -> list[ImagePositionLabelDetection]:
        if not self._persistence_enabled:
            return rows
        if not rows:
            return []
        return list(
            self._repo.replace_asset_detections_atomically(
                job_id=rows[0].job_id,
                source_asset_id=rows[0].source_asset_id,
                detector_version=rows[0].detector_version,
                detections=rows,
            )
        )

    def _build_row(
        self,
        command: ImagePositionDetectionCommand,
        *,
        now: datetime,
        status: PositionLabelDetectionStatus,
        signature_status: PositionLabelSignatureStatus,
        payload_hash: str | None,
        public_identifier: str | None = None,
        position_label_id: str | None = None,
        position_name_snapshot: str | None = None,
        payload_version: int | None = None,
        bounding_box_json: dict[str, Any] | None = None,
        rotation_degrees: float | None = None,
        confidence: float | None = None,
        detail: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ImagePositionLabelDetection:
        meta = dict(metadata or {})
        if detail:
            meta["detail"] = detail
        return ImagePositionLabelDetection(
            id=str(uuid4()),
            client_id=command.client_id,
            inventory_id=command.inventory_id,
            job_id=command.job_id,
            source_asset_id=command.source_asset_id,
            client_image_id=command.client_image_id,
            ordered_capture_session_id=command.ordered_capture_session_id,
            sequence_number=command.sequence_number,
            position_label_id=position_label_id,
            public_identifier=public_identifier,
            position_name_snapshot=position_name_snapshot,
            payload_version=payload_version,
            signature_status=signature_status,
            detection_status=status,
            confidence=confidence,
            bounding_box_json=bounding_box_json,
            rotation_degrees=rotation_degrees,
            raw_payload_hash=payload_hash,
            detector_name=self._detector_name,
            detector_version=self._detector_version,
            created_at=now,
            updated_at=now,
            metadata_json=meta,
        )
