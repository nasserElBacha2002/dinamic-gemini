"""Persist operator-confirmed local CODE_SCAN as authoritative (versioned) result."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from src.application.ports.authoritative_local_code_scan_repository import (
    AuthoritativeLocalCodeScanRepository,
    AuthoritativeUniqueViolationError,
)
from src.application.ports.clock import Clock
from src.application.ports.repositories import AisleRepository, SourceAssetRepository
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.domain.authoritative_local_code_scan.entities import (
    AuthoritativeLocalCodeScanResult,
    AuthoritativeQuantityStatus,
    AuthoritativeResultSource,
)

logger = logging.getLogger(__name__)

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$", re.IGNORECASE)
_CODE_MAX = 48
_QTY_MAX = 99_999_999
_ALLOWED_SOURCES = frozenset(
    {
        AuthoritativeResultSource.LOCAL_CODE_SCAN.value,
        AuthoritativeResultSource.LOCAL_MANUAL_CORRECTION.value,
    }
)
_ALLOWED_SYMBOLOGY = frozenset(
    {"QR_CODE", "CODE_128", "CODE_39", "EAN_13", "EAN_8", "UPC_A", "UPC_E", "UNKNOWN"}
)
_CODE_CHARSET = re.compile(r"^[A-Za-z0-9._\-/#]+$")

AUTH_INGEST_DISABLED = "AUTHORITATIVE_INGEST_DISABLED"
AUTH_VALIDATION_FAILED = "AUTHORITATIVE_VALIDATION_FAILED"
AUTH_IDEMPOTENCY_CONFLICT = "AUTHORITATIVE_IDEMPOTENCY_CONFLICT"
AUTH_ASSET_MISMATCH = "AUTHORITATIVE_ASSET_MISMATCH"
AUTH_FORBIDDEN = "AUTHORITATIVE_FORBIDDEN"


@dataclass(frozen=True)
class PersistAuthoritativeLocalCodeScanCommand:
    inventory_id: str
    aisle_id: str
    asset_id: str
    result_id: str
    schema_version: str
    client_file_id: str
    internal_code: str
    quantity: int | None
    quantity_status: str
    source: str
    detected_internal_code: str | None
    detected_quantity: int | None
    detected_symbology: str | None
    parser_version: str
    detector_version: str
    prepared_asset_sha256: str
    confirmed_at: datetime | None
    # Ignored if present — derived from auth.
    confirmed_by_user_id: str | None = None


@dataclass(frozen=True)
class PersistAuthoritativeLocalCodeScanResult:
    result_id: str
    asset_id: str
    result_version: int
    is_current: bool
    supersedes_result_id: str | None
    status: str
    duplicate: bool = False
    validation_errors: tuple[str, ...] = ()
    error_code: str | None = None


class AuthoritativeIngestDisabledError(Exception):
    pass


def _canonical_content_hash(
    *,
    internal_code: str,
    quantity: int | None,
    quantity_status: str,
    source: str,
    detected_internal_code: str | None,
    detected_quantity: int | None,
    detected_symbology: str | None,
    parser_version: str,
    detector_version: str,
    prepared_asset_sha256: str,
    client_file_id: str,
    asset_id: str,
) -> str:
    payload = {
        "asset_id": asset_id,
        "client_file_id": client_file_id,
        "internal_code": internal_code,
        "quantity": quantity,
        "quantity_status": quantity_status,
        "source": source,
        "detected_internal_code": detected_internal_code,
        "detected_quantity": detected_quantity,
        "detected_symbology": detected_symbology,
        "parser_version": parser_version,
        "detector_version": detector_version,
        "prepared_asset_sha256": prepared_asset_sha256.lower(),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


class PersistAuthoritativeLocalCodeScanResultUseCase:
    """Store a versioned authoritative local result (final persist applied at /process)."""

    def __init__(
        self,
        *,
        aisle_repo: AisleRepository,
        asset_repo: SourceAssetRepository,
        authoritative_repo: AuthoritativeLocalCodeScanRepository,
        clock: Clock,
        enabled: bool,
        authenticated_user_id: str,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._asset_repo = asset_repo
        self._repo = authoritative_repo
        self._clock = clock
        self._enabled = enabled
        self._user_id = (authenticated_user_id or "").strip()

    def execute(
        self, command: PersistAuthoritativeLocalCodeScanCommand
    ) -> PersistAuthoritativeLocalCodeScanResult:
        if not self._enabled:
            raise AuthoritativeIngestDisabledError()
        if not self._user_id:
            return PersistAuthoritativeLocalCodeScanResult(
                result_id=command.result_id,
                asset_id=command.asset_id,
                result_version=0,
                is_current=False,
                supersedes_result_id=None,
                status="REJECTED",
                validation_errors=("authenticated_user_required",),
                error_code=AUTH_FORBIDDEN,
            )

        require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            detail_style="strict",
        )

        errors = self._validate(command)
        if errors:
            return PersistAuthoritativeLocalCodeScanResult(
                result_id=command.result_id,
                asset_id=command.asset_id,
                result_version=0,
                is_current=False,
                supersedes_result_id=None,
                status="REJECTED",
                validation_errors=tuple(errors),
                error_code=AUTH_VALIDATION_FAILED,
            )

        asset = self._asset_repo.get_by_id(command.asset_id.strip())
        if asset is None or asset.aisle_id != command.aisle_id.strip():
            return PersistAuthoritativeLocalCodeScanResult(
                result_id=command.result_id,
                asset_id=command.asset_id,
                result_version=0,
                is_current=False,
                supersedes_result_id=None,
                status="REJECTED",
                validation_errors=("asset_not_in_aisle",),
                error_code=AUTH_ASSET_MISMATCH,
            )

        result_id = command.result_id.strip()
        content_hash = _canonical_content_hash(
            internal_code=command.internal_code.strip(),
            quantity=command.quantity,
            quantity_status=command.quantity_status.strip().upper(),
            source=command.source.strip().upper(),
            detected_internal_code=(command.detected_internal_code or None),
            detected_quantity=command.detected_quantity,
            detected_symbology=(command.detected_symbology or None),
            parser_version=command.parser_version.strip(),
            detector_version=command.detector_version.strip(),
            prepared_asset_sha256=command.prepared_asset_sha256.strip(),
            client_file_id=command.client_file_id.strip(),
            asset_id=command.asset_id.strip(),
        )

        existing = self._repo.get_by_id(result_id)
        if existing is not None:
            if existing.content_hash == content_hash and existing.asset_id == command.asset_id.strip():
                logger.info(
                    "authoritative_local.duplicate result_id=%s asset_id=%s version=%s",
                    result_id,
                    existing.asset_id,
                    existing.result_version,
                )
                return PersistAuthoritativeLocalCodeScanResult(
                    result_id=existing.id,
                    asset_id=existing.asset_id,
                    result_version=existing.result_version,
                    is_current=existing.is_current,
                    supersedes_result_id=existing.supersedes_result_id,
                    status="OK",
                    duplicate=True,
                )
            return PersistAuthoritativeLocalCodeScanResult(
                result_id=result_id,
                asset_id=command.asset_id,
                result_version=existing.result_version,
                is_current=existing.is_current,
                supersedes_result_id=existing.supersedes_result_id,
                status="CONFLICT",
                error_code=AUTH_IDEMPOTENCY_CONFLICT,
                validation_errors=("result_id_content_mismatch",),
            )

        now = self._clock.now()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        confirmed_at = command.confirmed_at or now
        if confirmed_at.tzinfo is None:
            confirmed_at = confirmed_at.replace(tzinfo=timezone.utc)

        current = self._repo.get_current_for_asset(command.asset_id.strip())
        supersedes_id: str | None = None
        next_version = 1
        if current is not None:
            supersedes_id = current.id
            next_version = max(self._repo.max_version_for_asset(command.asset_id.strip()) + 1, current.result_version + 1)
            marked = self._repo.mark_superseded(
                result_id=current.id,
                expected_row_version=current.row_version,
                updated_at=now,
            )
            if marked is None:
                # Concurrent supersede — re-read and retry once via unique violation path.
                current2 = self._repo.get_current_for_asset(command.asset_id.strip())
                if current2 is not None and current2.id != current.id:
                    supersedes_id = current2.id
                    next_version = self._repo.max_version_for_asset(command.asset_id.strip()) + 1
                    marked2 = self._repo.mark_superseded(
                        result_id=current2.id,
                        expected_row_version=current2.row_version,
                        updated_at=now,
                    )
                    if marked2 is None:
                        return PersistAuthoritativeLocalCodeScanResult(
                            result_id=result_id,
                            asset_id=command.asset_id,
                            result_version=0,
                            is_current=False,
                            supersedes_result_id=None,
                            status="CONFLICT",
                            error_code=AUTH_IDEMPOTENCY_CONFLICT,
                            validation_errors=("concurrent_supersede",),
                        )

        code = command.internal_code.strip()
        qty_status = command.quantity_status.strip().upper()
        quantity = command.quantity if qty_status == AuthoritativeQuantityStatus.PRESENT.value else None
        source = command.source.strip().upper()
        detected_code = (command.detected_internal_code or "").strip() or None
        detected_sym = (command.detected_symbology or "").strip().upper() or None

        row = AuthoritativeLocalCodeScanResult(
            id=result_id or str(uuid.uuid4()),
            asset_id=command.asset_id.strip(),
            inventory_id=command.inventory_id.strip(),
            aisle_id=command.aisle_id.strip(),
            client_file_id=command.client_file_id.strip(),
            result_version=next_version,
            supersedes_result_id=supersedes_id,
            is_current=True,
            internal_code=code,
            quantity=quantity,
            quantity_status=qty_status,
            source=source,
            detected_internal_code=detected_code,
            detected_quantity=command.detected_quantity,
            detected_symbology=detected_sym,
            parser_version=command.parser_version.strip(),
            detector_version=command.detector_version.strip(),
            prepared_asset_sha256=command.prepared_asset_sha256.strip().lower(),
            content_hash=content_hash,
            confirmed_by=self._user_id,
            confirmed_at=confirmed_at,
            applied_job_id=None,
            applied_at=None,
            row_version=1,
            schema_version=(command.schema_version or "1").strip() or "1",
            created_at=now,
            updated_at=now,
        )

        try:
            saved = self._repo.insert(row)
        except AuthoritativeUniqueViolationError:
            raced = self._repo.get_by_id(result_id)
            if raced is not None and raced.content_hash == content_hash:
                return PersistAuthoritativeLocalCodeScanResult(
                    result_id=raced.id,
                    asset_id=raced.asset_id,
                    result_version=raced.result_version,
                    is_current=raced.is_current,
                    supersedes_result_id=raced.supersedes_result_id,
                    status="OK",
                    duplicate=True,
                )
            return PersistAuthoritativeLocalCodeScanResult(
                result_id=result_id,
                asset_id=command.asset_id,
                result_version=0,
                is_current=False,
                supersedes_result_id=None,
                status="CONFLICT",
                error_code=AUTH_IDEMPOTENCY_CONFLICT,
                validation_errors=("unique_violation",),
            )

        logger.info(
            "authoritative_local.persisted result_id=%s asset_id=%s version=%s "
            "source=%s supersedes=%s confirmed_by=%s",
            saved.id,
            saved.asset_id,
            saved.result_version,
            saved.source,
            saved.supersedes_result_id,
            saved.confirmed_by,
        )
        return PersistAuthoritativeLocalCodeScanResult(
            result_id=saved.id,
            asset_id=saved.asset_id,
            result_version=saved.result_version,
            is_current=saved.is_current,
            supersedes_result_id=saved.supersedes_result_id,
            status="OK",
            duplicate=False,
        )

    def _validate(self, command: PersistAuthoritativeLocalCodeScanCommand) -> list[str]:
        errors: list[str] = []
        if not (command.result_id or "").strip():
            errors.append("result_id_required")
        if not (command.client_file_id or "").strip():
            errors.append("client_file_id_required")
        if not (command.asset_id or "").strip():
            errors.append("asset_id_required")
        code = (command.internal_code or "").strip()
        if not code:
            errors.append("internal_code_required")
        elif len(code) > _CODE_MAX:
            errors.append("internal_code_too_long")
        elif not _CODE_CHARSET.match(code):
            errors.append("internal_code_charset")
        qty_status = (command.quantity_status or "").strip().upper()
        if qty_status not in {
            AuthoritativeQuantityStatus.PRESENT.value,
            AuthoritativeQuantityStatus.MISSING.value,
        }:
            errors.append("quantity_status_invalid")
        elif qty_status == AuthoritativeQuantityStatus.PRESENT.value:
            if command.quantity is None:
                errors.append("quantity_required_when_present")
            elif not isinstance(command.quantity, int) or isinstance(command.quantity, bool):
                errors.append("quantity_not_integer")
            elif command.quantity <= 0:
                errors.append("quantity_not_positive")
            elif command.quantity > _QTY_MAX:
                errors.append("quantity_too_large")
        elif command.quantity is not None:
            errors.append("quantity_must_be_null_when_missing")
        source = (command.source or "").strip().upper()
        if source not in _ALLOWED_SOURCES:
            errors.append("source_not_allowed")
        if not (command.parser_version or "").strip():
            errors.append("parser_version_required")
        if not (command.detector_version or "").strip():
            errors.append("detector_version_required")
        sha = (command.prepared_asset_sha256 or "").strip()
        if not sha or not _SHA256_RE.match(sha):
            errors.append("prepared_asset_sha256_invalid")
        sym = (command.detected_symbology or "").strip().upper()
        if sym and sym not in _ALLOWED_SYMBOLOGY:
            errors.append("detected_symbology_invalid")
        return errors
