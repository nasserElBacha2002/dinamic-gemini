"""Upsert mobile preliminary CODE_SCAN draft — diagnostic only, never creates positions."""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from src.application.ports.clock import Clock
from src.application.ports.mobile_preliminary_detection_repository import (
    MobilePreliminaryDetectionRepository,
)
from src.application.ports.repositories import AisleRepository, SourceAssetRepository
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.domain.mobile_preliminary_detections.entities import MobilePreliminaryDetection

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
_CODE_MAX = 48
_QTY_MAX = 99_999_999


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


@dataclass(frozen=True)
class UpsertPreliminaryDetectionResult:
    draft_id: str
    server_preliminary_id: str
    status: str
    received_at: datetime
    validation_errors: tuple[str, ...]
    duplicate: bool = False


class UpsertPreliminaryDetectionUseCase:
    def __init__(
        self,
        *,
        aisle_repo: AisleRepository,
        asset_repo: SourceAssetRepository,
        preliminary_repo: MobilePreliminaryDetectionRepository,
        clock: Clock,
        enabled: bool,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._asset_repo = asset_repo
        self._preliminary_repo = preliminary_repo
        self._clock = clock
        self._enabled = enabled

    def execute(self, command: UpsertPreliminaryDetectionCommand) -> UpsertPreliminaryDetectionResult:
        if not self._enabled:
            raise PreliminaryDetectionIngestDisabledError()

        require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            detail_style="strict",
        )

        errors = self._validate_payload(command)
        if errors:
            now = self._clock.now()
            return UpsertPreliminaryDetectionResult(
                draft_id=command.draft_id,
                server_preliminary_id="",
                status="REJECTED",
                received_at=now,
                validation_errors=tuple(errors),
            )

        asset = self._asset_repo.get_by_id(command.asset_id.strip())
        if asset is None or asset.aisle_id != command.aisle_id.strip():
            now = self._clock.now()
            return UpsertPreliminaryDetectionResult(
                draft_id=command.draft_id,
                server_preliminary_id="",
                status="PENDING_ASSET",
                received_at=now,
                validation_errors=("ASSET_NOT_FOUND_OR_MISMATCHED",),
            )

        client_file = (command.client_file_id or "").strip()
        asset_client = (asset.upload_client_file_id or "").strip()
        if asset_client and asset_client != client_file:
            now = self._clock.now()
            return UpsertPreliminaryDetectionResult(
                draft_id=command.draft_id,
                server_preliminary_id="",
                status="REJECTED",
                received_at=now,
                validation_errors=("CLIENT_FILE_ID_MISMATCH",),
            )

        existing_draft = self._preliminary_repo.get_by_draft_id(command.draft_id.strip())
        if existing_draft is not None:
            if self._same_content(existing_draft, command):
                return UpsertPreliminaryDetectionResult(
                    draft_id=existing_draft.draft_id,
                    server_preliminary_id=existing_draft.id,
                    status=existing_draft.validation_status,
                    received_at=existing_draft.received_at,
                    validation_errors=(),
                    duplicate=True,
                )
            now = self._clock.now()
            return UpsertPreliminaryDetectionResult(
                draft_id=command.draft_id,
                server_preliminary_id=existing_draft.id,
                status="CONFLICT",
                received_at=now,
                validation_errors=("IDEMPOTENCY_CONTENT_CONFLICT",),
            )

        existing_key = self._preliminary_repo.get_by_idempotency_key(
            client_file_id=client_file,
            detector_version=command.detector_version.strip(),
            parser_version=command.parser_version.strip(),
            prepared_asset_sha256=command.prepared_asset_sha256.strip(),
        )
        if existing_key is not None and existing_key.draft_id != command.draft_id.strip():
            # Same image+versions+hash already stored under another draft_id → treat as duplicate
            return UpsertPreliminaryDetectionResult(
                draft_id=existing_key.draft_id,
                server_preliminary_id=existing_key.id,
                status=existing_key.validation_status,
                received_at=existing_key.received_at,
                validation_errors=(),
                duplicate=True,
            )

        now = self._clock.now()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        entity = MobilePreliminaryDetection(
            id=str(uuid.uuid4()),
            draft_id=command.draft_id.strip(),
            inventory_id=command.inventory_id.strip(),
            aisle_id=command.aisle_id.strip(),
            asset_id=asset.id,
            client_file_id=client_file,
            status=command.status.strip().upper(),
            internal_code=command.internal_code,
            quantity=command.quantity,
            quantity_status=command.quantity_status,
            detected_format=command.detected_format,
            detected_symbology=command.detected_symbology,
            candidate_count=max(0, int(command.candidate_count)),
            parser_version=command.parser_version.strip(),
            detector_version=command.detector_version.strip(),
            prepared_asset_sha256=command.prepared_asset_sha256.strip(),
            payload_hash=(command.payload_hash or "").strip() or None,
            processing_ms=command.processing_ms,
            detected_at=command.detected_at,
            received_at=now,
            validation_status="VALIDATED",
            validation_error_code=None,
            schema_version=(command.schema_version or "1").strip() or "1",
            created_at=now,
            updated_at=now,
        )
        saved = self._preliminary_repo.upsert(entity)
        logger.info(
            "preliminary_detection_validated draft_id=%s asset_id=%s status=%s",
            saved.draft_id,
            saved.asset_id,
            saved.status,
        )
        return UpsertPreliminaryDetectionResult(
            draft_id=saved.draft_id,
            server_preliminary_id=saved.id,
            status=saved.validation_status,
            received_at=saved.received_at,
            validation_errors=(),
        )

    def _same_content(
        self, existing: MobilePreliminaryDetection, command: UpsertPreliminaryDetectionCommand
    ) -> bool:
        return (
            existing.client_file_id == command.client_file_id.strip()
            and existing.asset_id == command.asset_id.strip()
            and existing.status == command.status.strip().upper()
            and (existing.internal_code or None) == (command.internal_code or None)
            and existing.quantity == command.quantity
            and existing.parser_version == command.parser_version.strip()
            and existing.detector_version == command.detector_version.strip()
            and existing.prepared_asset_sha256 == command.prepared_asset_sha256.strip()
            and (existing.payload_hash or None) == ((command.payload_hash or "").strip() or None)
        )

    def _validate_payload(self, command: UpsertPreliminaryDetectionCommand) -> list[str]:
        errors: list[str] = []
        if not (command.draft_id or "").strip():
            errors.append("DRAFT_ID_REQUIRED")
        if (command.schema_version or "").strip() not in ("1", "v1"):
            errors.append("SCHEMA_VERSION_UNSUPPORTED")
        if (command.processing_mode or "").strip().upper() != "CODE_SCAN":
            errors.append("PROCESSING_MODE_INVALID")
        status = (command.status or "").strip().upper()
        if status not in _ALLOWED_STATUS:
            errors.append("STATUS_INVALID")
        if not (command.client_file_id or "").strip():
            errors.append("CLIENT_FILE_ID_REQUIRED")
        if not (command.asset_id or "").strip():
            errors.append("ASSET_ID_REQUIRED")
        if not (command.parser_version or "").strip():
            errors.append("PARSER_VERSION_REQUIRED")
        if not (command.detector_version or "").strip():
            errors.append("DETECTOR_VERSION_REQUIRED")
        sha = (command.prepared_asset_sha256 or "").strip()
        if not _SHA256_RE.match(sha):
            errors.append("PREPARED_ASSET_SHA256_INVALID")
        if command.payload_hash and not _SHA256_RE.match(command.payload_hash.strip()):
            errors.append("PAYLOAD_HASH_INVALID")
        if command.candidate_count < 0 or command.candidate_count > 100:
            errors.append("CANDIDATE_COUNT_INVALID")
        symbology = (command.detected_symbology or "").strip().upper()
        if symbology and symbology not in _ALLOWED_SYMBOLOGY:
            errors.append("SYMBIOLOGY_INVALID")

        code = (command.internal_code or "").strip() or None
        qty_status = (command.quantity_status or "").strip().upper() or None
        if qty_status and qty_status not in _ALLOWED_QTY_STATUS:
            errors.append("QUANTITY_STATUS_INVALID")

        if status == "RESOLVED":
            if not code:
                errors.append("INTERNAL_CODE_REQUIRED_FOR_RESOLVED")
            elif len(code) > _CODE_MAX:
                errors.append("INTERNAL_CODE_TOO_LONG")
        if status in ("UNRESOLVED", "NOT_APPLICABLE") and code:
            errors.append("INTERNAL_CODE_MUST_BE_NULL")
        if status == "AMBIGUOUS" and command.quantity is not None:
            errors.append("AMBIGUOUS_MUST_NOT_HAVE_QUANTITY")

        if qty_status == "PRESENT":
            if command.quantity is None or command.quantity < 1 or command.quantity > _QTY_MAX:
                errors.append("QUANTITY_REQUIRED_WHEN_PRESENT")
        if qty_status in ("MISSING", "INVALID") and command.quantity is not None:
            errors.append("QUANTITY_MUST_BE_NULL")

        return errors


class PreliminaryDetectionIngestDisabledError(Exception):
    """Server ingest flag is off."""


class PreliminaryDetectionConflictError(Exception):
    """Idempotency content conflict for the same draft_id."""
