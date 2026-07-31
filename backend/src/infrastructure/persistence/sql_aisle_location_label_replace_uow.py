"""Transactional replace for aisle location labels (Phase 2 hardening)."""

from __future__ import annotations

import json
import logging
from datetime import datetime

import pyodbc

from src.application.errors import (
    AisleLocationLabelConflictError,
    AisleLocationLabelNotFoundError,
    IdempotencyKeyReusedError,
)
from src.application.ports.aisle_location_repository import (
    AisleLocationLabelReplaceUnitOfWork,
)
from src.database.sqlserver import SqlServerClient
from src.domain.aisle_location.label_entities import (
    AisleLocationLabel,
    AisleLocationLabelStatus,
    PositioningLabelSignatureStatus,
)
from src.infrastructure.database.sql_transaction import TransactionState
from src.infrastructure.repositories.db_row_text import normalize_db_str, optional_nonempty_db_str
from src.infrastructure.repositories.memory_aisle_location_repository import (
    MemoryAisleLocationLabelRepository,
)
from src.infrastructure.repositories.sql_aisle_location_repository import (
    _ensure_utc,
    _is_label_client_idempotency_unique_violation,
    _parse_payload,
)

logger = logging.getLogger(__name__)

_REPLACE_OP_PREFIX = "REPLACE_AISLE_LOCATION_LABEL"


def _row_to_label_locked(row) -> AisleLocationLabel:
    status_raw = normalize_db_str(getattr(row, "status", None)) or "ACTIVE"
    try:
        status = AisleLocationLabelStatus(status_raw)
    except ValueError:
        status = AisleLocationLabelStatus.ACTIVE
    sig_raw = normalize_db_str(getattr(row, "signature_status", None)) or "NOT_IMPLEMENTED"
    try:
        signature_status = PositioningLabelSignatureStatus(sig_raw)
    except ValueError:
        signature_status = PositioningLabelSignatureStatus.NOT_IMPLEMENTED
    generated = _ensure_utc(getattr(row, "generated_at", None))
    if generated is None:
        raise ValueError("aisle_location_labels row missing generated_at")
    return AisleLocationLabel(
        id=normalize_db_str(getattr(row, "id", None)),
        client_id=normalize_db_str(getattr(row, "client_id", None)),
        location_id=normalize_db_str(getattr(row, "location_id", None)),
        public_identifier=normalize_db_str(getattr(row, "public_identifier", None)),
        payload_version=int(getattr(row, "payload_version", 1) or 1),
        marker_version=int(getattr(row, "marker_version", 1) or 1),
        template_version=int(getattr(row, "template_version", 1) or 1),
        status=status,
        payload=_parse_payload(getattr(row, "payload_json", None)),
        generated_at=generated,
        payload_hash=optional_nonempty_db_str(getattr(row, "payload_hash", None)),
        signature_status=signature_status,
        generated_by=optional_nonempty_db_str(getattr(row, "generated_by", None)),
        invalidated_at=_ensure_utc(getattr(row, "invalidated_at", None)),
        invalidation_reason=optional_nonempty_db_str(getattr(row, "invalidation_reason", None)),
        replaced_by_label_id=optional_nonempty_db_str(
            getattr(row, "replaced_by_label_id", None)
        ),
        replaced_at=_ensure_utc(getattr(row, "replaced_at", None)),
        idempotency_key=optional_nonempty_db_str(getattr(row, "idempotency_key", None)),
        idempotency_request_hash=optional_nonempty_db_str(
            getattr(row, "idempotency_request_hash", None)
        ),
    )


class MemoryAisleLocationLabelReplaceUnitOfWork(AisleLocationLabelReplaceUnitOfWork):
    def __init__(self, label_repo: MemoryAisleLocationLabelRepository) -> None:
        self._labels = label_repo

    def replace_atomically(
        self,
        *,
        old_label_id: str,
        new_label: AisleLocationLabel,
        now: datetime,
        request_hash: str | None,
        idempotency_key: str | None,
    ) -> AisleLocationLabel:
        old = self._labels.get_by_id(old_label_id)
        if old is None:
            raise AisleLocationLabelNotFoundError(old_label_id)
        if old.status == AisleLocationLabelStatus.INVALIDATED:
            raise AisleLocationLabelConflictError(
                "Cannot replace an invalidated label",
                code="AISLE_LOCATION_LABEL_INVALIDATED",
            )
        if old.status == AisleLocationLabelStatus.REPLACED and old.replaced_by_label_id:
            existing = self._labels.get_by_id(old.replaced_by_label_id)
            if existing is not None:
                return existing
        if idempotency_key:
            prior = self._labels.get_by_client_idempotency_key(
                new_label.client_id, idempotency_key
            )
            if prior is not None:
                if (prior.idempotency_request_hash or "") == (request_hash or ""):
                    if old.status != AisleLocationLabelStatus.REPLACED:
                        old.status = AisleLocationLabelStatus.REPLACED
                        old.replaced_by_label_id = prior.id
                        old.replaced_at = now
                        self._labels.save(old)
                    return prior
                raise IdempotencyKeyReusedError(
                    "IDEMPOTENCY_KEY_REUSED: same key with a different replace fingerprint"
                )
        self._labels.save(new_label)
        old.status = AisleLocationLabelStatus.REPLACED
        old.replaced_by_label_id = new_label.id
        old.replaced_at = now
        self._labels.save(old)
        logger.info(
            "position_label_replaced old_label_id=%s new_label_id=%s",
            old.id,
            new_label.id,
        )
        return new_label


class SqlAisleLocationLabelReplaceUnitOfWork(AisleLocationLabelReplaceUnitOfWork):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def replace_atomically(
        self,
        *,
        old_label_id: str,
        new_label: AisleLocationLabel,
        now: datetime,
        request_hash: str | None,
        idempotency_key: str | None,
    ) -> AisleLocationLabel:
        txn = self._client.begin_transaction()
        txn.__enter__()
        try:
            cur = txn.connection.cursor()
            cur.execute(
                """
                SELECT id, client_id, location_id, public_identifier, payload_version,
                       marker_version, template_version, status, payload_json, payload_hash,
                       signature_status, generated_by, generated_at, invalidated_at,
                       invalidation_reason, replaced_by_label_id, replaced_at,
                       idempotency_key, idempotency_request_hash
                FROM aisle_location_labels WITH (UPDLOCK, ROWLOCK)
                WHERE id = ?
                """,
                (old_label_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise AisleLocationLabelNotFoundError(old_label_id)
            old = _row_to_label_locked(row)
            if old.status == AisleLocationLabelStatus.INVALIDATED:
                raise AisleLocationLabelConflictError(
                    "Cannot replace an invalidated label",
                    code="AISLE_LOCATION_LABEL_INVALIDATED",
                )
            if old.status == AisleLocationLabelStatus.REPLACED and old.replaced_by_label_id:
                cur.execute(
                    """
                    SELECT id, client_id, location_id, public_identifier, payload_version,
                           marker_version, template_version, status, payload_json, payload_hash,
                           signature_status, generated_by, generated_at, invalidated_at,
                           invalidation_reason, replaced_by_label_id, replaced_at,
                           idempotency_key, idempotency_request_hash
                    FROM aisle_location_labels WHERE id = ?
                    """,
                    (old.replaced_by_label_id,),
                )
                repl_row = cur.fetchone()
                if repl_row is not None:
                    txn.commit()
                    return _row_to_label_locked(repl_row)

            if idempotency_key:
                cur.execute(
                    """
                    SELECT id, client_id, location_id, public_identifier, payload_version,
                           marker_version, template_version, status, payload_json, payload_hash,
                           signature_status, generated_by, generated_at, invalidated_at,
                           invalidation_reason, replaced_by_label_id, replaced_at,
                           idempotency_key, idempotency_request_hash
                    FROM aisle_location_labels
                    WHERE client_id = ? AND idempotency_key = ?
                    """,
                    (new_label.client_id, idempotency_key),
                )
                prior_row = cur.fetchone()
                if prior_row is not None:
                    prior = _row_to_label_locked(prior_row)
                    if (prior.idempotency_request_hash or "") != (request_hash or ""):
                        raise IdempotencyKeyReusedError(
                            "IDEMPOTENCY_KEY_REUSED: same key with a different replace fingerprint"
                        )
                    if old.status != AisleLocationLabelStatus.REPLACED:
                        cur.execute(
                            """
                            UPDATE aisle_location_labels
                            SET status = ?, replaced_by_label_id = ?, replaced_at = ?
                            WHERE id = ?
                            """,
                            (
                                AisleLocationLabelStatus.REPLACED.value,
                                prior.id,
                                _ensure_utc(now),
                                old.id,
                            ),
                        )
                    txn.commit()
                    return prior

            payload_str = json.dumps(new_label.payload, ensure_ascii=False, sort_keys=True)
            try:
                cur.execute(
                    """
                    INSERT INTO aisle_location_labels (
                        id, client_id, location_id, public_identifier, payload_version,
                        marker_version, template_version, status, payload_json, payload_hash,
                        signature_status, generated_by, generated_at, invalidated_at,
                        invalidation_reason, replaced_by_label_id, replaced_at,
                        idempotency_key, idempotency_request_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        new_label.id,
                        new_label.client_id,
                        new_label.location_id,
                        new_label.public_identifier,
                        new_label.payload_version,
                        new_label.marker_version,
                        new_label.template_version,
                        new_label.status.value,
                        payload_str,
                        new_label.payload_hash,
                        new_label.signature_status.value,
                        new_label.generated_by,
                        _ensure_utc(new_label.generated_at),
                        None,
                        None,
                        None,
                        None,
                        new_label.idempotency_key,
                        new_label.idempotency_request_hash,
                    ),
                )
            except pyodbc.IntegrityError as exc:
                if _is_label_client_idempotency_unique_violation(exc):
                    raise IdempotencyKeyReusedError(
                        "IDEMPOTENCY_KEY_REUSED: key already registered"
                    ) from exc
                raise

            cur.execute(
                """
                UPDATE aisle_location_labels
                SET status = ?, replaced_by_label_id = ?, replaced_at = ?
                WHERE id = ?
                """,
                (
                    AisleLocationLabelStatus.REPLACED.value,
                    new_label.id,
                    _ensure_utc(now),
                    old.id,
                ),
            )
            txn.commit()
            logger.info(
                "position_label_replaced old_label_id=%s new_label_id=%s",
                old.id,
                new_label.id,
            )
            return new_label
        except Exception:
            if txn.state == TransactionState.ACTIVE:
                txn.rollback()
            raise
        finally:
            txn.close()
