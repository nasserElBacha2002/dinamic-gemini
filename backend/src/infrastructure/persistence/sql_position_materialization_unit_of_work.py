"""SQL Server atomic UOW for canonical physical-position materialization."""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timedelta
from typing import NoReturn, Protocol, cast

import pyodbc

from src.application.dto.position_materialization import (
    POSITION_MATERIALIZATION_FINGERPRINT_VERSION,
    MaterializePositionCommand,
)
from src.database.sqlserver import SqlServerClient
from src.domain.position_materialization.entities import (
    MaterializePositionResult,
    PositionMaterializationAssociationClaim,
    PositionMaterializationAssociationEvidence,
    PositionMaterializationAssociationStatus,
    PositionMaterializationEvidenceStatus,
    PositionMaterializationStatus,
)
from src.domain.inventory.write_policy import writable_status_values
from src.domain.position_materialization.errors import (
    PositionMaterializationConflictError,
    PositionMaterializationInvariantError,
    PositionMaterializationInventoryStateError,
    PositionMaterializationRetryableError,
    PositionMaterializationScopeError,
)
from src.infrastructure.database.position_materialization_sql_errors import (
    SqlFailureKind,
    classify_sql_failure,
)
from src.infrastructure.database.sql_transaction import SqlServerTransaction, TransactionState

logger = logging.getLogger(__name__)

_WRITABLE_INVENTORY_STATUSES = writable_status_values()


class _ReplayRow(Protocol):
    id: object
    request_hash: object
    fingerprint_version: int
    result: object
    location_id: object
    public_identifier: object


class _InventoryRow(Protocol):
    client_id: object
    status: object
    deleted_at: object


class _AisleRow(Protocol):
    inventory_id: object
    is_active: object
    client_supplier_id: object


class _IdentityLocationRow(Protocol):
    id: object
    public_identifier: object
    status: object
    client_supplier_id: object
    profile_id: object
    profile_version: object
    pallet: object
    side: object
    level: object
    marker_index: object
    marker_total: object


def _application_lock_resource(client_id: str, aisle_id: str, normalized_code: str) -> str:
    identity = "\x00".join((client_id, aisle_id, normalized_code)).encode("utf-8")
    return f"position-materialization:{hashlib.sha256(identity).hexdigest()}"


def _scope_error(message: str, code: str) -> PositionMaterializationScopeError:
    return PositionMaterializationScopeError(message, code=code)


def _conflict(message: str, code: str) -> PositionMaterializationConflictError:
    return PositionMaterializationConflictError(message, code=code)


class SqlPositionMaterializationUnitOfWork:
    def __init__(self, client: SqlServerClient, *, lock_timeout_ms: int = 10_000) -> None:
        if lock_timeout_ms < 0:
            raise ValueError("lock_timeout_ms must be non-negative")
        self._client = client
        self._lock_timeout_ms = lock_timeout_ms

    def lookup_replay(
        self,
        *,
        client_id: str,
        idempotency_key: str,
        request_hash: str,
    ) -> MaterializePositionResult | None:
        try:
            with self._client.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT r.id, r.request_hash, r.fingerprint_version,
                           r.result, r.location_id,
                           l.public_identifier
                    FROM dbo.position_materialization_requests AS r
                    INNER JOIN dbo.aisle_locations AS l ON l.id = r.location_id
                    WHERE r.client_id = ? AND r.idempotency_key = ?
                    """,
                    (client_id, idempotency_key),
                )
                row = cursor.fetchone()
        except pyodbc.ProgrammingError:
            raise
        except (pyodbc.DatabaseError, pyodbc.InterfaceError) as exc:  # type: ignore[attr-defined]
            self._raise_classified_sql_failure(exc)
        if row is None:
            return None
        return self._resolve_replay(row, request_hash)

    def materialize(
        self,
        command: MaterializePositionCommand,
        *,
        request_hash: str,
        now: datetime,
    ) -> MaterializePositionResult:
        client_id = command.principal.client_id
        if client_id is None:
            raise _scope_error("Tenant principal required", "PRINCIPAL_CLIENT_REQUIRED")

        txn = self._client.begin_transaction()
        txn.__enter__()
        try:
            cursor = txn.connection.cursor()
            replay = self._read_replay(cursor, client_id, command.idempotency_key)
            if replay is not None:
                result = self._resolve_replay(replay, request_hash)
                txn.commit()
                return result

            inventory = self._read_inventory(cursor, command.inventory_id)
            if (
                inventory is None
                or str(inventory.client_id) != client_id
                or inventory.deleted_at is not None
            ):
                raise _scope_error(
                    "Inventory is outside the principal scope",
                    "INVENTORY_SCOPE_MISMATCH",
                )

            aisle = self._read_aisle(cursor, command.aisle_id)
            if aisle is None or str(aisle.inventory_id) != command.inventory_id:
                raise _scope_error("Aisle is outside the inventory scope", "AISLE_SCOPE_MISMATCH")
            if not bool(aisle.is_active):
                raise _scope_error("Aisle is inactive", "AISLE_INACTIVE")
            aisle_supplier = aisle.client_supplier_id
            if aisle_supplier != command.recognition.client_supplier_id:
                raise _scope_error(
                    "Recognition supplier does not match aisle supplier",
                    "SUPPLIER_SCOPE_MISMATCH",
                )
            self._validate_profile_scope(cursor, command, client_id)
            if str(inventory.status).lower() not in _WRITABLE_INVENTORY_STATUSES:
                raise PositionMaterializationInventoryStateError(
                    "Inventory does not accept new positions",
                    code="INVENTORY_NOT_WRITABLE",
                )

            self._acquire_identity_lock(cursor, command, client_id)

            replay = self._read_replay(cursor, client_id, command.idempotency_key)
            if replay is not None:
                result = self._resolve_replay(replay, request_hash)
                txn.commit()
                return result

            location = self._read_identity_locations(cursor, command, client_id)
            if location is None:
                location_id, public_identifier = self._insert_location(
                    cursor, command, client_id, now
                )
                result_status = PositionMaterializationStatus.MATERIALIZED
            else:
                if str(location.status) != "ACTIVE":
                    raise _conflict(
                        "An inactive location already owns this canonical identity",
                        "INACTIVE_POSITION_IDENTITY",
                    )
                self._validate_compatible(location, command)
                location_id = str(location.id)
                public_identifier = str(location.public_identifier)
                result_status = PositionMaterializationStatus.REUSED

            request_id = str(uuid.uuid4())
            self._insert_request(
                cursor,
                request_id=request_id,
                command=command,
                client_id=client_id,
                location_id=location_id,
                request_hash=request_hash,
                result_status=result_status,
                now=now,
            )
            txn.commit()
            return MaterializePositionResult(
                status=result_status,
                idempotent_replay=False,
                location_id=location_id,
                public_identifier=public_identifier,
                request_id=request_id,
            )
        except (
            PositionMaterializationScopeError,
            PositionMaterializationConflictError,
            PositionMaterializationInventoryStateError,
            PositionMaterializationRetryableError,
        ):
            self._rollback_active(txn)
            raise
        except pyodbc.ProgrammingError:
            self._rollback_active(txn)
            raise
        except (pyodbc.DatabaseError, pyodbc.InterfaceError) as exc:  # type: ignore[attr-defined]
            self._rollback_active(txn)
            self._raise_classified_sql_failure(exc)
        except Exception:
            self._rollback_active(txn)
            raise
        finally:
            txn.close()

    def complete_association(
        self,
        request_id: str,
        *,
        target: PositionMaterializationAssociationStatus,
        error_code: str | None,
        now: datetime,
    ) -> bool:
        try:
            with self._client.cursor() as cursor:
                if target is PositionMaterializationAssociationStatus.ASSOCIATED:
                    cursor.execute(
                        """
                        UPDATE dbo.position_materialization_requests
                        SET association_status = 'ASSOCIATED',
                            associated_at = ?,
                            association_error_code = NULL
                        WHERE id = ?
                          AND association_status IN ('PENDING', 'REQUIRES_REVIEW')
                        """,
                        (now, request_id),
                    )
                elif target is PositionMaterializationAssociationStatus.REQUIRES_REVIEW:
                    cursor.execute(
                        """
                        UPDATE dbo.position_materialization_requests
                        SET association_status = 'REQUIRES_REVIEW',
                            associated_at = NULL,
                            association_error_code = ?
                        WHERE id = ? AND association_status = 'PENDING'
                        """,
                        (error_code, request_id),
                    )
                else:
                    raise ValueError(f"Unsupported association target: {target.value}")
                if int(cursor.rowcount or 0) > 0:
                    return True
                cursor.execute(
                    """
                    SELECT association_status
                    FROM dbo.position_materialization_requests
                    WHERE id = ?
                    """,
                    (request_id,),
                )
                row = cursor.fetchone()
                return row is not None and str(row.association_status) == target.value
        except pyodbc.ProgrammingError:
            raise
        except (pyodbc.DatabaseError, pyodbc.InterfaceError) as exc:  # type: ignore[attr-defined]
            self._raise_classified_sql_failure(exc)

    def get_association_status(
        self,
        request_id: str,
    ) -> PositionMaterializationAssociationStatus | None:
        try:
            with self._client.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT association_status
                    FROM dbo.position_materialization_requests
                    WHERE id = ?
                    """,
                    (request_id,),
                )
                row = cursor.fetchone()
        except pyodbc.ProgrammingError:
            raise
        except (pyodbc.DatabaseError, pyodbc.InterfaceError) as exc:  # type: ignore[attr-defined]
            self._raise_classified_sql_failure(exc)
        if row is None:
            return None
        try:
            return PositionMaterializationAssociationStatus(str(row.association_status))
        except ValueError as exc:
            raise RuntimeError("Invalid persisted materialization association status") from exc

    def claim_due_associations(
        self,
        *,
        owner: str,
        now: datetime,
        lease: timedelta,
        batch: int,
        max_attempts: int,
    ) -> list[PositionMaterializationAssociationClaim]:
        if not owner.strip() or batch < 1 or max_attempts < 1 or lease.total_seconds() <= 0:
            raise ValueError("Invalid association claim parameters")
        lease_expires_at = now + lease
        try:
            with self._client.cursor() as cursor:
                cursor.execute(
                    """
                    ;WITH due AS (
                        SELECT TOP (?) id
                        FROM dbo.position_materialization_requests
                            WITH (UPDLOCK, READPAST, ROWLOCK)
                        WHERE association_status = 'PENDING'
                          AND attempt_count < ?
                          AND (next_retry_at IS NULL OR next_retry_at <= ?)
                          AND (lease_owner IS NULL OR lease_expires_at <= ?)
                        ORDER BY COALESCE(next_retry_at, created_at), created_at, id
                    )
                    UPDATE requests
                    SET lease_owner = ?, lease_expires_at = ?
                    OUTPUT inserted.id, inserted.attempt_count, inserted.lease_expires_at
                    FROM dbo.position_materialization_requests AS requests
                    INNER JOIN due ON due.id = requests.id
                    """,
                    (batch, max_attempts, now, now, owner, lease_expires_at),
                )
                rows = cursor.fetchall()
        except pyodbc.ProgrammingError:
            raise
        except (pyodbc.DatabaseError, pyodbc.InterfaceError) as exc:  # type: ignore[attr-defined]
            self._raise_classified_sql_failure(exc)
        return [
            PositionMaterializationAssociationClaim(
                request_id=str(row.id),
                owner=owner,
                attempt_count=int(row.attempt_count),
                lease_expires_at=row.lease_expires_at,
            )
            for row in rows
        ]

    def inspect_association_evidence(
        self, request_id: str
    ) -> PositionMaterializationAssociationEvidence:
        try:
            with self._client.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        (SELECT COUNT_BIG(*) FROM
                            dbo.position_materialization_association_receipts
                         WHERE request_id = ? AND target_type = 'IMAGE_RESULT') AS receipt_count,
                        (SELECT COUNT_BIG(*) FROM dbo.mobile_preliminary_detections
                         WHERE position_materialization_request_id = ?) AS preliminary_count,
                        (SELECT MIN(target_id) FROM
                            dbo.position_materialization_association_receipts
                         WHERE request_id = ? AND target_type = 'IMAGE_RESULT') AS target_id
                    """,
                    (request_id, request_id, request_id),
                )
                row = cursor.fetchone()
        except pyodbc.ProgrammingError:
            raise
        except (pyodbc.DatabaseError, pyodbc.InterfaceError) as exc:  # type: ignore[attr-defined]
            self._raise_classified_sql_failure(exc)
        receipt_count = int(row.receipt_count or 0)
        preliminary_count = int(row.preliminary_count or 0)
        if receipt_count > 1:
            return PositionMaterializationAssociationEvidence(
                status=PositionMaterializationEvidenceStatus.CONTRADICTION,
                source="IMAGE_RESULT",
            )
        if receipt_count == 1:
            return PositionMaterializationAssociationEvidence(
                status=PositionMaterializationEvidenceStatus.PRESENT,
                source="IMAGE_RESULT",
                target_id=str(row.target_id),
            )
        if preliminary_count:
            return PositionMaterializationAssociationEvidence(
                status=PositionMaterializationEvidenceStatus.PRESENT,
                source="MOBILE_PRELIMINARY_DETECTION",
            )
        return PositionMaterializationAssociationEvidence(
            status=PositionMaterializationEvidenceStatus.ABSENT
        )

    def complete_claimed(self, *, request_id: str, owner: str, now: datetime) -> bool:
        return self._finish_claimed(
            request_id=request_id,
            owner=owner,
            status=PositionMaterializationAssociationStatus.ASSOCIATED,
            now=now,
            next_retry_at=None,
            error_code=None,
        )

    def reschedule_claimed(
        self,
        *,
        request_id: str,
        owner: str,
        now: datetime,
        next_retry_at: datetime,
        error_code: str,
    ) -> bool:
        return self._finish_claimed(
            request_id=request_id,
            owner=owner,
            status=PositionMaterializationAssociationStatus.PENDING,
            now=now,
            next_retry_at=next_retry_at,
            error_code=error_code,
        )

    def exhaust_claimed(
        self, *, request_id: str, owner: str, now: datetime, error_code: str
    ) -> bool:
        return self._finish_claimed(
            request_id=request_id,
            owner=owner,
            status=PositionMaterializationAssociationStatus.EXHAUSTED,
            now=now,
            next_retry_at=None,
            error_code=error_code,
        )

    def _finish_claimed(
        self,
        *,
        request_id: str,
        owner: str,
        status: PositionMaterializationAssociationStatus,
        now: datetime,
        next_retry_at: datetime | None,
        error_code: str | None,
    ) -> bool:
        associated_at = (
            now if status is PositionMaterializationAssociationStatus.ASSOCIATED else None
        )
        try:
            with self._client.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE dbo.position_materialization_requests
                    SET association_status = ?, associated_at = ?,
                        association_error_code = ?, attempt_count = attempt_count + 1,
                        last_attempt_at = ?, next_retry_at = ?,
                        lease_owner = NULL, lease_expires_at = NULL
                    WHERE id = ? AND association_status = 'PENDING'
                      AND lease_owner = ? AND lease_expires_at > ?
                    """,
                    (
                        status.value,
                        associated_at,
                        error_code,
                        now,
                        next_retry_at,
                        request_id,
                        owner,
                        now,
                    ),
                )
                return int(cursor.rowcount or 0) == 1
        except pyodbc.ProgrammingError:
            raise
        except (pyodbc.DatabaseError, pyodbc.InterfaceError) as exc:  # type: ignore[attr-defined]
            self._raise_classified_sql_failure(exc)

    def release_expired_associations(self, *, now: datetime) -> int:
        try:
            with self._client.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE dbo.position_materialization_requests
                    SET lease_owner = NULL, lease_expires_at = NULL
                    WHERE association_status = 'PENDING'
                      AND lease_owner IS NOT NULL AND lease_expires_at <= ?
                    """,
                    (now,),
                )
                return int(cursor.rowcount or 0)
        except pyodbc.ProgrammingError:
            raise
        except (pyodbc.DatabaseError, pyodbc.InterfaceError) as exc:  # type: ignore[attr-defined]
            self._raise_classified_sql_failure(exc)

    @staticmethod
    def _rollback_active(txn: SqlServerTransaction) -> None:
        if txn.state == TransactionState.ACTIVE:
            txn.rollback()

    @staticmethod
    def _raise_classified_sql_failure(exc: BaseException) -> NoReturn:
        classification = classify_sql_failure(exc)
        if classification.kind is SqlFailureKind.IDENTITY_CONFLICT:
            raise PositionMaterializationConflictError(
                "Canonical position identity already exists",
                code="POSITION_IDENTITY_CONFLICT",
            ) from exc
        if classification.kind is SqlFailureKind.IDEMPOTENCY_CONFLICT:
            raise PositionMaterializationConflictError(
                "Materialization idempotency key already exists",
                code="IDEMPOTENCY_KEY_CONFLICT",
            ) from exc
        if classification.kind is SqlFailureKind.RETRYABLE:
            raise PositionMaterializationRetryableError(
                "Position materialization database operation is retryable",
                code="MATERIALIZATION_DATABASE_RETRYABLE",
            ) from exc
        raise PositionMaterializationInvariantError(
            "Position materialization persistence invariant failed",
            code="MATERIALIZATION_PERSISTENCE_INVARIANT",
        ) from exc

    @staticmethod
    def _read_replay(
        cursor: pyodbc.Cursor,
        client_id: str,
        idempotency_key: str,
    ) -> _ReplayRow | None:
        cursor.execute(
            """
            SELECT r.id, r.request_hash, r.fingerprint_version, r.result,
                   r.location_id, l.public_identifier
            FROM dbo.position_materialization_requests AS r WITH (UPDLOCK, HOLDLOCK)
            INNER JOIN dbo.aisle_locations AS l ON l.id = r.location_id
            WHERE r.client_id = ? AND r.idempotency_key = ?
            """,
            (client_id, idempotency_key),
        )
        return cast(_ReplayRow | None, cursor.fetchone())

    @staticmethod
    def _resolve_replay(
        row: _ReplayRow,
        request_hash: str,
    ) -> MaterializePositionResult:
        fingerprint_version = int(row.fingerprint_version)
        if fingerprint_version != POSITION_MATERIALIZATION_FINGERPRINT_VERSION:
            raise PositionMaterializationInvariantError(
                "Stored materialization fingerprint version is unsupported",
                code="UNSUPPORTED_MATERIALIZATION_FINGERPRINT_VERSION",
            )
        if str(row.request_hash).lower() != request_hash.lower():
            raise _conflict(
                "Idempotency key was used with a different payload",
                "IDEMPOTENCY_KEY_CONFLICT",
            )
        try:
            status = PositionMaterializationStatus(str(row.result))
        except ValueError as exc:
            raise RuntimeError("Invalid persisted materialization result") from exc
        return MaterializePositionResult(
            status=status,
            idempotent_replay=True,
            location_id=str(row.location_id),
            public_identifier=str(row.public_identifier),
            request_id=str(row.id),
        )

    @staticmethod
    def _read_inventory(cursor: pyodbc.Cursor, inventory_id: str) -> _InventoryRow | None:
        cursor.execute(
            """
            SELECT id, client_id, status, deleted_at
            FROM dbo.inventories WITH (HOLDLOCK)
            WHERE id = ?
            """,
            (inventory_id,),
        )
        return cast(_InventoryRow | None, cursor.fetchone())

    @staticmethod
    def _read_aisle(cursor: pyodbc.Cursor, aisle_id: str) -> _AisleRow | None:
        cursor.execute(
            """
            SELECT id, inventory_id, is_active, client_supplier_id
            FROM dbo.aisles WITH (HOLDLOCK)
            WHERE id = ?
            """,
            (aisle_id,),
        )
        return cast(_AisleRow | None, cursor.fetchone())

    @staticmethod
    def _validate_profile_scope(
        cursor: pyodbc.Cursor,
        command: MaterializePositionCommand,
        client_id: str,
    ) -> None:
        recognition = command.recognition
        if recognition.client_supplier_id is None:
            if recognition.profile_id is not None or recognition.profile_version is not None:
                raise _scope_error(
                    "A supplier-less recognition cannot reference a profile",
                    "PROFILE_SCOPE_MISMATCH",
                )
            return
        if recognition.profile_id is None:
            if recognition.profile_version is not None:
                raise _scope_error(
                    "Profile version requires a profile identifier",
                    "PROFILE_SCOPE_MISMATCH",
                )
            return
        if recognition.profile_version is None:
            raise _scope_error(
                "Profile identifier requires an exact profile version",
                "PROFILE_SCOPE_MISMATCH",
            )
        cursor.execute(
            """
            SELECT id
            FROM dbo.supplier_extraction_profiles WITH (HOLDLOCK)
            WHERE id = ? AND client_id = ? AND supplier_id = ? AND version = ?
            """,
            (
                recognition.profile_id,
                client_id,
                recognition.client_supplier_id,
                recognition.profile_version,
            ),
        )
        if cursor.fetchone() is None:
            raise _scope_error(
                "Recognition profile is outside the client/supplier/version scope",
                "PROFILE_SCOPE_MISMATCH",
            )

    def _acquire_identity_lock(
        self,
        cursor: pyodbc.Cursor,
        command: MaterializePositionCommand,
        client_id: str,
    ) -> None:
        resource = _application_lock_resource(
            client_id,
            command.aisle_id,
            command.recognition.normalized_code,
        )
        cursor.execute(
            """
            DECLARE @lock_result INT;
            EXEC @lock_result = sys.sp_getapplock
                @Resource = ?,
                @LockMode = 'Exclusive',
                @LockOwner = 'Transaction',
                @LockTimeout = ?;
            SELECT @lock_result AS lock_result;
            """,
            (resource, self._lock_timeout_ms),
        )
        row = cursor.fetchone()
        if row is None:
            raise PositionMaterializationInvariantError(
                "Application lock returned no result",
                code="MATERIALIZATION_LOCK_INVARIANT",
            )
        lock_result = int(row.lock_result)
        if lock_result in {-1, -2, -3}:
            raise PositionMaterializationRetryableError(
                "Canonical position identity lock was unavailable",
                code="MATERIALIZATION_LOCK_UNAVAILABLE",
            )
        if lock_result == -999 or lock_result < 0:
            raise PositionMaterializationInvariantError(
                "Application lock invocation failed",
                code="MATERIALIZATION_LOCK_INVARIANT",
            )

    @staticmethod
    def _read_identity_locations(
        cursor: pyodbc.Cursor,
        command: MaterializePositionCommand,
        client_id: str,
    ) -> _IdentityLocationRow | None:
        cursor.execute(
            """
            SELECT id, public_identifier, status, client_supplier_id, profile_id,
                   profile_version, pallet, side, level, marker_index, marker_total
            FROM dbo.aisle_locations WITH (UPDLOCK, HOLDLOCK)
            WHERE client_id = ? AND aisle_id = ? AND normalized_code = ?
            ORDER BY CASE WHEN status = 'ACTIVE' THEN 0 ELSE 1 END, created_at
            """,
            (client_id, command.aisle_id, command.recognition.normalized_code),
        )
        rows = cursor.fetchall()
        active = next((row for row in rows if str(row.status) == "ACTIVE"), None)
        return cast(_IdentityLocationRow | None, active or (rows[0] if rows else None))

    @staticmethod
    def _validate_compatible(
        location: _IdentityLocationRow,
        command: MaterializePositionCommand,
    ) -> None:
        recognition = command.recognition
        fields = (
            ("client_supplier_id", location.client_supplier_id, recognition.client_supplier_id),
            ("profile_id", location.profile_id, recognition.profile_id),
            ("profile_version", location.profile_version, recognition.profile_version),
            ("pallet", location.pallet, recognition.pallet),
            ("side", location.side, recognition.side),
            ("level", location.level, recognition.level),
            ("marker_index", location.marker_index, recognition.marker_index),
            ("marker_total", location.marker_total, recognition.marker_total),
        )
        for field, persisted, requested in fields:
            if persisted is not None and requested is not None and persisted != requested:
                raise _conflict(
                    f"Existing location has contradictory {field}",
                    f"POSITION_{field.upper()}_CONFLICT",
                )

    @staticmethod
    def _insert_request(
        cursor: pyodbc.Cursor,
        *,
        request_id: str,
        command: MaterializePositionCommand,
        client_id: str,
        location_id: str,
        request_hash: str,
        result_status: PositionMaterializationStatus,
        now: datetime,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO dbo.position_materialization_requests (
                id, client_id, inventory_id, aisle_id, location_id,
                idempotency_key, request_hash, fingerprint_version,
                normalized_code, source, actor, result, created_at, association_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
            """,
            (
                request_id,
                client_id,
                command.inventory_id,
                command.aisle_id,
                location_id,
                command.idempotency_key,
                request_hash,
                POSITION_MATERIALIZATION_FINGERPRINT_VERSION,
                command.recognition.normalized_code,
                command.recognition.source.value,
                command.principal.actor_id,
                result_status.value,
                now,
            ),
        )

    @staticmethod
    def _insert_location(
        cursor: pyodbc.Cursor,
        command: MaterializePositionCommand,
        client_id: str,
        now: datetime,
    ) -> tuple[str, str]:
        location_id = str(uuid.uuid4())
        public_identifier = f"loc_{location_id.replace('-', '')}"
        recognition = command.recognition
        cursor.execute(
            """
            INSERT INTO dbo.aisle_locations (
                id, public_identifier, client_id, aisle_id, code, normalized_code,
                display_name, description, status, created_by, created_at, updated_at,
                creation_source, recognition_source, client_supplier_id, profile_id,
                profile_version, raw_recognition_code, pallet, side, level,
                marker_index, marker_total, source_capture_id, auto_materialized_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, NULL, NULL, 'ACTIVE', ?, ?, ?,
                'AUTO', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                location_id,
                public_identifier,
                client_id,
                command.aisle_id,
                recognition.normalized_code,
                recognition.normalized_code,
                command.principal.actor_id,
                now,
                now,
                recognition.source.value,
                recognition.client_supplier_id,
                recognition.profile_id,
                recognition.profile_version,
                recognition.raw_code,
                recognition.pallet,
                recognition.side,
                recognition.level,
                recognition.marker_index,
                recognition.marker_total,
                command.capture_id,
                now,
            ),
        )
        return location_id, public_identifier
