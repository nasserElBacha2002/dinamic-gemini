"""Upsert mobile preliminary CODE_SCAN draft — diagnostic only, never creates positions."""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal, cast

from src.application.errors import (
    ClientSupplierClientMismatchError,
    ClientSupplierNotFoundError,
)
from src.application.ports.clock import Clock
from src.application.ports.mobile_preliminary_detection_repository import (
    MobilePreliminaryDetectionRepository,
    PreliminaryUniqueViolationError,
)
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    SourceAssetRepository,
)
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.application.services.label_profile_resolver import (
    LabelProfileResolutionContext,
    LabelProfileResolver,
)
from src.application.services.position_recognition import (
    CanonicalPositionValidationCommand,
    CanonicalPositionValidator,
)
from src.application.services.preliminary_detection_content import (
    PreliminaryDetectionContentCanonicalizer,
)
from src.domain.label_profiles.errors import SupplierLabelProfileNotConfiguredError
from src.domain.label_validation import CandidateLabel
from src.domain.label_validation.context import LabelValidationContext
from src.domain.mobile_preliminary_detections.entities import MobilePreliminaryDetection
from src.domain.position_recognition import (
    CanonicalPositionValidationStatus,
    PositionRecognitionSource,
)

logger = logging.getLogger(__name__)

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$", re.IGNORECASE)
_ALLOWED_STATUS = frozenset(
    {
        "RESOLVED",
        "UNRESOLVED",
        "INVALID",
        "AMBIGUOUS",
        "FAILED",
        "FAILED_RETRYABLE",
        "DETECTED_UNVERIFIED",
        "NOT_APPLICABLE",
    }
)
_ALLOWED_QTY_STATUS = frozenset({"PRESENT", "MISSING", "INVALID"})
_ALLOWED_SYMBOLOGY = frozenset(
    {"QR_CODE", "CODE_128", "CODE_39", "EAN_13", "EAN_8", "UPC_A", "UPC_E", "UNKNOWN"}
)
_ALLOWED_POSITION_SOURCES = frozenset(
    {"LOCAL_CODE_SCAN", "SERVER_CODE_SCAN", "VISION", "OCR", "TXT", "MANUAL"}
)
_CODE_MAX = 48
_QTY_MAX = 99_999_999
_RETENTION_DAYS = 90

PRELIMINARY_INGEST_DISABLED = "PRELIMINARY_INGEST_DISABLED"
PRELIMINARY_ASSET_PENDING = "PRELIMINARY_ASSET_PENDING"
PRELIMINARY_VALIDATION_FAILED = "PRELIMINARY_VALIDATION_FAILED"
PRELIMINARY_IDEMPOTENCY_CONFLICT = "PRELIMINARY_IDEMPOTENCY_CONFLICT"
PRELIMINARY_FORBIDDEN = "PRELIMINARY_FORBIDDEN"
PositionAuthoritativeStatus = Literal[
    "ACCEPTED_EXISTING",
    "ACCEPTED_UNMATERIALIZED",
    "REJECTED_FORMAT",
    "REJECTED_PROFILE",
    "REJECTED_SCOPE",
    "REJECTED_INVENTORY_STATE",
    "REJECTED_AMBIGUOUS",
    "REJECTED_DUPLICATE",
    "RETRYABLE_ERROR",
]


@dataclass(frozen=True)
class UpsertPreliminaryDetectionCommand:
    inventory_id: str
    aisle_id: str
    draft_id: str
    schema_version: str
    capture_session_id: str | None
    capture_photo_id: str | None
    client_file_id: str
    asset_id: str
    processing_mode: str
    status: str
    internal_code: str | None
    quantity: int | None
    quantity_status: str | None
    detected_format: str | None
    detected_symbology: str | None
    candidate_count: int
    parser_version: str
    detector_version: str
    prepared_asset_sha256: str
    payload_hash: str | None
    processing_ms: int | None
    detected_at: datetime | None
    position_reference: PositionReferenceEvidenceV2 | None = None


@dataclass(frozen=True)
class PositionSignatureEvidenceV2:
    present: bool
    verification: str


@dataclass(frozen=True)
class PositionReferenceEvidenceV2:
    payload_version: int
    local_recognition_id: str
    raw_code: str
    normalized_code: str
    remote_position_id: str | None
    remote_position_label_id: str | None
    source: str
    profile_id: str | None
    profile_version: int | None
    client_supplier_id: str | None
    signature: PositionSignatureEvidenceV2
    captured_at: datetime


@dataclass(frozen=True)
class PositionAuthoritativeResultV2:
    local_recognition_id: str
    normalized_code: str | None
    remote_position_id: str | None
    remote_position_label_id: str | None
    status: PositionAuthoritativeStatus
    error_code: str | None
    retryable: bool
    server_timestamp: datetime
    reconciliation_revision: int = 1


@dataclass(frozen=True)
class UpsertPreliminaryDetectionResult:
    draft_id: str
    requested_draft_id: str
    server_preliminary_id: str
    status: str
    received_at: datetime
    validation_errors: tuple[str, ...]
    duplicate: bool = False
    error_code: str | None = None
    position_result: PositionAuthoritativeResultV2 | None = None


class UpsertPreliminaryDetectionUseCase:
    def __init__(
        self,
        *,
        aisle_repo: AisleRepository,
        asset_repo: SourceAssetRepository,
        preliminary_repo: MobilePreliminaryDetectionRepository,
        clock: Clock,
        enabled: bool,
        inventory_repo: InventoryRepository | None = None,
        canonical_position_validator: CanonicalPositionValidator | None = None,
        label_profile_resolver: LabelProfileResolver | None = None,
        retention_days: int = _RETENTION_DAYS,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._asset_repo = asset_repo
        self._preliminary_repo = preliminary_repo
        self._clock = clock
        self._enabled = enabled
        self._inventory_repo = inventory_repo
        self._canonical_position_validator = canonical_position_validator
        self._label_profile_resolver = label_profile_resolver
        self._retention_days = max(1, int(retention_days))
        self._canonicalizer = PreliminaryDetectionContentCanonicalizer()

    def execute(
        self, command: UpsertPreliminaryDetectionCommand
    ) -> UpsertPreliminaryDetectionResult:
        if not self._enabled:
            raise PreliminaryDetectionIngestDisabledError()

        aisle = require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            detail_style="strict",
        )

        incoming = self._canonicalizer.from_command_like(command)
        errors = self._validate_payload(command, incoming)
        if errors:
            now = self._clock.now()
            return UpsertPreliminaryDetectionResult(
                draft_id=command.draft_id.strip(),
                requested_draft_id=command.draft_id.strip(),
                server_preliminary_id="",
                status="REJECTED",
                received_at=now,
                validation_errors=tuple(errors),
                error_code=PRELIMINARY_VALIDATION_FAILED,
            )

        asset = self._asset_repo.get_by_id(command.asset_id.strip())
        if asset is None or asset.aisle_id != command.aisle_id.strip():
            now = self._clock.now()
            return UpsertPreliminaryDetectionResult(
                draft_id=command.draft_id.strip(),
                requested_draft_id=command.draft_id.strip(),
                server_preliminary_id="",
                status="PENDING_ASSET",
                received_at=now,
                validation_errors=("ASSET_NOT_FOUND_OR_MISMATCHED",),
                error_code=PRELIMINARY_ASSET_PENDING,
            )

        client_file = incoming.client_file_id
        asset_client = (asset.upload_client_file_id or "").strip()
        if asset_client and asset_client != client_file:
            now = self._clock.now()
            return UpsertPreliminaryDetectionResult(
                draft_id=command.draft_id.strip(),
                requested_draft_id=command.draft_id.strip(),
                server_preliminary_id="",
                status="REJECTED",
                received_at=now,
                validation_errors=("CLIENT_FILE_ID_MISMATCH",),
                error_code=PRELIMINARY_VALIDATION_FAILED,
            )

        existing_draft = self._preliminary_repo.get_by_draft_id(incoming.draft_id)
        if existing_draft is not None:
            return self._compare_existing(existing_draft, incoming, requested=incoming.draft_id)

        existing_key = self._preliminary_repo.get_by_idempotency_key(
            client_file_id=client_file,
            detector_version=incoming.detector_version,
            parser_version=incoming.parser_version,
            prepared_asset_sha256=incoming.prepared_asset_sha256,
        )
        if existing_key is not None:
            return self._compare_existing(existing_key, incoming, requested=incoming.draft_id)

        position_result = self._validate_position_reference(
            command,
            aisle_active=aisle.is_active,
            aisle_client_supplier_id=aisle.client_supplier_id,
        )
        if position_result is not None and position_result.retryable:
            now = self._clock.now()
            return UpsertPreliminaryDetectionResult(
                draft_id=incoming.draft_id,
                requested_draft_id=incoming.draft_id,
                server_preliminary_id="",
                status="VALIDATED",
                received_at=now,
                validation_errors=(),
                position_result=position_result,
            )
        return self._insert_new(
            command,
            incoming,
            asset_id=asset.id,
            position_result=position_result,
        )

    def purge_expired(self) -> int:
        now = self._clock.now()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        deleted = int(self._preliminary_repo.delete_expired(now=now, limit=500))
        if deleted:
            logger.info("preliminary_detection_purged count=%s", deleted)
        return deleted

    def _insert_new(
        self,
        command: UpsertPreliminaryDetectionCommand,
        incoming,
        *,
        asset_id: str,
        position_result: PositionAuthoritativeResultV2 | None,
    ) -> UpsertPreliminaryDetectionResult:
        now = self._clock.now()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        entity = MobilePreliminaryDetection(
            id=str(uuid.uuid4()),
            draft_id=incoming.draft_id,
            inventory_id=command.inventory_id.strip(),
            aisle_id=command.aisle_id.strip(),
            asset_id=asset_id,
            client_file_id=incoming.client_file_id,
            status=incoming.status,
            internal_code=incoming.internal_code,
            quantity=incoming.quantity,
            quantity_status=incoming.quantity_status,
            detected_format=incoming.detected_format,
            detected_symbology=incoming.detected_symbology,
            candidate_count=incoming.candidate_count,
            parser_version=incoming.parser_version,
            detector_version=incoming.detector_version,
            prepared_asset_sha256=incoming.prepared_asset_sha256,
            payload_hash=incoming.payload_hash,
            processing_ms=command.processing_ms,
            detected_at=command.detected_at,
            received_at=now,
            expires_at=now + timedelta(days=self._retention_days),
            validation_status="VALIDATED",
            validation_error_code=None,
            schema_version=incoming.schema_version,
            created_at=now,
            updated_at=now,
            position_local_recognition_id=(
                command.position_reference.local_recognition_id
                if command.position_reference is not None
                else None
            ),
            position_raw_code=(
                command.position_reference.raw_code
                if command.position_reference is not None
                else None
            ),
            position_claimed_normalized_code=(
                command.position_reference.normalized_code
                if command.position_reference is not None
                else None
            ),
            position_claimed_remote_id=(
                command.position_reference.remote_position_id
                if command.position_reference is not None
                else None
            ),
            position_claimed_remote_label_id=(
                command.position_reference.remote_position_label_id
                if command.position_reference is not None
                else None
            ),
            position_source=(
                command.position_reference.source
                if command.position_reference is not None
                else None
            ),
            position_profile_id=(
                command.position_reference.profile_id
                if command.position_reference is not None
                else None
            ),
            position_profile_version=(
                command.position_reference.profile_version
                if command.position_reference is not None
                else None
            ),
            position_client_supplier_id=(
                command.position_reference.client_supplier_id
                if command.position_reference is not None
                else None
            ),
            position_signature_present=(
                command.position_reference.signature.present
                if command.position_reference is not None
                else None
            ),
            position_signature_verification=(
                command.position_reference.signature.verification
                if command.position_reference is not None
                else None
            ),
            position_captured_at=(
                command.position_reference.captured_at
                if command.position_reference is not None
                else None
            ),
            position_result_status=position_result.status if position_result else None,
            position_result_error_code=position_result.error_code if position_result else None,
            position_result_retryable=position_result.retryable if position_result else None,
            position_normalized_code=position_result.normalized_code if position_result else None,
            position_remote_id=position_result.remote_position_id if position_result else None,
            position_remote_label_id=(
                position_result.remote_position_label_id if position_result else None
            ),
            position_validated_at=position_result.server_timestamp if position_result else None,
            position_reconciliation_revision=(
                position_result.reconciliation_revision if position_result else 0
            ),
        )
        try:
            saved = self._preliminary_repo.insert(entity)
        except PreliminaryUniqueViolationError as exc:
            return self._resolve_unique_race(exc.constraint, incoming)

        logger.info(
            "preliminary_detection_validated draft_id=%s asset_id=%s status=%s",
            saved.draft_id,
            saved.asset_id,
            saved.status,
        )
        return UpsertPreliminaryDetectionResult(
            draft_id=saved.draft_id,
            requested_draft_id=incoming.draft_id,
            server_preliminary_id=saved.id,
            status=saved.validation_status,
            received_at=saved.received_at,
            validation_errors=(),
            position_result=position_result,
        )

    def _resolve_unique_race(self, constraint: str, incoming) -> UpsertPreliminaryDetectionResult:
        if constraint == "draft_id":
            existing = self._preliminary_repo.get_by_draft_id(incoming.draft_id)
        else:
            existing = self._preliminary_repo.get_by_idempotency_key(
                client_file_id=incoming.client_file_id,
                detector_version=incoming.detector_version,
                parser_version=incoming.parser_version,
                prepared_asset_sha256=incoming.prepared_asset_sha256,
            )
        if existing is None:
            # Extremely rare: deleted between conflict and re-read
            now = self._clock.now()
            return UpsertPreliminaryDetectionResult(
                draft_id=incoming.draft_id,
                requested_draft_id=incoming.draft_id,
                server_preliminary_id="",
                status="CONFLICT",
                received_at=now,
                validation_errors=("IDEMPOTENCY_RACE_UNRESOLVED",),
                error_code=PRELIMINARY_IDEMPOTENCY_CONFLICT,
            )
        return self._compare_existing(existing, incoming, requested=incoming.draft_id)

    def _compare_existing(
        self, existing: MobilePreliminaryDetection, incoming, *, requested: str
    ) -> UpsertPreliminaryDetectionResult:
        existing_content = self._canonicalizer.from_command_like(existing)
        same = (
            self._canonicalizer.same_for_draft_id(existing_content, incoming)
            if existing.draft_id == incoming.draft_id
            else self._canonicalizer.same_payload(existing_content, incoming)
        )
        if same:
            return UpsertPreliminaryDetectionResult(
                draft_id=existing.draft_id,
                requested_draft_id=requested,
                server_preliminary_id=existing.id,
                status=existing.validation_status,
                received_at=existing.received_at,
                validation_errors=(),
                duplicate=True,
                position_result=self._position_result_from_entity(existing),
            )
        now = self._clock.now()
        return UpsertPreliminaryDetectionResult(
            draft_id=existing.draft_id,
            requested_draft_id=requested,
            server_preliminary_id=existing.id,
            status="CONFLICT",
            received_at=now,
            validation_errors=("IDEMPOTENCY_CONTENT_CONFLICT",),
            error_code=PRELIMINARY_IDEMPOTENCY_CONFLICT,
        )

    def _validate_payload(self, command: UpsertPreliminaryDetectionCommand, incoming) -> list[str]:
        errors: list[str] = []
        if not incoming.draft_id:
            errors.append("DRAFT_ID_REQUIRED")
        if incoming.schema_version not in ("1", "2"):
            errors.append("SCHEMA_VERSION_UNSUPPORTED")
        if incoming.schema_version == "2" and command.position_reference is None:
            errors.append("POSITION_REFERENCE_REQUIRED")
        if incoming.schema_version == "1" and command.position_reference is not None:
            errors.append("POSITION_REFERENCE_REQUIRES_SCHEMA_V2")
        if (
            command.position_reference is not None
            and command.position_reference.source.strip().upper() not in _ALLOWED_POSITION_SOURCES
        ):
            errors.append("POSITION_SOURCE_INVALID")
        if (command.processing_mode or "").strip().upper() != "CODE_SCAN":
            errors.append("PROCESSING_MODE_INVALID")
        if incoming.status not in _ALLOWED_STATUS:
            errors.append("STATUS_INVALID")
        if not incoming.client_file_id:
            errors.append("CLIENT_FILE_ID_REQUIRED")
        if not incoming.asset_id:
            errors.append("ASSET_ID_REQUIRED")
        if not incoming.parser_version:
            errors.append("PARSER_VERSION_REQUIRED")
        if not incoming.detector_version:
            errors.append("DETECTOR_VERSION_REQUIRED")
        if not _SHA256_RE.match(incoming.prepared_asset_sha256 or ""):
            errors.append("PREPARED_ASSET_SHA256_INVALID")
        if incoming.payload_hash and not _SHA256_RE.match(incoming.payload_hash):
            errors.append("PAYLOAD_HASH_INVALID")
        if incoming.candidate_count < 0 or incoming.candidate_count > 100:
            errors.append("CANDIDATE_COUNT_INVALID")
        if incoming.detected_symbology and incoming.detected_symbology not in _ALLOWED_SYMBOLOGY:
            errors.append("SYMBIOLOGY_INVALID")
        if incoming.quantity_status and incoming.quantity_status not in _ALLOWED_QTY_STATUS:
            errors.append("QUANTITY_STATUS_INVALID")

        if incoming.status == "RESOLVED":
            if not incoming.internal_code:
                errors.append("INTERNAL_CODE_REQUIRED_FOR_RESOLVED")
            elif len(incoming.internal_code) > _CODE_MAX:
                errors.append("INTERNAL_CODE_TOO_LONG")
        if incoming.status in ("UNRESOLVED", "NOT_APPLICABLE") and incoming.internal_code:
            errors.append("INTERNAL_CODE_MUST_BE_NULL")
        if incoming.status == "AMBIGUOUS" and incoming.quantity is not None:
            errors.append("AMBIGUOUS_MUST_NOT_HAVE_QUANTITY")

        if incoming.quantity_status == "PRESENT":
            if incoming.quantity is None or incoming.quantity < 1 or incoming.quantity > _QTY_MAX:
                errors.append("QUANTITY_REQUIRED_WHEN_PRESENT")
        if incoming.quantity_status in ("MISSING", "INVALID") and incoming.quantity is not None:
            errors.append("QUANTITY_MUST_BE_NULL")

        return errors

    def _validate_position_reference(
        self,
        command: UpsertPreliminaryDetectionCommand,
        *,
        aisle_active: bool,
        aisle_client_supplier_id: str | None,
    ) -> PositionAuthoritativeResultV2 | None:
        reference = command.position_reference
        if reference is None:
            return None
        now = self._clock.now()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        def outcome(
            status: PositionAuthoritativeStatus,
            error_code: str | None,
            *,
            normalized_code: str | None = None,
            remote_position_label_id: str | None = None,
            retryable: bool = False,
        ) -> PositionAuthoritativeResultV2:
            return PositionAuthoritativeResultV2(
                local_recognition_id=reference.local_recognition_id,
                normalized_code=normalized_code,
                remote_position_id=None,
                remote_position_label_id=remote_position_label_id,
                status=status,
                error_code=error_code,
                retryable=retryable,
                server_timestamp=now,
            )

        if self._inventory_repo is None:
            return outcome(
                "RETRYABLE_ERROR", "POSITION_INVENTORY_REPOSITORY_UNAVAILABLE", retryable=True
            )
        inventory = self._inventory_repo.get_by_id(command.inventory_id.strip())
        if inventory is None or inventory.is_deleted or not aisle_active:
            return outcome("REJECTED_INVENTORY_STATE", "POSITION_INVENTORY_STATE_INVALID")
        client_id = (inventory.client_id or "").strip()
        if not client_id:
            return outcome("REJECTED_SCOPE", "POSITION_CLIENT_CONTEXT_MISSING")
        if (
            reference.client_supplier_id
            and reference.client_supplier_id.strip() != (aisle_client_supplier_id or "").strip()
        ):
            return outcome("REJECTED_SCOPE", "POSITION_SUPPLIER_SCOPE_MISMATCH")
        if self._canonical_position_validator is None:
            return outcome("RETRYABLE_ERROR", "POSITION_VALIDATOR_UNAVAILABLE", retryable=True)

        resolved_profiles = None
        if self._label_profile_resolver is not None:
            try:
                resolved_profiles = self._label_profile_resolver.resolve(
                    LabelProfileResolutionContext(
                        client_id=client_id,
                        client_supplier_id=aisle_client_supplier_id,
                        aisle=self._aisle_repo.get_by_id(command.aisle_id.strip()),
                    )
                )
            except (
                ClientSupplierClientMismatchError,
                ClientSupplierNotFoundError,
                SupplierLabelProfileNotConfiguredError,
            ):
                return outcome("REJECTED_PROFILE", "POSITION_PROFILE_RESOLUTION_FAILED")

        try:
            canonical = self._canonical_position_validator.validate(
                CanonicalPositionValidationCommand(
                    candidate=CandidateLabel(raw_payload=reference.raw_code),
                    source=PositionRecognitionSource.MOBILE,
                    context=LabelValidationContext(
                        resolved_profiles=resolved_profiles,
                        job_id=command.capture_session_id,
                        client_id=client_id,
                    ),
                    client_supplier_id=aisle_client_supplier_id,
                )
            )
        except (TimeoutError, ConnectionError, OSError):
            logger.warning(
                "preliminary_position_validation_unavailable draft_id=%s inventory_id=%s",
                command.draft_id,
                command.inventory_id,
            )
            return outcome("RETRYABLE_ERROR", "POSITION_VALIDATION_UNAVAILABLE", retryable=True)

        recognition = canonical.recognition
        normalized_code = recognition.normalized_code if recognition is not None else None
        if (
            normalized_code is not None
            and reference.normalized_code.strip().upper() != normalized_code
        ):
            return outcome(
                "REJECTED_FORMAT",
                "POSITION_NORMALIZED_CODE_MISMATCH",
                normalized_code=normalized_code,
            )
        if canonical.status is CanonicalPositionValidationStatus.VALID_EXISTING:
            label_id = canonical.existing_position_label_id
            if (
                reference.remote_position_label_id is not None
                and reference.remote_position_label_id.strip() != (label_id or "")
            ):
                return outcome(
                    "REJECTED_SCOPE",
                    "POSITION_REMOTE_LABEL_MISMATCH",
                    normalized_code=normalized_code,
                    remote_position_label_id=label_id,
                )
            return outcome(
                "ACCEPTED_EXISTING",
                None,
                normalized_code=normalized_code,
                remote_position_label_id=label_id,
            )
        if canonical.status is CanonicalPositionValidationStatus.VALID_UNMATERIALIZED:
            return outcome("ACCEPTED_UNMATERIALIZED", None, normalized_code=normalized_code)
        if canonical.status is CanonicalPositionValidationStatus.AMBIGUOUS_CODE:
            return outcome(
                "REJECTED_AMBIGUOUS",
                canonical.error_code,
                normalized_code=normalized_code,
            )
        if canonical.status is CanonicalPositionValidationStatus.PROFILE_NOT_ALLOWED:
            status: PositionAuthoritativeStatus = (
                "REJECTED_SCOPE"
                if canonical.error_code
                in {"POSITION_SCOPE_MISMATCH", "POSITION_SUPPLIER_SCOPE_MISMATCH"}
                else "REJECTED_PROFILE"
            )
            return outcome(status, canonical.error_code, normalized_code=normalized_code)
        if canonical.status is CanonicalPositionValidationStatus.INTERNAL_ERROR:
            return outcome(
                "RETRYABLE_ERROR",
                canonical.error_code,
                normalized_code=normalized_code,
                retryable=True,
            )
        return outcome(
            "REJECTED_FORMAT",
            canonical.error_code or canonical.status.value,
            normalized_code=normalized_code,
        )

    @staticmethod
    def _position_result_from_entity(
        row: MobilePreliminaryDetection,
    ) -> PositionAuthoritativeResultV2 | None:
        if row.position_local_recognition_id is None or row.position_result_status is None:
            return None
        return PositionAuthoritativeResultV2(
            local_recognition_id=row.position_local_recognition_id,
            normalized_code=row.position_normalized_code,
            remote_position_id=row.position_remote_id,
            remote_position_label_id=row.position_remote_label_id,
            status=cast(PositionAuthoritativeStatus, row.position_result_status),
            error_code=row.position_result_error_code,
            retryable=bool(row.position_result_retryable),
            server_timestamp=row.position_validated_at or row.received_at,
            reconciliation_revision=row.position_reconciliation_revision,
        )


class PreliminaryDetectionIngestDisabledError(Exception):
    """Server ingest flag is off."""
