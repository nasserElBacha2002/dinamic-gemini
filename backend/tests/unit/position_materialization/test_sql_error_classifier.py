from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pyodbc
import pytest

from src.application.dto.access_principal import AccessPrincipal
from src.application.dto.position_materialization import MaterializePositionCommand
from src.domain.position_materialization.errors import (
    PositionMaterializationInvariantError,
    PositionMaterializationRetryableError,
)
from src.domain.position_recognition.entities import (
    CanonicalPositionRecognition,
    PositionRecognitionSource,
)
from src.infrastructure.database.position_materialization_sql_errors import (
    ACTIVE_IDENTITY_INDEX,
    LEDGER_IDEMPOTENCY_INDEX,
    SqlFailureKind,
    classify_sql_failure,
)
from src.infrastructure.database.sql_transaction import TransactionState
from src.infrastructure.persistence.sql_position_materialization_unit_of_work import (
    SqlPositionMaterializationUnitOfWork,
)


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (
            (
                "23000",
                f"[23000] duplicate key on index '{ACTIVE_IDENTITY_INDEX}' (2627)",
            ),
            SqlFailureKind.IDENTITY_CONFLICT,
        ),
        (
            ([("23000", f"duplicate {LEDGER_IDEMPOTENCY_INDEX} (2601)")],),
            SqlFailureKind.IDEMPOTENCY_CONFLICT,
        ),
        (("23000", "foreign key constraint (547)"), SqlFailureKind.INVARIANT_VIOLATION),
        (("22001", "string data would be truncated (2628)"), SqlFailureKind.INVARIANT_VIOLATION),
        (("22001", "string or binary data truncated (8152)"), SqlFailureKind.INVARIANT_VIOLATION),
        (("40001", "transaction deadlock (1205)"), SqlFailureKind.RETRYABLE),
        (([("HYT00", "timeout expired")],), SqlFailureKind.RETRYABLE),
        (("08S01", "communication link failure"), SqlFailureKind.RETRYABLE),
        (("23000", "unknown integrity constraint"), SqlFailureKind.INVARIANT_VIOLATION),
        (
            ("23000", "duplicate key on unrelated index (2627)"),
            SqlFailureKind.INVARIANT_VIOLATION,
        ),
    ],
)
def test_classifies_realistic_pyodbc_diagnostic_shapes(
    args: tuple[object, ...],
    expected: SqlFailureKind,
) -> None:
    exc = Exception(*args)

    classification = classify_sql_failure(exc)

    assert classification.kind is expected
    assert not hasattr(classification, "message")


class _LockCursor:
    def __init__(self, result: int) -> None:
        self._result = result

    def execute(self, *_args: object) -> None:
        return None

    def fetchone(self):
        return type("Row", (), {"lock_result": self._result})()


def _command() -> MaterializePositionCommand:
    return MaterializePositionCommand(
        recognition=CanonicalPositionRecognition(
            raw_code="A-1",
            normalized_code="A-1",
            source=PositionRecognitionSource.CODE_SCAN,
        ),
        inventory_id="inventory",
        aisle_id="aisle",
        principal=AccessPrincipal(
            actor_id="actor",
            client_id="client",
            roles=frozenset(),
            is_platform=False,
        ),
        idempotency_key="key",
    )


@pytest.mark.parametrize("lock_result", [-1, -2, -3])
def test_application_lock_transient_results_are_retryable(lock_result: int) -> None:
    uow = SqlPositionMaterializationUnitOfWork(object())  # type: ignore[arg-type]

    with pytest.raises(PositionMaterializationRetryableError):
        uow._acquire_identity_lock(_LockCursor(lock_result), _command(), "client")


def test_application_lock_parameter_error_is_invariant() -> None:
    uow = SqlPositionMaterializationUnitOfWork(object())  # type: ignore[arg-type]

    with pytest.raises(PositionMaterializationInvariantError):
        uow._acquire_identity_lock(_LockCursor(-999), _command(), "client")


class _FailingTransaction:
    def __init__(self, exc: BaseException) -> None:
        cursor = SimpleNamespace(execute=lambda *_args: (_ for _ in ()).throw(exc))
        self.connection = SimpleNamespace(cursor=lambda: cursor)
        self.state = TransactionState.CLOSED

    def __enter__(self):
        self.state = TransactionState.ACTIVE
        return self

    def rollback(self) -> None:
        self.state = TransactionState.ROLLED_BACK

    def close(self) -> None:
        self.state = TransactionState.CLOSED


class _FailingClient:
    def __init__(self, exc: BaseException) -> None:
        self.exc = exc

    def begin_transaction(self) -> _FailingTransaction:
        return _FailingTransaction(self.exc)


def test_data_error_is_classified_as_invariant_and_preserves_cause() -> None:
    original = pyodbc.DataError("22001", "string data right truncation (8152)")
    uow = SqlPositionMaterializationUnitOfWork(_FailingClient(original))  # type: ignore[arg-type]

    with pytest.raises(PositionMaterializationInvariantError) as exc:
        uow.materialize(
            _command(),
            request_hash="a" * 64,
            now=datetime.now(timezone.utc),
        )

    assert exc.value.__cause__ is original


def test_programming_error_is_not_hidden() -> None:
    original = pyodbc.ProgrammingError("42000", "invalid column")
    uow = SqlPositionMaterializationUnitOfWork(_FailingClient(original))  # type: ignore[arg-type]

    with pytest.raises(pyodbc.ProgrammingError) as exc:
        uow.materialize(
            _command(),
            request_hash="a" * 64,
            now=datetime.now(timezone.utc),
        )

    assert exc.value is original


def test_sql_replay_rejects_unsupported_fingerprint_version() -> None:
    row = SimpleNamespace(
        fingerprint_version=99,
        request_hash="a" * 64,
        result="MATERIALIZED",
        location_id="location",
        public_identifier="loc_location",
        id="request",
    )

    with pytest.raises(PositionMaterializationInvariantError) as exc:
        SqlPositionMaterializationUnitOfWork._resolve_replay(row, "a" * 64)

    assert exc.value.code == "UNSUPPORTED_MATERIALIZATION_FINGERPRINT_VERSION"
