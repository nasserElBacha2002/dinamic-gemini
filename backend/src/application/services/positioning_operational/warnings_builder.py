"""Build actionable positioning warnings for the operational view."""

from __future__ import annotations

from collections.abc import Sequence

from src.domain.position_label_detection.entities import PositionLabelDetectionStatus
from src.domain.position_reconciliation.entities import AssignmentStatus
from src.domain.positioning_operational.entities import (
    PositioningOperationalWarning,
    PositioningWarningSeverity,
    UnassignedCauseBucket,
)

_UNASSIGNED_HINTS: dict[str, str] = {
    AssignmentStatus.UNASSIGNED_NO_PREVIOUS_POSITION.value: "revisar secuencia",
    AssignmentStatus.UNASSIGNED_AFTER_AMBIGUOUS_POSITION.value: "resolver ambigüedad",
    AssignmentStatus.UNASSIGNED_INVALID_POSITION.value: "revisar etiqueta inválida",
    AssignmentStatus.UNASSIGNED_UNORDERED_ASSET.value: "asignar secuencia",
    "NO_RECONCILIATION": "ejecutar reconciliación",
    "ASSIGNMENT_MISSING": "reconciliar nuevamente",
    "MANUAL_REMOVE": "restaurar automática o asignar",
}


def transition_message_for_action(action: str | None, *, reason: str | None = None) -> str:
    key = (action or "").strip().upper()
    messages = {
        "SET_POSITION": "Se estableció una nueva posición a partir de la etiqueta detectada.",
        "KEEP_POSITION": (
            "La posición anterior se mantuvo porque esta imagen no contiene una etiqueta válida."
        ),
        "CLEAR_POSITION": "Se limpió la posición efectiva para este frame.",
        "AMBIGUOUS": "Se detectó más de una etiqueta de posición válida en la misma imagen.",
        "INVALID_SIGNATURE": "La firma de la etiqueta de posición no es válida.",
        "CLIENT_MISMATCH": "La etiqueta no pertenece a este cliente.",
        "LEGACY_UNSIGNED_REQUIRES_REVIEW": (
            "Etiqueta sin firma criptográfica: la posición se aplicó y queda marcada para revisión."
        ),
        "NO_LABEL": "No se detectó etiqueta de posicionamiento en esta imagen.",
    }
    base = messages.get(key)
    if base is None and reason:
        return reason
    return base or (reason or "Evento de transición de posición.")


def build_operational_warnings(
    *,
    processing_state: str,
    recoverable: bool,
    reconciliation_status: str | None,
    unassigned_count: int,
    ambiguous_count: int,
    detections_count: int,
    unordered_count: int,
    invalid_count: int,
    stale_count: int,
    allowed_action_names: frozenset[str] | None = None,
) -> tuple[PositioningOperationalWarning, ...]:
    warnings: list[PositioningOperationalWarning] = []
    state = (processing_state or "").upper()

    def _actions(*names: str) -> tuple[str, ...]:
        if allowed_action_names is None:
            return names
        return tuple(n for n in names if n in allowed_action_names)

    if recoverable or state == "RECOVERY_REQUIRED":
        warnings.append(
            PositioningOperationalWarning(
                code="PROCESSING_RECOVERY_REQUIRED",
                title="Recuperación de procesamiento requerida",
                description=(
                    "El procesamiento quedó interrumpido. Recuperelo antes de iniciar uno nuevo."
                ),
                severity=PositioningWarningSeverity.ERROR,
                affected_count=1,
                allowed_actions=_actions("recover"),
            )
        )
    if (reconciliation_status or "").upper() == "STALE":
        warnings.append(
            PositioningOperationalWarning(
                code="RECONCILIATION_STALE",
                title="Reconciliación desactualizada",
                description=(
                    "La última posición publicada se mantiene, pero conviene reconciliar nuevamente."
                ),
                severity=PositioningWarningSeverity.WARNING,
                affected_count=stale_count or unassigned_count,
                allowed_actions=_actions("reconcile_only", "reprocess"),
            )
        )
    if detections_count == 0 and unassigned_count > 0:
        warnings.append(
            PositioningOperationalWarning(
                code="NO_POSITION_LABEL_DETECTIONS",
                title="Sin detecciones de etiqueta",
                description=(
                    "No hay detecciones de etiqueta de posicionamiento en este job. "
                    "Verifique que el procesamiento use CODE_SCAN."
                ),
                severity=PositioningWarningSeverity.WARNING,
                affected_count=unassigned_count,
                allowed_actions=_actions("reprocess", "review"),
            )
        )
    if ambiguous_count > 0:
        warnings.append(
            PositioningOperationalWarning(
                code="AMBIGUOUS_POSITION_LABEL",
                title="Detecciones ambiguas",
                description="Hay imágenes con más de una etiqueta de posición válida.",
                severity=PositioningWarningSeverity.WARNING,
                affected_count=ambiguous_count,
                allowed_actions=_actions("review"),
            )
        )
    if unordered_count > 0:
        warnings.append(
            PositioningOperationalWarning(
                code="SEQUENCE_MISSING",
                title="Assets sin secuencia",
                description="Algunos assets no tienen número de secuencia ordenado.",
                severity=PositioningWarningSeverity.WARNING,
                affected_count=unordered_count,
                allowed_actions=_actions("review"),
            )
        )
    if invalid_count > 0:
        warnings.append(
            PositioningOperationalWarning(
                code="INVALID_POSITION_LABEL",
                title="Etiquetas inválidas",
                description="Hay detecciones de posición inválidas o con firma rechazada.",
                severity=PositioningWarningSeverity.WARNING,
                affected_count=invalid_count,
                allowed_actions=_actions("review", "correct_position"),
            )
        )
    if unassigned_count > 0:
        warnings.append(
            PositioningOperationalWarning(
                code="PRODUCTS_WITHOUT_POSITION",
                title="Productos sin posición",
                description="Hay resultados sin posición efectiva asignada.",
                severity=PositioningWarningSeverity.INFO,
                affected_count=unassigned_count,
                allowed_actions=_actions("review", "correct_position"),
            )
        )
    return tuple(warnings)


def unassigned_buckets_from_assignments(
    assignment_statuses: Sequence[str],
) -> tuple[UnassignedCauseBucket, ...]:
    counts: dict[str, int] = {}
    for raw in assignment_statuses:
        status = (raw or "").strip()
        if not status or status == AssignmentStatus.ASSIGNED_AUTOMATIC.value:
            continue
        if status.startswith("UNASSIGNED") or status in _UNASSIGNED_HINTS:
            counts[status] = counts.get(status, 0) + 1
    buckets = [
        UnassignedCauseBucket(
            cause=cause,
            count=count,
            suggested_action=_UNASSIGNED_HINTS.get(cause, "revisar resultados"),
        )
        for cause, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    return tuple(buckets)


def is_ambiguous_detection_status(status: str | PositionLabelDetectionStatus | None) -> bool:
    if status is None:
        return False
    value = status.value if isinstance(status, PositionLabelDetectionStatus) else str(status)
    return value.upper() in {
        PositionLabelDetectionStatus.AMBIGUOUS_POSITION_DETECTION.value,
        PositionLabelDetectionStatus.DUPLICATE_POSITION_CODES.value,
        "AMBIGUOUS",
    }


def is_invalid_detection_status(status: str | PositionLabelDetectionStatus | None) -> bool:
    if status is None:
        return False
    value = status.value if isinstance(status, PositionLabelDetectionStatus) else str(status)
    return value.upper() in {
        PositionLabelDetectionStatus.INVALID_SIGNATURE.value,
        PositionLabelDetectionStatus.INVALID_JSON.value,
        PositionLabelDetectionStatus.CLIENT_MISMATCH.value,
        PositionLabelDetectionStatus.LEGACY_UNSIGNED_REQUIRES_REVIEW.value,
        PositionLabelDetectionStatus.LABEL_INVALIDATED.value,
        PositionLabelDetectionStatus.LABEL_NOT_FOUND.value,
    }
