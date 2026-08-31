"""CODE_SCAN single-pass label classification (kind / source / ambiguity).

Strategy owns scanning, timeout, orchestration, metrics, and materialization.
This classifier owns deterministic CandidateLabel → typed classification only.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from src.application.ports.code_scanner import CodeScanDetectionCandidate
from src.application.services.label_validation import (
    LabelValidationService,
    item_profile_source,
    position_profile_source,
)
from src.domain.code_scans.entities import CodeType
from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource
from src.domain.label_validation import (
    CandidateLabel,
    LabelValidationErrorCode,
    LabelValidationStatus,
    NormalizedItemLabel,
    NormalizedPositionLabel,
    RecognitionSource,
)
from src.domain.label_validation.context import LabelValidationContext

_SYMBOLOGY_BY_CODE_TYPE = {
    CodeType.QR: "QR_CODE",
    CodeType.BARCODE: "CODE_128",
    CodeType.DATAMATRIX: "DATA_MATRIX",
    CodeType.UNKNOWN: "UNKNOWN",
}


def _symbology_for_candidate(candidate: CodeScanDetectionCandidate) -> str:
    meta = candidate.metadata_json if isinstance(candidate.metadata_json, dict) else {}
    raw = meta.get("pyzbar_type") or meta.get("symbology")
    if isinstance(raw, str) and raw.strip():
        return raw.strip().upper()
    return _SYMBOLOGY_BY_CODE_TYPE.get(candidate.code_type, "UNKNOWN")


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


@dataclass(frozen=True)
class ClassifiedItem:
    detection_index: int
    label: NormalizedItemLabel
    candidate: CodeScanDetectionCandidate


@dataclass(frozen=True)
class ClassifiedPosition:
    detection_index: int
    label: NormalizedPositionLabel
    candidate: CodeScanDetectionCandidate


@dataclass(frozen=True)
class ClassificationRejection:
    detection_index: int
    error_code: str | None
    detail: str | None
    raw_payload_hash: str
    label_kind: LabelKind | None = None


@dataclass(frozen=True)
class CodeScanClassificationResult:
    """Typed CODE_SCAN classification outcome (no dict[str, Any] contract)."""

    items: tuple[ClassifiedItem, ...]
    positions: tuple[ClassifiedPosition, ...]
    ambiguous_indexes: tuple[int, ...]
    rejections: tuple[ClassificationRejection, ...]
    #: Candidates neither claimed as item/position nor hard-rejected (legacy leftover).
    leftover: tuple[tuple[int, CodeScanDetectionCandidate], ...]

    @property
    def has_ambiguity(self) -> bool:
        return bool(self.ambiguous_indexes)

    @property
    def position_candidate_indexes(self) -> tuple[int, ...]:
        return tuple(p.detection_index for p in self.positions)

    @property
    def item_candidates(self) -> tuple[CodeScanDetectionCandidate, ...]:
        return tuple(i.candidate for i in self.items)


class CodeScanLabelClassifier:
    """Classify decoded CODE_SCAN candidates with one policy (no POSITION-first)."""

    def __init__(self, validation_service: LabelValidationService | None = None) -> None:
        self._validation = validation_service or LabelValidationService()

    def classify(
        self,
        candidates: list[CodeScanDetectionCandidate],
        *,
        context: LabelValidationContext,
    ) -> CodeScanClassificationResult:
        items: list[ClassifiedItem] = []
        positions: list[ClassifiedPosition] = []
        ambiguous: list[int] = []
        rejections: list[ClassificationRejection] = []
        leftover: list[tuple[int, CodeScanDetectionCandidate]] = []
        seen_item_ids: set[str] = set()
        seen_position_ids: set[str] = set()

        item_source = item_profile_source(context)
        position_source = position_profile_source(context)

        for idx, cand in enumerate(candidates):
            raw = (cand.code_value or "").strip()
            result = self._validation.validate_best_effort(
                CandidateLabel(
                    raw_payload=raw,
                    recognition_source=RecognitionSource.CODE_SCAN,
                    symbology=_symbology_for_candidate(cand),
                ),
                context=context,
            )

            if result.status is LabelValidationStatus.AMBIGUOUS:
                ambiguous.append(idx)
                rejections.append(
                    ClassificationRejection(
                        detection_index=idx,
                        error_code=result.error_code
                        or LabelValidationErrorCode.AMBIGUOUS_LABEL_KIND.value,
                        detail=result.detail,
                        raw_payload_hash=_sha256_hex(raw),
                    )
                )
                continue

            if (
                result.status is LabelValidationStatus.VALID
                and isinstance(result.label, NormalizedItemLabel)
            ):
                identity = (result.label.label_id or result.label.sku).strip()
                if identity in seen_item_ids:
                    rejections.append(
                        ClassificationRejection(
                            detection_index=idx,
                            error_code="DUPLICATE",
                            detail="duplicate supplier/item identity in image",
                            raw_payload_hash=_sha256_hex(raw),
                            label_kind=LabelKind.ITEM,
                        )
                    )
                    continue
                seen_item_ids.add(identity)
                items.append(
                    ClassifiedItem(detection_index=idx, label=result.label, candidate=cand)
                )
                continue

            if (
                result.status is LabelValidationStatus.VALID
                and isinstance(result.label, NormalizedPositionLabel)
            ):
                identity = result.label.position_id.strip()
                if identity in seen_position_ids:
                    rejections.append(
                        ClassificationRejection(
                            detection_index=idx,
                            error_code="DUPLICATE",
                            detail="duplicate position identity in image",
                            raw_payload_hash=_sha256_hex(raw),
                            label_kind=LabelKind.POSITION,
                        )
                    )
                    continue
                seen_position_ids.add(identity)
                positions.append(
                    ClassifiedPosition(
                        detection_index=idx, label=result.label, candidate=cand
                    )
                )
                continue

            if result.status is LabelValidationStatus.NOT_APPLICABLE:
                leftover.append((idx, cand))
                continue

            # INVALID / TECHNICAL — fail-closed Dinamic under SUPPLIER stays rejected.
            rejections.append(
                ClassificationRejection(
                    detection_index=idx,
                    error_code=result.error_code or result.status.value,
                    detail=result.detail,
                    raw_payload_hash=_sha256_hex(raw),
                    label_kind=result.label_kind,
                )
            )
            # Do not feed Dinamic-looking invalids back into the opposite kind path.
            if result.error_code and (
                "DINAMIC" in result.error_code
                or result.error_code
                == LabelValidationErrorCode.LABEL_PROFILE_SOURCE_MISMATCH.value
            ):
                continue
            # Soft supplier mismatch may still be leftover for opposite legacy path
            # only when the profile source for that kind is DINAMIC.
            if item_source is LabelProfileSource.DINAMIC or (
                position_source is LabelProfileSource.DINAMIC
            ):
                leftover.append((idx, cand))

        return CodeScanClassificationResult(
            items=tuple(items),
            positions=tuple(positions),
            ambiguous_indexes=tuple(ambiguous),
            rejections=tuple(rejections),
            leftover=tuple(leftover),
        )
