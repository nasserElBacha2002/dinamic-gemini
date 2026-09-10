"""Bridge import productive rows to Phase 3 canonical position materialization."""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from src.application.dto.access_principal import AccessPrincipal
from src.application.dto.position_materialization import MaterializePositionCommand
from src.application.ports.repositories import AisleRepository
from src.application.services.position_materialization.service import MaterializePositionService
from src.application.services.position_recognition import (
    PositionCodeNormalizationError,
    normalize_position_code,
)
from src.domain.local_csv_import.entities import LocalCsvProductiveResult
from src.domain.local_csv_import.sources import INGESTION_SOURCE_DINAMIC_SCANNER_TXT
from src.domain.position_materialization.entities import (
    MAX_ID_LENGTH,
    PositionMaterializationStatus,
)
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

_IMPORT_ACTOR = "import-position-materializer"

_SUCCESS_STATUSES = frozenset(
    {
        PositionMaterializationStatus.MATERIALIZED,
        PositionMaterializationStatus.REUSED,
    }
)


@dataclass(frozen=True)
class ImportCanonicalMaterializationSummary:
    attempted: int
    created_or_reused: int
    skipped: int
    failed: int
    last_status: str | None = None
    last_error_code: str | None = None
    last_detail: str | None = None


class ImportCanonicalPositionMaterializer:
    """Materialize unique aisle positions via Phase 3 service (no second creator)."""

    def __init__(
        self,
        *,
        materialize_service: MaterializePositionService,
        enabled: bool,
        aisle_repo: AisleRepository | None = None,
    ) -> None:
        self._service = materialize_service
        self._enabled = enabled
        self._aisle_repo = aisle_repo

    def materialize_from_results(
        self,
        results: Sequence[LocalCsvProductiveResult],
        *,
        client_id: str,
        actor_id: str | None = None,
    ) -> ImportCanonicalMaterializationSummary:
        if not self._enabled:
            return ImportCanonicalMaterializationSummary(0, 0, 0, 0)

        principal = AccessPrincipal(
            actor_id=(actor_id or "").strip() or _IMPORT_ACTOR,
            client_id=client_id,
            roles=frozenset({"system"}),
            is_platform=False,
        )
        seen: set[tuple[str, str]] = set()
        supplier_by_aisle: dict[str, str | None] = {}
        attempted = 0
        created_or_reused = 0
        skipped = 0
        failed = 0
        last_status: str | None = None
        last_error_code: str | None = None
        last_detail: str | None = None

        for result in results:
            code = (result.position_code or "").strip()
            if not code:
                skipped += 1
                continue
            try:
                normalized = normalize_position_code(code).normalized_code
            except PositionCodeNormalizationError as exc:
                failed += 1
                last_status = PositionMaterializationStatus.REJECTED_VALIDATION.value
                last_error_code = getattr(exc, "code", None) or "POSITION_CODE_INVALID"
                last_detail = str(exc)
                break
            key = (result.aisle_id, normalized)
            if key in seen:
                skipped += 1
                continue
            seen.add(key)
            attempted += 1
            source = _source_for(result)
            if result.aisle_id not in supplier_by_aisle:
                supplier_by_aisle[result.aisle_id] = _aisle_client_supplier_id(
                    self._aisle_repo, result.aisle_id
                )
            command = _command_for(
                result,
                normalized_code=normalized,
                source=source,
                principal=principal,
                client_supplier_id=supplier_by_aisle[result.aisle_id],
            )
            outcome = self._service.execute(command)
            if outcome.status in _SUCCESS_STATUSES:
                created_or_reused += 1
                continue
            failed += 1
            last_status = outcome.status.value
            last_error_code = outcome.error_code
            last_detail = outcome.detail
            logger.warning(
                "import_canonical_materialization_reject status=%s error_code=%s "
                "import_id=%s aisle_id=%s",
                outcome.status.value,
                outcome.error_code,
                result.import_id,
                result.aisle_id,
            )
            record_position_materialization(
                component=PositionMaterializationMetricComponent.SERVICE,
                source=(
                    PositionMaterializationMetricSource.TXT
                    if source is PositionRecognitionSource.TXT
                    else PositionMaterializationMetricSource.CSV
                ),
                mode=PositionMaterializationMetricMode.SUPPLIER,
                outcome=PositionMaterializationMetricOutcome.VALIDATION_REJECTED,
                reason_code=PositionMaterializationMetricReason.INVALID_REQUEST,
            )
            break

        return ImportCanonicalMaterializationSummary(
            attempted=attempted,
            created_or_reused=created_or_reused,
            skipped=skipped,
            failed=failed,
            last_status=last_status,
            last_error_code=last_error_code,
            last_detail=last_detail,
        )


def _source_for(result: LocalCsvProductiveResult) -> PositionRecognitionSource:
    ingestion = (result.ingestion_source or "").strip().upper()
    if ingestion == INGESTION_SOURCE_DINAMIC_SCANNER_TXT:
        return PositionRecognitionSource.TXT
    return PositionRecognitionSource.CSV


def materialization_capture_id(result: LocalCsvProductiveResult) -> str:
    """Fit Phase 3 ``capture_id`` (max 36) while keeping mobile/TXT ids stable.

    Prefer ``source_asset_id`` when the package already created a UUID asset.
    Mobile ZIP photos use ``{session_id}:{media_store_id}`` (~47 chars). TXT imports
    use ``txt-scan-…`` keys. Both exceed ``MAX_ID_LENGTH``; map them to a
    deterministic UUID so confirm does not fail validation.
    """
    asset = (result.source_asset_id or "").strip()
    if asset and len(asset) <= MAX_ID_LENGTH:
        return asset
    raw = (result.capture_photo_id or "").strip()
    if raw and len(raw) <= MAX_ID_LENGTH:
        return raw
    if raw:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"dinamic:import-capture:{raw}"))
    fallback = (result.id or "").strip()
    if fallback and len(fallback) <= MAX_ID_LENGTH:
        return fallback
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"dinamic:import-result:{result.import_id}:{raw}"))


def _aisle_client_supplier_id(
    aisle_repo: AisleRepository | None, aisle_id: str
) -> str | None:
    """Mirror aisle supplier onto recognition so Phase 3 scope checks pass.

    Package/CSV productive rows do not carry ``client_supplier_id``; the aisle is
    the durable scope owner used by materialization UoW.
    """
    if aisle_repo is None:
        return None
    aisle = aisle_repo.get_by_id(aisle_id)
    if aisle is None:
        return None
    supplier = (aisle.client_supplier_id or "").strip()
    return supplier or None


def _command_for(
    result: LocalCsvProductiveResult,
    *,
    normalized_code: str,
    source: PositionRecognitionSource,
    principal: AccessPrincipal,
    client_supplier_id: str | None = None,
) -> MaterializePositionCommand:
    raw = (result.position_code or "").strip() or normalized_code
    recognition = CanonicalPositionRecognition(
        raw_code=raw,
        normalized_code=normalized_code,
        source=source,
        client_supplier_id=client_supplier_id,
        signature=PositionSignatureEvidence(
            present=False,
            verification=PositionSignatureVerification.NOT_APPLICABLE,
        ),
        evidence={
            "import_id": result.import_id,
            "import_row_id": result.import_row_id,
            "productive_result_id": result.id,
            "capture_photo_id": (result.capture_photo_id or "").strip() or None,
        },
    )
    identity = "\0".join(
        (
            result.import_id,
            result.aisle_id,
            source.value,
            normalized_code,
        )
    ).encode("utf-8")
    return MaterializePositionCommand(
        recognition=recognition,
        inventory_id=result.inventory_id,
        aisle_id=result.aisle_id,
        principal=principal,
        idempotency_key=(
            f"import:{source.value.lower()}:{hashlib.sha256(identity).hexdigest()}"
        ),
        capture_id=materialization_capture_id(result),
    )
