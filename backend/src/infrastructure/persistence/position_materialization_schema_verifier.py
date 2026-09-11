"""Fail-closed SQL schema precondition for position materialization."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

import pyodbc

from src.database.sqlserver import SqlServerClient
from src.infrastructure.database.position_materialization_sql_errors import (
    ACTIVE_IDENTITY_INDEX,
    LEDGER_IDEMPOTENCY_INDEX,
)
from src.infrastructure.database.sql_transaction import TransactionState

SCHEMA_PRECONDITION_ERROR = "POSITION_MATERIALIZATION_SCHEMA_PRECONDITION_FAILED"


class PositionMaterializationSchemaError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(SCHEMA_PRECONDITION_ERROR)


@dataclass(frozen=True)
class _ExpectedIndex:
    table_name: str
    index_name: str
    keys: str
    included: str | None
    unique: bool
    filter_definition: str | None


@dataclass(frozen=True)
class _ExpectedCheck:
    table_name: str
    constraint_name: str
    definitions: tuple[str, ...]


class _IndexRow(Protocol):
    is_unique: object
    is_disabled: object
    type_desc: object
    has_filter: object
    filter_definition: str | None
    key_columns: object
    included_columns: object | None


class _CheckRow(Protocol):
    definition: str | None
    is_disabled: object
    is_not_trusted: object


class _FingerprintColumnRow(Protocol):
    type_name: object
    max_length: int
    is_nullable: object
    default_name: object
    default_definition: str | None


_EXPECTED = (
    _ExpectedIndex(
        "aisle_locations",
        ACTIVE_IDENTITY_INDEX,
        "client_id,aisle_id,normalized_code",
        None,
        True,
        "status='ACTIVE'",
    ),
    _ExpectedIndex(
        "position_materialization_requests",
        LEDGER_IDEMPOTENCY_INDEX,
        "client_id,idempotency_key",
        None,
        True,
        None,
    ),
    _ExpectedIndex(
        "position_materialization_requests",
        "IX_pmr_association_due",
        "association_status,next_retry_at,lease_expires_at,attempt_count,created_at",
        "lease_owner",
        False,
        None,
    ),
)

_EXPECTED_CHECKS = (
    _ExpectedCheck(
        "product_position_assignments",
        "CK_ppa_automatic_evidence",
        (
            """
            assignment_status <> 'ASSIGNED_AUTOMATIC'
            OR (
                source_detection_id IS NOT NULL
                AND (position_label_id IS NOT NULL OR aisle_location_id IS NOT NULL)
            )
            """,
        ),
    ),
    _ExpectedCheck(
        "product_position_assignments",
        "CK_ppa_unassigned_position_null",
        (
            """
            assignment_status = 'ASSIGNED_AUTOMATIC'
            OR (position_label_id IS NULL AND aisle_location_id IS NULL)
            """,
        ),
    ),
    _ExpectedCheck(
        "position_materialization_requests",
        "CK_pmr_fingerprint_version",
        ("fingerprint_version = 1",),
    ),
    _ExpectedCheck(
        "position_materialization_requests",
        "CK_pmr_attempt_count",
        ("attempt_count >= 0",),
    ),
    _ExpectedCheck(
        "position_materialization_requests",
        "CK_pmr_lease_pair",
        (
            """
            (lease_owner IS NULL AND lease_expires_at IS NULL)
            OR (lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)
            """,
        ),
    ),
    _ExpectedCheck(
        "position_materialization_requests",
        "CK_pmr_association_state",
        (
            """
            (association_status = 'PENDING' AND associated_at IS NULL
                AND (association_error_code IS NULL
                     OR LEN(association_error_code) BETWEEN 1 AND 64))
            OR (association_status = 'ASSOCIATED' AND associated_at IS NOT NULL
                AND association_error_code IS NULL)
            OR (association_status IN ('REQUIRES_REVIEW', 'EXHAUSTED')
                AND associated_at IS NULL
                AND LEN(association_error_code) BETWEEN 1 AND 64)
            """,
            """
            (association_status = 'PENDING' AND associated_at IS NULL
                AND (association_error_code IS NULL
                     OR LEN(association_error_code) BETWEEN 1 AND 64))
            OR (association_status = 'ASSOCIATED' AND associated_at IS NOT NULL
                AND association_error_code IS NULL)
            OR ((association_status = 'REQUIRES_REVIEW'
                 OR association_status = 'EXHAUSTED')
                AND associated_at IS NULL
                AND LEN(association_error_code) BETWEEN 1 AND 64)
            """,
            """
            (association_status = 'PENDING' AND associated_at IS NULL
                AND (association_error_code IS NULL
                     OR LEN(association_error_code) BETWEEN 1 AND 64))
            OR (association_status = 'ASSOCIATED' AND associated_at IS NOT NULL
                AND association_error_code IS NULL)
            OR (association_status = 'REQUIRES_REVIEW'
                AND associated_at IS NULL
                AND LEN(association_error_code) BETWEEN 1 AND 64)
            OR (association_status = 'EXHAUSTED'
                AND associated_at IS NULL
                AND LEN(association_error_code) BETWEEN 1 AND 64)
            """,
            """
            (association_status = 'PENDING' AND associated_at IS NULL
                AND (association_error_code IS NULL
                     OR (LEN(association_error_code) >= 1
                         AND LEN(association_error_code) <= 64)))
            OR (association_status = 'ASSOCIATED' AND associated_at IS NOT NULL
                AND association_error_code IS NULL)
            OR ((association_status = 'EXHAUSTED'
                 OR association_status = 'REQUIRES_REVIEW')
                AND associated_at IS NULL
                AND (LEN(association_error_code) >= 1
                     AND LEN(association_error_code) <= 64))
            """,
        ),
    ),
    _ExpectedCheck(
        "position_materialization_association_receipts",
        "CK_pmar_target_type",
        ("target_type = 'IMAGE_RESULT'",),
    ),
    _ExpectedCheck(
        "position_materialization_association_receipts",
        "CK_pmar_target_id",
        (
            "LEN(target_id) BETWEEN 1 AND 36",
            "LEN(target_id) >= 1 AND LEN(target_id) <= 36",
        ),
    ),
)


def _canonical_filter(value: str | None) -> str | None:
    if value is None:
        return None
    canonical = re.sub(r"[\s\[\]\(\)]", "", value).upper()
    canonical = re.sub(r"(?<![A-Z0-9_])N'", "'", canonical)
    return canonical


class SqlPositionMaterializationSchemaVerifier:
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def verify(self) -> None:
        txn = None
        try:
            txn = self._client.begin_transaction()
            txn.__enter__()
            cursor = txn.connection.cursor()
            for expected in _EXPECTED:
                cursor.execute(
                    """
                        SELECT i.is_unique, i.is_disabled, i.type_desc,
                               i.has_filter, i.filter_definition,
                               STRING_AGG(
                                   CASE WHEN ic.key_ordinal > 0 THEN c.name END, ','
                               ) WITHIN GROUP (ORDER BY ic.index_column_id) AS key_columns,
                               STRING_AGG(
                                   CASE WHEN ic.is_included_column = 1 THEN c.name END, ','
                               ) WITHIN GROUP (ORDER BY ic.index_column_id) AS included_columns
                        FROM sys.indexes AS i
                        INNER JOIN sys.index_columns AS ic
                            ON ic.object_id = i.object_id
                           AND ic.index_id = i.index_id
                        INNER JOIN sys.columns AS c
                            ON c.object_id = ic.object_id
                           AND c.column_id = ic.column_id
                        WHERE i.object_id = OBJECT_ID(?)
                          AND i.name = ?
                        GROUP BY i.is_unique, i.is_disabled, i.type_desc,
                                 i.has_filter, i.filter_definition
                        """,
                    (f"dbo.{expected.table_name}", expected.index_name),
                )
                row = cursor.fetchone()
                if not self._matches(row, expected):
                    raise PositionMaterializationSchemaError
            for expected_check in _EXPECTED_CHECKS:
                cursor.execute(
                    """
                    SELECT definition, is_disabled, is_not_trusted
                    FROM sys.check_constraints
                    WHERE parent_object_id = OBJECT_ID(?)
                      AND name = ?
                    """,
                    (
                        f"dbo.{expected_check.table_name}",
                        expected_check.constraint_name,
                    ),
                )
                if not self._matches_check(cursor.fetchone(), expected_check):
                    raise PositionMaterializationSchemaError
            cursor.execute(
                """
                SELECT t.name AS type_name, c.max_length, c.is_nullable,
                       dc.name AS default_name, dc.definition AS default_definition
                FROM sys.columns AS c
                INNER JOIN sys.types AS t ON t.user_type_id = c.user_type_id
                LEFT JOIN sys.default_constraints AS dc
                    ON dc.parent_object_id = c.object_id
                   AND dc.parent_column_id = c.column_id
                WHERE c.object_id = OBJECT_ID(
                    N'dbo.position_materialization_requests'
                )
                  AND c.name = N'fingerprint_version'
                """
            )
            fingerprint_column = cursor.fetchone()
            if not self._matches_fingerprint_column(fingerprint_column):
                raise PositionMaterializationSchemaError
            cursor.execute(
                """
                    SELECT
                        CASE WHEN COL_LENGTH(N'dbo.position_materialization_requests',
                            N'attempt_count') IS NOT NULL
                            AND COL_LENGTH(N'dbo.position_materialization_requests',
                            N'last_attempt_at') IS NOT NULL
                            AND COL_LENGTH(N'dbo.position_materialization_requests',
                            N'next_retry_at') IS NOT NULL
                            AND COL_LENGTH(N'dbo.position_materialization_requests',
                            N'lease_owner') IS NOT NULL
                            AND COL_LENGTH(N'dbo.position_materialization_requests',
                            N'lease_expires_at') IS NOT NULL
                            THEN 1 ELSE 0 END AS ledger_columns_valid,
                        CASE WHEN OBJECT_ID(
                            N'dbo.position_materialization_association_receipts', N'U'
                        ) IS NOT NULL
                            AND COL_LENGTH(
                                N'dbo.position_materialization_association_receipts',
                                N'request_id') IS NOT NULL
                            AND COL_LENGTH(
                                N'dbo.position_materialization_association_receipts',
                                N'target_type') IS NOT NULL
                            AND COL_LENGTH(
                                N'dbo.position_materialization_association_receipts',
                                N'target_id') IS NOT NULL
                            AND COL_LENGTH(
                                N'dbo.position_materialization_association_receipts',
                                N'created_at') IS NOT NULL
                            THEN 1 ELSE 0 END AS receipt_schema_valid,
                        CASE WHEN EXISTS (
                            SELECT 1
                            FROM sys.foreign_keys AS fk
                            INNER JOIN sys.foreign_key_columns AS fkc
                                ON fkc.constraint_object_id = fk.object_id
                            INNER JOIN sys.columns AS parent_column
                                ON parent_column.object_id = fkc.parent_object_id
                               AND parent_column.column_id = fkc.parent_column_id
                            INNER JOIN sys.columns AS referenced_column
                                ON referenced_column.object_id = fkc.referenced_object_id
                               AND referenced_column.column_id = fkc.referenced_column_id
                            WHERE fk.parent_object_id = OBJECT_ID(
                                N'dbo.position_materialization_association_receipts')
                              AND fk.name = N'FK_pmar_request'
                              AND fk.referenced_object_id = OBJECT_ID(
                                N'dbo.position_materialization_requests')
                              AND parent_column.name = N'request_id'
                              AND referenced_column.name = N'id'
                              AND fk.is_disabled = 0 AND fk.is_not_trusted = 0
                        ) THEN 1 ELSE 0 END AS receipt_fk_valid,
                        CASE WHEN EXISTS (
                            SELECT 1
                            FROM sys.key_constraints AS kc
                            INNER JOIN sys.index_columns AS ic
                                ON ic.object_id = kc.parent_object_id
                               AND ic.index_id = kc.unique_index_id
                               AND ic.key_ordinal = 1
                            INNER JOIN sys.columns AS c
                                ON c.object_id = ic.object_id
                               AND c.column_id = ic.column_id
                            WHERE kc.parent_object_id = OBJECT_ID(
                                N'dbo.position_materialization_association_receipts')
                              AND kc.type = N'PK'
                              AND kc.name = N'PK_position_materialization_association_receipts'
                              AND c.name = N'request_id'
                              AND NOT EXISTS (
                                  SELECT 1 FROM sys.index_columns AS extra
                                  WHERE extra.object_id = kc.parent_object_id
                                    AND extra.index_id = kc.unique_index_id
                                    AND extra.key_ordinal > 1
                              )
                        ) THEN 1 ELSE 0 END AS receipt_pk_valid,
                        CASE WHEN EXISTS (
                            SELECT 1 FROM dbo.aisle_locations
                            WHERE status = 'ACTIVE'
                            GROUP BY client_id, aisle_id, normalized_code
                            HAVING COUNT_BIG(*) > 1
                        ) THEN 1 ELSE 0 END AS active_duplicates,
                        CASE WHEN EXISTS (
                            SELECT 1 FROM dbo.position_materialization_requests
                            GROUP BY client_id, idempotency_key
                            HAVING COUNT_BIG(*) > 1
                        ) THEN 1 ELSE 0 END AS ledger_duplicates
                    """
            )
            schema_row = cursor.fetchone()
            if (
                schema_row is None
                or not bool(schema_row.ledger_columns_valid)
                or not bool(schema_row.receipt_schema_valid)
                or not bool(schema_row.receipt_fk_valid)
                or not bool(schema_row.receipt_pk_valid)
                or bool(schema_row.active_duplicates)
                or bool(schema_row.ledger_duplicates)
            ):
                raise PositionMaterializationSchemaError
            txn.commit()
        except PositionMaterializationSchemaError:
            raise
        except (pyodbc.Error, AttributeError, TypeError, ValueError, RuntimeError) as exc:
            raise PositionMaterializationSchemaError from exc
        finally:
            if txn is not None:
                if txn.state == TransactionState.ACTIVE:
                    txn.rollback()
                txn.close()

    @staticmethod
    def _matches(row: _IndexRow | None, expected: _ExpectedIndex) -> bool:
        if row is None:
            return False
        filter_definition = _canonical_filter(row.filter_definition)
        return (
            bool(row.is_unique) == expected.unique
            and not bool(row.is_disabled)
            and str(row.type_desc).upper() == "NONCLUSTERED"
            and str(row.key_columns).lower() == expected.keys
            and (
                (str(row.included_columns).lower() if row.included_columns is not None else None)
                == expected.included
            )
            and bool(row.has_filter) == (expected.filter_definition is not None)
            and filter_definition == _canonical_filter(expected.filter_definition)
        )

    @staticmethod
    def _matches_check(row: _CheckRow | None, expected: _ExpectedCheck) -> bool:
        return (
            row is not None
            and not bool(row.is_disabled)
            and not bool(row.is_not_trusted)
            and _canonical_filter(row.definition)
            in {_canonical_filter(definition) for definition in expected.definitions}
        )

    @staticmethod
    def _matches_fingerprint_column(row: _FingerprintColumnRow | None) -> bool:
        return (
            row is not None
            and str(row.type_name).lower() == "int"
            and int(row.max_length) == 4
            and not bool(row.is_nullable)
            and str(row.default_name) == "DF_pmr_fingerprint_version"
            and _canonical_filter(row.default_definition) == "1"
        )
