from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.infrastructure.database.sql_transaction import TransactionState
from src.infrastructure.persistence.position_materialization_schema_verifier import (
    SCHEMA_PRECONDITION_ERROR,
    PositionMaterializationSchemaError,
    SqlPositionMaterializationSchemaVerifier,
)


class _Cursor:
    def __init__(self, rows: list[object | None]) -> None:
        self._rows = iter(rows)

    def execute(self, *_args: object) -> None:
        return None

    def fetchone(self) -> object | None:
        return next(self._rows)


class _Client:
    def __init__(self, rows: list[object | None]) -> None:
        self._rows = rows

    def begin_transaction(self):
        cursor = _Cursor(self._rows)

        class Transaction:
            connection = SimpleNamespace(cursor=lambda: cursor)
            state = TransactionState.CLOSED

            def __enter__(self):
                self.state = TransactionState.ACTIVE
                return self

            def commit(self) -> None:
                self.state = TransactionState.COMMITTED

            def rollback(self) -> None:
                self.state = TransactionState.ROLLED_BACK

            def close(self) -> None:
                self.state = TransactionState.CLOSED

        return Transaction()


def _index(
    keys: str,
    *,
    unique: bool = True,
    disabled: bool = False,
    filter_definition: str | None = None,
    included_columns: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        is_unique=unique,
        is_disabled=disabled,
        type_desc="NONCLUSTERED",
        has_filter=filter_definition is not None,
        filter_definition=filter_definition,
        key_columns=keys,
        included_columns=included_columns,
    )


def _check(definition: str, *, disabled: bool = False, untrusted: bool = False):
    return SimpleNamespace(
        definition=definition,
        is_disabled=disabled,
        is_not_trusted=untrusted,
    )


def _schema(**overrides: int) -> SimpleNamespace:
    values = {
        "ledger_columns_valid": 1,
        "receipt_schema_valid": 1,
        "receipt_fk_valid": 1,
        "receipt_pk_valid": 1,
        "active_duplicates": 0,
        "ledger_duplicates": 0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _valid_rows() -> list[object]:
    return [
        _index(
            "client_id,aisle_id,normalized_code",
            filter_definition="([status]=N'ACTIVE')",
        ),
        _index("client_id,idempotency_key"),
        _index(
            "association_status,next_retry_at,lease_expires_at,attempt_count,created_at",
            unique=False,
            included_columns="lease_owner",
        ),
        _check(
            "([assignment_status]<>'ASSIGNED_AUTOMATIC' OR "
            "([source_detection_id] IS NOT NULL AND "
            "([position_label_id] IS NOT NULL OR [aisle_location_id] IS NOT NULL)))"
        ),
        _check(
            "([assignment_status]='ASSIGNED_AUTOMATIC' OR "
            "([position_label_id] IS NULL AND [aisle_location_id] IS NULL))"
        ),
        _check("([fingerprint_version]=(1))"),
        _check("([attempt_count]>=(0))"),
        _check(
            "([lease_owner] IS NULL AND [lease_expires_at] IS NULL "
            "OR [lease_owner] IS NOT NULL AND [lease_expires_at] IS NOT NULL)"
        ),
        _check(
            "([association_status]='PENDING' AND [associated_at] IS NULL "
            "AND ([association_error_code] IS NULL "
            "OR len([association_error_code]) BETWEEN (1) AND (64)) "
            "OR [association_status]='ASSOCIATED' AND [associated_at] IS NOT NULL "
            "AND [association_error_code] IS NULL "
            "OR [association_status] IN ('REQUIRES_REVIEW','EXHAUSTED') "
            "AND [associated_at] IS NULL "
            "AND len([association_error_code]) BETWEEN (1) AND (64))"
        ),
        _check("([target_type]='IMAGE_RESULT')"),
        _check("(len([target_id]) BETWEEN (1) AND (36))"),
        SimpleNamespace(
            type_name="int",
            max_length=4,
            is_nullable=0,
            default_name="DF_pmr_fingerprint_version",
            default_definition="((1))",
        ),
        _schema(),
    ]


def test_accepts_exact_enabled_unique_index_contracts() -> None:
    SqlPositionMaterializationSchemaVerifier(_Client(_valid_rows())).verify()  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("index", "legacy_definition"),
    [
        (
            3,
            "([assignment_status]<>'ASSIGNED_AUTOMATIC' OR "
            "([position_label_id] IS NOT NULL AND [source_detection_id] IS NOT NULL))",
        ),
        (
            4,
            "([assignment_status]='ASSIGNED_AUTOMATIC' OR [position_label_id] IS NULL)",
        ),
    ],
)
def test_rejects_legacy_assignment_evidence_constraints(index: int, legacy_definition: str) -> None:
    rows = _valid_rows()
    rows[index] = _check(legacy_definition)
    with pytest.raises(PositionMaterializationSchemaError):
        SqlPositionMaterializationSchemaVerifier(_Client(rows)).verify()  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "mutated",
    [
        [None, *_valid_rows()[1:]],
        [
            _index(
                "client_id,aisle_id,normalized_code",
                unique=False,
                filter_definition="[status]='ACTIVE'",
            ),
            *_valid_rows()[1:],
        ],
        [
            _index(
                "client_id,normalized_code,aisle_id",
                filter_definition="[status]='ACTIVE'",
            ),
            *_valid_rows()[1:],
        ],
        [
            _index(
                "client_id,aisle_id,normalized_code",
                filter_definition="[status]='INACTIVE'",
            ),
            *_valid_rows()[1:],
        ],
        [
            _index(
                "client_id,aisle_id,normalized_code",
                disabled=True,
                filter_definition="[status]='ACTIVE'",
            ),
            *_valid_rows()[1:],
        ],
        [
            *_valid_rows()[:-1],
            _schema(active_duplicates=1),
        ],
        [
            *_valid_rows()[:-1],
            _schema(ledger_columns_valid=0),
        ],
        [*_valid_rows()[:2], None, *_valid_rows()[3:]],
        [
            *_valid_rows()[:2],
            _index(
                "association_status,next_retry_at,attempt_count,lease_expires_at,created_at",
                unique=False,
                included_columns="lease_owner",
            ),
            *_valid_rows()[3:],
        ],
        [
            *_valid_rows()[:-1],
            _schema(receipt_fk_valid=0),
        ],
        [
            *_valid_rows()[:3],
            _check("([fingerprint_version]>(0))"),
            *_valid_rows()[4:],
        ],
        [
            *_valid_rows()[:7],
            _check("([target_type]='IMAGE_RESULT' OR [target_type]='OTHER')"),
            *_valid_rows()[8:],
        ],
        [
            *_valid_rows()[:8],
            _check("(len([target_id])>=(0))", untrusted=True),
            *_valid_rows()[9:],
        ],
        [
            *_valid_rows()[:9],
            SimpleNamespace(
                type_name="smallint",
                max_length=2,
                is_nullable=0,
                default_name="DF_pmr_fingerprint_version",
                default_definition="((1))",
            ),
            _valid_rows()[-1],
        ],
    ],
)
def test_fails_closed_for_malformed_schema(mutated: list[object | None]) -> None:
    with pytest.raises(PositionMaterializationSchemaError) as exc:
        SqlPositionMaterializationSchemaVerifier(_Client(mutated)).verify()  # type: ignore[arg-type]

    assert str(exc.value) == SCHEMA_PRECONDITION_ERROR
