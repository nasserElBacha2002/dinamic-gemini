"""Build read-only review signals from latest code scan detections (Phase 6A)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from src.application.services.code_scan_summary import detection_counts_toward_summary
from src.domain.code_scans.entities import CodeScanDetection, CodeScanRun
from src.domain.code_scans.matching import CodeScanMatchStatus
from src.domain.code_scans.signals import CodeScanSignalSeverity, CodeScanSignalType

MANY_UNMATCHED_THRESHOLD = 3
MANY_MULTIPLE_CANDIDATES_THRESHOLD = 2


@dataclass(frozen=True)
class CodeScanReviewSignal:
    id: str
    type: str
    severity: str
    message: str
    detection_id: str | None = None
    position_id: str | None = None
    asset_id: str | None = None
    code_value: str | None = None
    code_type: str | None = None


@dataclass(frozen=True)
class CodeScanReviewSignalsSummary:
    total_signals: int
    info: int
    warning: int
    attention: int
    unmatched_codes: int
    multiple_candidates: int
    matched_codes: int


def _message_for_type(signal_type: CodeScanSignalType) -> str:
    return {
        CodeScanSignalType.CODE_MATCH_FOUND: "Coincidencia sugerida con resultado existente.",
        CodeScanSignalType.CODE_NO_MATCH: "Código detectado sin resultado vinculado.",
        CodeScanSignalType.CODE_MULTIPLE_CANDIDATES: "El código coincide con más de un resultado posible.",
        CodeScanSignalType.CODE_CONFLICT: "Posible conflicto de código.",
        CodeScanSignalType.CODE_DETECTED_WITHOUT_RESULT: "Código detectado sin resultado vinculado.",
        CodeScanSignalType.RESULT_HAS_CODE_EVIDENCE: "Este resultado tiene evidencia de código asociada.",
        CodeScanSignalType.RESULT_WITHOUT_CODE_EVIDENCE: "No hay códigos vinculados a este resultado.",
        CodeScanSignalType.MANY_UNMATCHED_CODES_IN_AISLE: (
            "Hay varios códigos sin coincidencia en este pasillo."
        ),
        CodeScanSignalType.MANY_MULTIPLE_CANDIDATE_CODES_IN_AISLE: (
            "Hay varios códigos con coincidencia múltiple en este pasillo."
        ),
        CodeScanSignalType.MATCHING_NOT_EVALUATED: "No se evaluaron coincidencias para este código.",
    }[signal_type]


def _emit(
    signals: list[CodeScanReviewSignal],
    *,
    signal_type: CodeScanSignalType,
    severity: CodeScanSignalSeverity,
    detection: CodeScanDetection | None = None,
    position_id: str | None = None,
) -> None:
    signals.append(
        CodeScanReviewSignal(
            id=str(uuid4()),
            type=signal_type.value,
            severity=severity.value,
            message=_message_for_type(signal_type),
            detection_id=detection.id if detection else None,
            position_id=position_id or (detection.matched_position_id if detection else None),
            asset_id=detection.asset_id if detection else None,
            code_value=detection.code_value if detection else None,
            code_type=detection.code_type.value if detection else None,
        )
    )


def _matching_skipped(metadata: dict[str, Any] | None) -> bool:
    if not metadata:
        return False
    matching = metadata.get("matching")
    if not isinstance(matching, dict):
        return False
    return matching.get("status") == "skipped" or matching.get("attempted") is False


def build_review_signals(
    *,
    detections: tuple[CodeScanDetection, ...],
    latest_run: CodeScanRun | None,
) -> tuple[CodeScanReviewSignal, ...]:
    if latest_run is None:
        return ()

    signals: list[CodeScanReviewSignal] = []
    eligible = [d for d in detections if detection_counts_toward_summary(d.detection_status)]

    if _matching_skipped(latest_run.metadata_json):
        _emit(
            signals,
            signal_type=CodeScanSignalType.MATCHING_NOT_EVALUATED,
            severity=CodeScanSignalSeverity.WARNING,
        )

    status_counts: Counter[str] = Counter()
    positions_with_evidence: set[str] = set()

    for det in eligible:
        status = (det.match_status or CodeScanMatchStatus.NOT_EVALUATED.value).strip()
        status_counts[status] += 1

        if status == CodeScanMatchStatus.MATCHED.value:
            _emit(
                signals,
                signal_type=CodeScanSignalType.CODE_MATCH_FOUND,
                severity=CodeScanSignalSeverity.INFO,
                detection=det,
            )
            if det.matched_position_id:
                positions_with_evidence.add(det.matched_position_id)
        elif status == CodeScanMatchStatus.NO_MATCH.value:
            _emit(
                signals,
                signal_type=CodeScanSignalType.CODE_NO_MATCH,
                severity=CodeScanSignalSeverity.ATTENTION,
                detection=det,
            )
        elif status == CodeScanMatchStatus.MULTIPLE_CANDIDATES.value:
            _emit(
                signals,
                signal_type=CodeScanSignalType.CODE_MULTIPLE_CANDIDATES,
                severity=CodeScanSignalSeverity.WARNING,
                detection=det,
            )
        elif status == CodeScanMatchStatus.CONFLICT.value:
            _emit(
                signals,
                signal_type=CodeScanSignalType.CODE_CONFLICT,
                severity=CodeScanSignalSeverity.WARNING,
                detection=det,
            )
        elif status == CodeScanMatchStatus.NOT_EVALUATED.value:
            _emit(
                signals,
                signal_type=CodeScanSignalType.MATCHING_NOT_EVALUATED,
                severity=CodeScanSignalSeverity.WARNING,
                detection=det,
            )

    for position_id in sorted(positions_with_evidence):
        _emit(
            signals,
            signal_type=CodeScanSignalType.RESULT_HAS_CODE_EVIDENCE,
            severity=CodeScanSignalSeverity.INFO,
            position_id=position_id,
        )

    unmatched = status_counts.get(CodeScanMatchStatus.NO_MATCH.value, 0)
    multi = status_counts.get(CodeScanMatchStatus.MULTIPLE_CANDIDATES.value, 0)

    if unmatched >= MANY_UNMATCHED_THRESHOLD:
        _emit(
            signals,
            signal_type=CodeScanSignalType.MANY_UNMATCHED_CODES_IN_AISLE,
            severity=CodeScanSignalSeverity.ATTENTION,
        )
    if multi >= MANY_MULTIPLE_CANDIDATES_THRESHOLD:
        _emit(
            signals,
            signal_type=CodeScanSignalType.MANY_MULTIPLE_CANDIDATE_CODES_IN_AISLE,
            severity=CodeScanSignalSeverity.WARNING,
        )

    return tuple(signals)


def summarize_signals(
    signals: tuple[CodeScanReviewSignal, ...],
    *,
    detections: tuple[CodeScanDetection, ...] = (),
) -> CodeScanReviewSignalsSummary:
    info = sum(1 for s in signals if s.severity == CodeScanSignalSeverity.INFO.value)
    warning = sum(1 for s in signals if s.severity == CodeScanSignalSeverity.WARNING.value)
    attention = sum(1 for s in signals if s.severity == CodeScanSignalSeverity.ATTENTION.value)

    status_counts: Counter[str] = Counter()
    for det in detections:
        if not detection_counts_toward_summary(det.detection_status):
            continue
        status_counts[(det.match_status or CodeScanMatchStatus.NOT_EVALUATED.value).strip()] += 1

    return CodeScanReviewSignalsSummary(
        total_signals=len(signals),
        info=info,
        warning=warning,
        attention=attention,
        unmatched_codes=status_counts.get(CodeScanMatchStatus.NO_MATCH.value, 0),
        multiple_candidates=status_counts.get(
            CodeScanMatchStatus.MULTIPLE_CANDIDATES.value, 0
        ),
        matched_codes=status_counts.get(CodeScanMatchStatus.MATCHED.value, 0),
    )
