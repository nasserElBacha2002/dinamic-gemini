"""Real-SQL behavioral contract for position materialization."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier, Event
from uuid import uuid4

import pyodbc
import pytest

from src.application.dto.access_principal import AccessPrincipal
from src.application.services.position_materialization import (
    MaterializePositionCommand,
    MaterializePositionService,
    canonical_request_fingerprint,
)
from src.database.migrations import service as migration_service
from src.database.sqlserver import SqlServerClient
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.client.entities import Client, ClientStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
from src.domain.position_label_detection.entities import (
    ImagePositionLabelDetection,
    PositionLabelDetectionStatus,
    PositionLabelSignatureStatus,
)
from src.domain.position_materialization import (
    PositionMaterializationAssociationStatus,
    PositionMaterializationStatus,
)
from src.domain.position_materialization.entities import (
    PositionMaterializationAssociationReceipt,
)
from src.domain.position_materialization.errors import PositionMaterializationConflictError
from src.domain.position_recognition.entities import (
    CanonicalPositionRecognition,
    PositionRecognitionSource,
)
from src.domain.position_reconciliation.entities import (
    PositionReconciliation,
    ReconciliationStatus,
)
from src.infrastructure.persistence.sql_materialized_position_identity_reader import (
    SqlMaterializedPositionIdentityReader,
)
from src.infrastructure.persistence.sql_position_materialization_association_receipt_repository import (
    SqlPositionMaterializationAssociationReceiptRepository,
)
from src.infrastructure.persistence.sql_position_materialization_unit_of_work import (
    SqlPositionMaterializationUnitOfWork,
)
from src.infrastructure.repositories.sql_aisle_repository import SqlAisleRepository
from src.infrastructure.repositories.sql_client_repository import SqlClientRepository
from src.infrastructure.repositories.sql_image_position_label_detection_repository import (
    SqlImagePositionLabelDetectionRepository,
)
from src.infrastructure.repositories.sql_inventory_repository import SqlInventoryRepository
from src.infrastructure.repositories.sql_job_repository import SqlJobRepository
from src.infrastructure.repositories.sql_position_reconciliation_repository import (
    SqlPositionReconciliationRepository,
)
from tests.support.sql_integration import sql_server_client_or_skip
from tests.support.sql_migration_fixture import ensure_sql_migrations_applied
from tests.support.sqlserver_test_connection import resolved_sqlserver_connection_string_for_tests

pytestmark = pytest.mark.integration

_0106_DOWN_PREFLIGHT = migration_service._split_sql_batches(
    (
        Path(__file__).parents[3]
        / "src/database/migrations/versions/0106_position_materialization_association_recovery.down.sql"
    ).read_text(encoding="utf-8")
)[0]
_0107_DOWN_PREFLIGHT = migration_service._split_sql_batches(
    (
        Path(__file__).parents[3]
        / "src/database/migrations/versions/0107_position_materialization_fingerprint_version.down.sql"
    ).read_text(encoding="utf-8")
)[0]


@pytest.fixture(scope="module")
def sql_client() -> SqlServerClient:
    client = sql_server_client_or_skip(resolved_sqlserver_connection_string_for_tests())
    ensure_sql_migrations_applied(client)
    return client


@dataclass(frozen=True)
class MaterializationSqlCase:
    client: SqlServerClient
    client_id: str
    inventory_id: str
    aisle_id: str
    supplier_id: str
    profile_id: str
    profile_version: int
    normalized_code: str

    def command(
        self,
        *,
        key: str,
        raw_code: str | None = None,
        principal_client_id: str | None = None,
        supplier_id: str | None = None,
        profile_id: str | None = None,
        profile_version: int | None = None,
    ) -> MaterializePositionCommand:
        return MaterializePositionCommand(
            recognition=CanonicalPositionRecognition(
                raw_code=raw_code or f"raw {self.normalized_code}",
                normalized_code=self.normalized_code,
                source=PositionRecognitionSource.CODE_SCAN,
                client_supplier_id=supplier_id if supplier_id is not None else self.supplier_id,
                profile_id=profile_id if profile_id is not None else self.profile_id,
                profile_version=(
                    profile_version if profile_version is not None else self.profile_version
                ),
            ),
            inventory_id=self.inventory_id,
            aisle_id=self.aisle_id,
            principal=AccessPrincipal(
                actor_id="sql-contract-test",
                client_id=principal_client_id or self.client_id,
                roles=frozenset({"operator"}),
                is_platform=False,
            ),
            idempotency_key=key,
        )

    def service(
        self,
        uow_type: type[SqlPositionMaterializationUnitOfWork] = (
            SqlPositionMaterializationUnitOfWork
        ),
    ) -> MaterializePositionService:
        return MaterializePositionService(uow_type(self.client))


@pytest.fixture
def sql_case(sql_client: SqlServerClient):
    now = datetime.now(timezone.utc)
    token = uuid4().hex
    client_id = str(uuid4())
    inventory_id = str(uuid4())
    aisle_id = str(uuid4())
    supplier_id = str(uuid4())
    profile_id = str(uuid4())
    profile_version = 7

    SqlClientRepository(sql_client).save(
        Client(
            id=client_id,
            name=f"Position materialization {token}",
            status=ClientStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )
    SqlInventoryRepository(sql_client).save(
        Inventory(
            id=inventory_id,
            name=f"Position materialization {token}",
            status=InventoryStatus.PROCESSING,
            created_at=now,
            updated_at=now,
            client_id=client_id,
        )
    )
    with sql_client.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO dbo.client_suppliers
                (id, client_id, name, status, created_at, updated_at)
            VALUES (?, ?, ?, 'active', ?, ?)
            """,
            (supplier_id, client_id, f"Supplier {token}", now, now),
        )
        cursor.execute(
            """
            INSERT INTO dbo.supplier_extraction_profiles (
                id, client_id, supplier_id, profile_key, version, status,
                configuration_json, created_by, created_at, updated_at, label_kind
            ) VALUES (?, ?, ?, ?, ?, 'SUPERSEDED', N'{}', ?, ?, ?, 'POSITION')
            """,
            (
                profile_id,
                client_id,
                supplier_id,
                f"position-{token}",
                profile_version,
                "sql-contract-test",
                now,
                now,
            ),
        )
    SqlAisleRepository(sql_client).save(
        Aisle(
            id=aisle_id,
            inventory_id=inventory_id,
            code=f"A-{token[:8]}",
            status=AisleStatus.PROCESSING,
            created_at=now,
            updated_at=now,
            client_supplier_id=supplier_id,
        )
    )
    case = MaterializationSqlCase(
        client=sql_client,
        client_id=client_id,
        inventory_id=inventory_id,
        aisle_id=aisle_id,
        supplier_id=supplier_id,
        profile_id=profile_id,
        profile_version=profile_version,
        normalized_code=f"RACK-{token[:8]}",
    )
    try:
        yield case
    finally:
        with sql_client.cursor() as cursor:
            cursor.execute(
                """
                DELETE receipts
                FROM dbo.position_materialization_association_receipts AS receipts
                INNER JOIN dbo.position_materialization_requests AS requests
                    ON requests.id = receipts.request_id
                WHERE requests.inventory_id = ?
                """,
                (inventory_id,),
            )
            cursor.execute(
                "DELETE FROM dbo.position_materialization_requests WHERE inventory_id = ?",
                (inventory_id,),
            )
            cursor.execute(
                "DELETE FROM dbo.aisle_locations WHERE client_id = ? AND aisle_id = ?",
                (client_id, aisle_id),
            )
            cursor.execute("DELETE FROM dbo.aisles WHERE id = ?", (aisle_id,))
            cursor.execute(
                "DELETE FROM dbo.supplier_extraction_profiles WHERE id = ?",
                (profile_id,),
            )
            cursor.execute("DELETE FROM dbo.client_suppliers WHERE id = ?", (supplier_id,))
            cursor.execute("DELETE FROM dbo.inventories WHERE id = ?", (inventory_id,))
            cursor.execute("DELETE FROM dbo.clients WHERE id = ?", (client_id,))


def test_same_key_same_payload_is_explicit_replay(sql_case: MaterializationSqlCase) -> None:
    command = sql_case.command(key="same-payload")
    service = sql_case.service()
    first = service.execute(command)
    replay = service.lookup_replay(command)
    assert replay is not None

    assert first.status is PositionMaterializationStatus.MATERIALIZED
    assert first.idempotent_replay is False
    assert replay.status is PositionMaterializationStatus.MATERIALIZED
    assert replay.idempotent_replay is True
    assert replay.location_id == first.location_id
    assert replay.request_id == first.request_id


def test_replay_only_lookup_missing_does_not_create_rows(
    sql_case: MaterializationSqlCase,
) -> None:
    result = sql_case.service().lookup_replay(sql_case.command(key="pre-rollout-missing"))

    assert result is None
    with sql_case.client.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                (SELECT COUNT_BIG(*) FROM dbo.aisle_locations
                 WHERE client_id = ? AND aisle_id = ?) AS locations,
                (SELECT COUNT_BIG(*) FROM dbo.position_materialization_requests
                 WHERE client_id = ?) AS requests
            """,
            (sql_case.client_id, sql_case.aisle_id, sql_case.client_id),
        )
        row = cursor.fetchone()
    assert int(row.locations) == 0
    assert int(row.requests) == 0


def test_association_cas_moves_review_to_associated(sql_case: MaterializationSqlCase) -> None:
    service = sql_case.service()
    result = service.execute(sql_case.command(key="association-cas"))
    assert result.request_id is not None
    assert service.get_association_status(str(uuid4())) is None
    assert (
        service.get_association_status(result.request_id)
        is PositionMaterializationAssociationStatus.PENDING
    )

    assert service.complete_association(
        result.request_id,
        success=False,
        error_code="IMAGE_RESULT_CONFLICT",
    )
    assert service.complete_association(result.request_id, success=True)
    assert (
        service.complete_association(
            result.request_id,
            success=False,
            error_code="LATE_FAILURE",
        )
        is False
    )
    with sql_case.client.cursor() as cursor:
        cursor.execute(
            """
            SELECT association_status, associated_at, association_error_code
            FROM dbo.position_materialization_requests WHERE id = ?
            """,
            (result.request_id,),
        )
        row = cursor.fetchone()

    assert str(row.association_status) == "ASSOCIATED"
    assert (
        service.get_association_status(result.request_id)
        is PositionMaterializationAssociationStatus.ASSOCIATED
    )
    assert row.associated_at is not None
    assert row.association_error_code is None


def test_two_connection_association_claim_reclaim_and_owner_fencing(
    sql_case: MaterializationSqlCase,
) -> None:
    result = sql_case.service().execute(sql_case.command(key="association-fencing"))
    assert result.request_id is not None
    now = datetime.now(timezone.utc)
    connection_string = resolved_sqlserver_connection_string_for_tests()
    worker_clients = {
        "first-a": SqlServerClient(connection_string),
        "first-b": SqlServerClient(connection_string),
    }
    start = Barrier(2)

    def claim(worker: tuple[str, SqlServerClient]):
        owner, client = worker
        start.wait(timeout=5)
        return SqlPositionMaterializationUnitOfWork(client).claim_due_associations(
            owner=owner,
            now=now,
            lease=timedelta(seconds=1),
            batch=1,
            max_attempts=3,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(
            executor.map(
                claim,
                worker_clients.items(),
            )
        )

    winners = [
        claim
        for worker_claims in claims
        for claim in worker_claims
        if claim.request_id == result.request_id
    ]
    assert len(winners) == 1
    first_owner = winners[0].owner
    first_uow = SqlPositionMaterializationUnitOfWork(worker_clients[first_owner])

    reclaim_at = now + timedelta(seconds=2)
    second_owner = "second-owner"
    second_uow = SqlPositionMaterializationUnitOfWork(SqlServerClient(connection_string))
    reclaimed = second_uow.claim_due_associations(
        owner=second_owner,
        now=reclaim_at,
        lease=timedelta(minutes=1),
        batch=1,
        max_attempts=3,
    )
    assert [claim.request_id for claim in reclaimed] == [result.request_id]
    assert reclaimed[0].attempt_count == 0

    assert not first_uow.complete_claimed(
        request_id=result.request_id, owner=first_owner, now=reclaim_at
    )
    assert not first_uow.reschedule_claimed(
        request_id=result.request_id,
        owner=first_owner,
        now=reclaim_at,
        next_retry_at=reclaim_at + timedelta(minutes=1),
        error_code="STALE_RESCHEDULE",
    )
    assert not first_uow.exhaust_claimed(
        request_id=result.request_id,
        owner=first_owner,
        now=reclaim_at,
        error_code="STALE_EXHAUST",
    )

    assert second_uow.complete_claimed(
        request_id=result.request_id,
        owner=second_owner,
        now=reclaim_at,
    )

    with sql_case.client.cursor() as cursor:
        cursor.execute(
            """
            SELECT association_status, attempt_count, last_attempt_at,
                   next_retry_at, lease_owner, lease_expires_at
            FROM dbo.position_materialization_requests
            WHERE id = ?
            """,
            (result.request_id,),
        )
        row = cursor.fetchone()

    assert str(row.association_status) == "ASSOCIATED"
    assert int(row.attempt_count) == 1
    assert row.last_attempt_at is not None
    assert row.next_retry_at is None
    assert row.lease_owner is None
    assert row.lease_expires_at is None


def test_0106_down_preflight_rejects_every_non_drained_status(
    sql_case: MaterializationSqlCase,
) -> None:
    result = sql_case.service().execute(sql_case.command(key="down-preflight"))
    assert result.request_id is not None

    for status, error_code in (
        ("PENDING", None),
        ("REQUIRES_REVIEW", "NEEDS_REVIEW"),
        ("EXHAUSTED", "ATTEMPTS_EXHAUSTED"),
    ):
        with sql_case.client.cursor() as cursor:
            cursor.execute(
                """
                UPDATE dbo.position_materialization_requests
                SET association_status = ?, association_error_code = ?,
                    associated_at = NULL, lease_owner = NULL, lease_expires_at = NULL
                WHERE id = ?
                """,
                (status, error_code, result.request_id),
            )
        with pytest.raises(pyodbc.Error, match="51016"):
            with sql_case.client.cursor() as cursor:
                cursor.execute(_0106_DOWN_PREFLIGHT)


def test_same_key_different_payload_conflicts(sql_case: MaterializationSqlCase) -> None:
    service = sql_case.service()
    service.execute(sql_case.command(key="payload-conflict"))

    result = service.execute(
        sql_case.command(key="payload-conflict", raw_code="contradictory raw evidence")
    )

    assert result.status is PositionMaterializationStatus.REJECTED_IDEMPOTENCY_CONFLICT
    assert result.error_code == "IDEMPOTENCY_KEY_CONFLICT"
    with pytest.raises(PositionMaterializationConflictError) as exc:
        service.lookup_replay(
            sql_case.command(
                key="payload-conflict",
                raw_code="another contradictory raw value",
            )
        )
    assert exc.value.code == "IDEMPOTENCY_KEY_CONFLICT"


def test_new_write_rejected_after_close_but_committed_replay_succeeds(
    sql_case: MaterializationSqlCase,
) -> None:
    committed = sql_case.command(key="before-close")
    first = sql_case.service().execute(committed)
    with sql_case.client.cursor() as cursor:
        cursor.execute(
            "UPDATE dbo.inventories SET status = 'completed' WHERE id = ?",
            (sql_case.inventory_id,),
        )

    replay = sql_case.service().execute(committed)
    rejected = sql_case.service().execute(sql_case.command(key="after-close"))

    assert first.status is PositionMaterializationStatus.MATERIALIZED
    assert replay.status is PositionMaterializationStatus.MATERIALIZED
    assert replay.idempotent_replay is True
    assert rejected.status is PositionMaterializationStatus.REJECTED_INVENTORY_STATE


def test_tenant_mismatch_is_rejected(sql_case: MaterializationSqlCase) -> None:
    result = sql_case.service().execute(
        sql_case.command(key="wrong-tenant", principal_client_id=str(uuid4()))
    )

    assert result.status is PositionMaterializationStatus.REJECTED_SCOPE
    assert result.error_code == "INVENTORY_SCOPE_MISMATCH"


def test_supplier_and_profile_scope_mismatches_are_rejected(
    sql_case: MaterializationSqlCase,
) -> None:
    supplier_result = sql_case.service().execute(
        sql_case.command(key="wrong-supplier", supplier_id=str(uuid4()))
    )
    profile_result = sql_case.service().execute(
        sql_case.command(key="wrong-profile", profile_id=str(uuid4()))
    )
    version_result = sql_case.service().execute(
        sql_case.command(key="wrong-profile-version", profile_version=99)
    )
    with sql_case.client.cursor() as cursor:
        cursor.execute(
            "UPDATE dbo.aisles SET client_supplier_id = NULL WHERE id = ?",
            (sql_case.aisle_id,),
        )
    supplierless_profile = MaterializePositionCommand(
        recognition=CanonicalPositionRecognition(
            raw_code=f"raw {sql_case.normalized_code}",
            normalized_code=sql_case.normalized_code,
            source=PositionRecognitionSource.CODE_SCAN,
            client_supplier_id=None,
            profile_id=sql_case.profile_id,
            profile_version=sql_case.profile_version,
        ),
        inventory_id=sql_case.inventory_id,
        aisle_id=sql_case.aisle_id,
        principal=AccessPrincipal(
            actor_id="sql-contract-test",
            client_id=sql_case.client_id,
            roles=frozenset({"operator"}),
            is_platform=False,
        ),
        idempotency_key="supplierless-profile",
    )
    supplierless_result = sql_case.service().execute(supplierless_profile)

    assert supplier_result.error_code == "SUPPLIER_SCOPE_MISMATCH"
    assert profile_result.error_code == "PROFILE_SCOPE_MISMATCH"
    assert version_result.error_code == "PROFILE_SCOPE_MISMATCH"
    assert supplierless_result.error_code == "PROFILE_SCOPE_MISMATCH"


def test_ledger_insert_failure_rolls_back_inserted_location(
    sql_case: MaterializationSqlCase,
) -> None:
    class FailingLedgerUow(SqlPositionMaterializationUnitOfWork):
        def _insert_request(self, *args, **kwargs) -> None:
            raise pyodbc.IntegrityError("forced ledger failure")

    result = sql_case.service(FailingLedgerUow).execute(
        sql_case.command(key="forced-ledger-failure")
    )

    assert result.status is PositionMaterializationStatus.INVARIANT_VIOLATION
    assert result.error_code == "MATERIALIZATION_PERSISTENCE_INVARIANT"
    with sql_case.client.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                (SELECT COUNT_BIG(*) FROM dbo.aisle_locations
                 WHERE client_id = ? AND aisle_id = ? AND normalized_code = ?) AS locations,
                (SELECT COUNT_BIG(*) FROM dbo.position_materialization_requests
                 WHERE client_id = ? AND idempotency_key = ?) AS requests
            """,
            (
                sql_case.client_id,
                sql_case.aisle_id,
                sql_case.normalized_code,
                sql_case.client_id,
                "forced-ledger-failure",
            ),
        )
        row = cursor.fetchone()

    assert int(row.locations) == 0
    assert int(row.requests) == 0


def test_unexpected_transaction_failure_rolls_back_and_reraises_original(
    sql_case: MaterializationSqlCase,
) -> None:
    original = RuntimeError("unexpected persistence defect")

    class FailingLedgerUow(SqlPositionMaterializationUnitOfWork):
        def _insert_request(self, *args, **kwargs) -> None:
            raise original

    command = sql_case.command(key="unexpected-ledger-failure")
    with pytest.raises(RuntimeError) as raised:
        FailingLedgerUow(sql_case.client).materialize(
            command,
            request_hash=canonical_request_fingerprint(command),
            now=datetime.now(timezone.utc),
        )

    assert raised.value is original
    with sql_case.client.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT_BIG(*)
            FROM dbo.aisle_locations
            WHERE client_id = ? AND aisle_id = ? AND normalized_code = ?
            """,
            (sql_case.client_id, sql_case.aisle_id, sql_case.normalized_code),
        )
        row = cursor.fetchone()
    assert int(row[0]) == 0


def test_0107_down_blocks_unsupported_persisted_fingerprint_version(
    sql_case: MaterializationSqlCase,
) -> None:
    result = sql_case.service().execute(sql_case.command(key="down-version-guard"))
    assert result.request_id is not None
    try:
        with sql_case.client.cursor() as cursor:
            cursor.execute(
                """
                ALTER TABLE dbo.position_materialization_requests
                    NOCHECK CONSTRAINT CK_pmr_fingerprint_version;
                UPDATE dbo.position_materialization_requests
                SET fingerprint_version = 2
                WHERE id = ?;
                """,
                (result.request_id,),
            )
        with pytest.raises(pyodbc.Error):
            with sql_case.client.cursor() as cursor:
                cursor.execute(_0107_DOWN_PREFLIGHT)
    finally:
        with sql_case.client.cursor() as cursor:
            cursor.execute(
                """
                UPDATE dbo.position_materialization_requests
                SET fingerprint_version = 1
                WHERE id = ?;
                ALTER TABLE dbo.position_materialization_requests
                    WITH CHECK CHECK CONSTRAINT CK_pmr_fingerprint_version;
                """,
                (result.request_id,),
            )


def test_inventory_completion_waits_for_materialization_transaction(
    sql_case: MaterializationSqlCase,
) -> None:
    entered = Event()
    release = Event()
    completion_finished = Event()

    class PausingAfterScopeReadUow(SqlPositionMaterializationUnitOfWork):
        def _acquire_identity_lock(self, cursor, command, client_id) -> None:
            super()._acquire_identity_lock(cursor, command, client_id)
            entered.set()
            if not release.wait(timeout=5):
                raise RuntimeError("test did not release materialization")

    def complete_inventory() -> None:
        with sql_case.client.cursor() as cursor:
            cursor.execute(
                "UPDATE dbo.inventories SET status = 'completed' WHERE id = ?",
                (sql_case.inventory_id,),
            )
        completion_finished.set()

    with ThreadPoolExecutor(max_workers=2) as executor:
        materialization = executor.submit(
            sql_case.service(PausingAfterScopeReadUow).execute,
            sql_case.command(key="completion-race"),
        )
        assert entered.wait(timeout=5)
        completion = executor.submit(complete_inventory)
        assert completion_finished.wait(timeout=0.25) is False
        release.set()
        result = materialization.result(timeout=5)
        completion.result(timeout=5)

    assert result.status is PositionMaterializationStatus.MATERIALIZED
    with sql_case.client.cursor() as cursor:
        cursor.execute(
            "SELECT status FROM dbo.inventories WHERE id = ?",
            (sql_case.inventory_id,),
        )
        row = cursor.fetchone()
    assert str(row.status) == "completed"


def test_detection_replacement_nulls_receipt_and_revokes_identity(
    sql_case: MaterializationSqlCase,
) -> None:
    now = datetime.now(timezone.utc)
    job_id = str(uuid4())
    asset_id = str(uuid4())
    detection_id = str(uuid4())
    SqlJobRepository(sql_case.client).save(
        Job(
            id=job_id,
            target_type="aisle",
            target_id=sql_case.aisle_id,
            job_type="process_aisle",
            status=JobStatus.RUNNING,
            payload_json={"aisle_id": sql_case.aisle_id},
            created_at=now,
            updated_at=now,
        )
    )
    with sql_case.client.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO dbo.source_assets (
                id, aisle_id, type, original_filename, storage_path,
                mime_type, uploaded_at
            ) VALUES (?, ?, 'photo', 'position.jpg', 'test/position.jpg',
                      'image/jpeg', ?)
            """,
            (asset_id, sql_case.aisle_id, now),
        )
    reconciliation_repository = SqlPositionReconciliationRepository(sql_case.client)
    failed_attempt = PositionReconciliation(
        id=str(uuid4()),
        client_id=sql_case.client_id,
        inventory_id=sql_case.inventory_id,
        job_id=job_id,
        ordered_capture_session_id=None,
        input_fingerprint="a" * 64,
        status=ReconciliationStatus.RUNNING,
        started_at=now,
        created_at=now,
        updated_at=now,
        is_active=False,
    )
    assert reconciliation_repository.begin_or_get_running(failed_attempt).id == failed_attempt.id
    failed_attempt.status = ReconciliationStatus.FAILED
    failed_attempt.failure_code = "POSITION_RECONCILIATION_PUBLISH_FAILED"
    failed_attempt.completed_at = now
    reconciliation_repository.record_failed_attempt(failed_attempt)
    assert (
        reconciliation_repository.get_by_id(failed_attempt.id).status is ReconciliationStatus.FAILED
    )
    retry_attempt = PositionReconciliation(
        id=str(uuid4()),
        client_id=sql_case.client_id,
        inventory_id=sql_case.inventory_id,
        job_id=job_id,
        ordered_capture_session_id=None,
        input_fingerprint=failed_attempt.input_fingerprint,
        status=ReconciliationStatus.RUNNING,
        started_at=now,
        created_at=now,
        updated_at=now,
        is_active=False,
    )
    assert reconciliation_repository.begin_or_get_running(retry_attempt).id == retry_attempt.id
    retry_attempt.status = ReconciliationStatus.FAILED
    retry_attempt.failure_code = "TEST_CLEANUP"
    retry_attempt.completed_at = now
    reconciliation_repository.record_failed_attempt(retry_attempt)
    detections = SqlImagePositionLabelDetectionRepository(sql_case.client)
    detector_version = "0108-delete-contract"
    detections.upsert_idempotent(
        ImagePositionLabelDetection(
            id=detection_id,
            client_id=sql_case.client_id,
            inventory_id=sql_case.inventory_id,
            job_id=job_id,
            source_asset_id=asset_id,
            detection_status=PositionLabelDetectionStatus.VALID,
            signature_status=PositionLabelSignatureStatus.SKIPPED,
            payload_version=None,
            raw_payload_hash=uuid4().hex,
            detector_name="test",
            detector_version=detector_version,
            public_identifier=sql_case.normalized_code,
            position_name_snapshot=sql_case.normalized_code,
            created_at=now,
            updated_at=now,
        )
    )
    materialized = sql_case.service().execute(sql_case.command(key=f"detection-delete-{uuid4()}"))
    assert materialized.request_id is not None
    SqlPositionMaterializationAssociationReceiptRepository(sql_case.client).save(
        PositionMaterializationAssociationReceipt(
            request_id=materialized.request_id,
            target_type="IMAGE_RESULT",
            target_id=str(uuid4()),
            created_at=now,
            source_detection_id=detection_id,
        )
    )
    sql_case.service().complete_association(materialized.request_id, success=True, now=now)
    reader = SqlMaterializedPositionIdentityReader(sql_case.client)
    assert detection_id in reader.read_by_detection_ids(
        [detection_id],
        client_id=sql_case.client_id,
        inventory_id=sql_case.inventory_id,
        aisle_id=sql_case.aisle_id,
    )

    position_id = str(uuid4())
    result_id = str(uuid4())
    reconciliation_id = str(uuid4())
    label_id = str(uuid4())
    with sql_case.client.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO dbo.positions (
                id, aisle_id, status, confidence, needs_review, created_at, updated_at
            ) VALUES (?, ?, 'detected', 1, 0, ?, ?)
            """,
            (position_id, sql_case.aisle_id, now, now),
        )
        cursor.execute(
            """
            INSERT INTO dbo.product_records (
                id, position_id, sku, detected_quantity, confidence, created_at, updated_at
            ) VALUES (?, ?, 'SKU-0108', 1, 1, ?, ?)
            """,
            (result_id, position_id, now, now),
        )
        cursor.execute(
            """
            INSERT INTO dbo.position_reconciliations (
                id, client_id, inventory_id, job_id, reconciliation_name,
                reconciliation_version, input_fingerprint, status, started_at,
                completed_at, attempt_count, assigned_count, unassigned_count,
                sequence_gap_count, is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'test', '1.0.0', ?, 'COMPLETED', ?, ?,
                      1, 0, 0, 0, 1, ?, ?)
            """,
            (
                reconciliation_id,
                sql_case.client_id,
                sql_case.inventory_id,
                job_id,
                "f" * 64,
                now,
                now,
                now,
                now,
            ),
        )
        cursor.execute(
            """
            INSERT INTO dbo.client_position_labels (
                id, client_id, public_identifier, name, normalized_name,
                canonical_payload, created_at, updated_at
            ) VALUES (?, ?, 'LEGACY-0108', N'Legacy 0108', N'LEGACY 0108',
                      N'{}', ?, ?)
            """,
            (label_id, sql_case.client_id, now, now),
        )

    def insert_assignment(
        *,
        status: str,
        position_label_id: str | None,
        aisle_location_id: str | None,
    ) -> str:
        assignment_id = str(uuid4())
        with sql_case.client.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO dbo.product_position_assignments (
                    id, client_id, inventory_id, job_id, result_id, source_asset_id,
                    position_label_id, aisle_location_id, source_detection_id,
                    assignment_status, assignment_reason, reconciliation_id,
                    reconciliation_version, is_active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'TEST', ?, '1.0.0', 1, ?, ?)
                """,
                (
                    assignment_id,
                    sql_case.client_id,
                    sql_case.inventory_id,
                    job_id,
                    result_id,
                    asset_id,
                    position_label_id,
                    aisle_location_id,
                    detection_id,
                    status,
                    reconciliation_id,
                    now,
                    now,
                ),
            )
        return assignment_id

    try:
        physical_assignment_id = insert_assignment(
            status="ASSIGNED_AUTOMATIC",
            position_label_id=None,
            aisle_location_id=materialized.location_id,
        )
        with sql_case.client.cursor() as cursor:
            cursor.execute(
                "DELETE FROM dbo.product_position_assignments WHERE id = ?",
                (physical_assignment_id,),
            )
        legacy_assignment_id = insert_assignment(
            status="ASSIGNED_AUTOMATIC",
            position_label_id=label_id,
            aisle_location_id=None,
        )
        with sql_case.client.cursor() as cursor:
            cursor.execute(
                "DELETE FROM dbo.product_position_assignments WHERE id = ?",
                (legacy_assignment_id,),
            )
        with pytest.raises(pyodbc.IntegrityError):
            insert_assignment(
                status="UNASSIGNED_NO_PREVIOUS_POSITION",
                position_label_id=None,
                aisle_location_id=materialized.location_id,
            )
        with pytest.raises(pyodbc.IntegrityError):
            insert_assignment(
                status="ASSIGNED_AUTOMATIC",
                position_label_id=None,
                aisle_location_id=None,
            )

        detections.replace_asset_detections_atomically(
            job_id=job_id,
            source_asset_id=asset_id,
            detector_version=detector_version,
            detections=[],
        )
        with sql_case.client.cursor() as cursor:
            cursor.execute(
                """
                SELECT source_detection_id
                FROM dbo.position_materialization_association_receipts
                WHERE request_id = ?
                """,
                (materialized.request_id,),
            )
            receipt = cursor.fetchone()
        assert receipt is not None
        assert receipt.source_detection_id is None
        assert (
            reader.read_by_detection_ids(
                [detection_id],
                client_id=sql_case.client_id,
                inventory_id=sql_case.inventory_id,
                aisle_id=sql_case.aisle_id,
            )
            == {}
        )
    finally:
        with sql_case.client.cursor() as cursor:
            cursor.execute(
                "DELETE FROM dbo.product_position_assignments WHERE reconciliation_id = ?",
                (reconciliation_id,),
            )
            cursor.execute("DELETE FROM dbo.position_reconciliations WHERE job_id = ?", (job_id,))
            cursor.execute("DELETE FROM dbo.product_records WHERE id = ?", (result_id,))
            cursor.execute("DELETE FROM dbo.positions WHERE id = ?", (position_id,))
            cursor.execute("DELETE FROM dbo.client_position_labels WHERE id = ?", (label_id,))
            cursor.execute("DELETE FROM dbo.source_assets WHERE id = ?", (asset_id,))
            cursor.execute("DELETE FROM dbo.inventory_jobs WHERE id = ?", (job_id,))
