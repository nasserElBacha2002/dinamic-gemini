from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.application.use_cases.position_reconciliation.reconcile_job_positions import (
    POSITION_RECONCILIATION_PUBLISH_FAILED,
    ReconcileJobPositionsCommand,
    ReconcileJobPositionsUseCase,
)
from src.domain.jobs.entities import JobStatus
from src.domain.position_reconciliation.entities import ReconciliationStatus
from src.infrastructure.repositories.memory_position_reconciliation_repository import (
    MemoryPositionReconciliationRepository,
)

NOW = datetime(2026, 9, 8, tzinfo=timezone.utc)


class _PublishError(RuntimeError):
    pass


class _FailFirstPublishRepository(MemoryPositionReconciliationRepository):
    def __init__(self, error: Exception, *, fail_record: bool = False) -> None:
        super().__init__()
        self._error = error
        self._fail_publish = True
        self._fail_record = fail_record

    def publish_completed_revision_atomically(
        self,
        reconciliation,
        assignments,
        previous_active_id,
        expected_input_fingerprint,
    ):
        if self._fail_publish:
            self._fail_publish = False
            raise self._error
        return super().publish_completed_revision_atomically(
            reconciliation,
            assignments,
            previous_active_id,
            expected_input_fingerprint,
        )

    def record_failed_attempt(self, attempt):
        if self._fail_record:
            raise RuntimeError("secondary failure contains sensitive details")
        return super().record_failed_attempt(attempt)


def _use_case(repository: MemoryPositionReconciliationRepository):
    inventory = SimpleNamespace(id="inventory-1", client_id="client-1")
    aisle = SimpleNamespace(id="aisle-1", inventory_id="inventory-1")
    job = SimpleNamespace(
        id="job-1",
        target_type="aisle",
        target_id="aisle-1",
        status=JobStatus.SUCCEEDED,
        ordered_capture_session_id=None,
        sequence_version=1,
    )
    link = SimpleNamespace(
        source_asset_id="asset-1",
        sequence_number=1,
        position_order=None,
    )
    asset = SimpleNamespace(
        id="asset-1",
        upload_client_file_id="client-image-1",
        ordered_capture_session_id=None,
        sequence_number=1,
    )
    return ReconcileJobPositionsUseCase(
        inventory_repo=SimpleNamespace(get_by_id=lambda _id: inventory),
        aisle_repo=SimpleNamespace(get_by_id=lambda _id: aisle),
        job_repo=SimpleNamespace(get_by_id=lambda _id: job),
        source_asset_repo=SimpleNamespace(
            get_by_ids=lambda _ids: {"asset-1": asset}
        ),
        job_source_asset_repo=SimpleNamespace(list_for_job=lambda _id: [link]),
        coverage_repo=SimpleNamespace(),
        product_record_repo=SimpleNamespace(),
        detection_repo=SimpleNamespace(list_by_job=lambda _id: []),
        reconciliation_repo=repository,
        final_item_result_reader=SimpleNamespace(
            list_for_job=lambda **_kwargs: [
                SimpleNamespace(source_asset_id="asset-1", result_id="result-1")
            ]
        ),
        clock=SimpleNamespace(now=lambda: NOW),
    )


def test_publish_failure_is_marked_failed_and_same_fingerprint_retry_succeeds() -> None:
    primary = _PublishError("primary publication failure")
    repository = _FailFirstPublishRepository(primary)
    use_case = _use_case(repository)
    command = ReconcileJobPositionsCommand("inventory-1", "job-1")

    with pytest.raises(_PublishError) as raised:
        use_case.execute(command)
    assert raised.value is primary

    failed = repository.get_last_attempt_by_job("job-1")
    assert failed is not None
    assert failed.status is ReconciliationStatus.FAILED
    assert failed.failure_code == POSITION_RECONCILIATION_PUBLISH_FAILED
    assert failed.completed_at == NOW
    assert failed.updated_at == NOW
    assert failed.is_active is False

    retried = use_case.execute(command)
    assert retried.reconciliation.status is ReconciliationStatus.COMPLETED
    assert retried.reconciliation.input_fingerprint == failed.input_fingerprint


def test_secondary_failure_recording_does_not_mask_primary(caplog) -> None:
    primary = _PublishError("primary publication failure")
    repository = _FailFirstPublishRepository(primary, fail_record=True)

    with pytest.raises(_PublishError) as raised:
        _use_case(repository).execute(
            ReconcileJobPositionsCommand("inventory-1", "job-1")
        )

    assert raised.value is primary
    assert "primary publication failure" not in caplog.text
    assert "sensitive details" not in caplog.text
    assert "primary_error_type=_PublishError" in caplog.text
    assert "record_error_type=RuntimeError" in caplog.text
