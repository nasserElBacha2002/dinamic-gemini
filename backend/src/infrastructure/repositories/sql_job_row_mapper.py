"""Map inventory_jobs SQL rows to domain Job entities.

Extracted from SqlJobRepository (Phase 6) so persistence mapping is reusable
and the repository class focuses on CAS / query / recovery operations.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from src.domain.aisle_identification.modes import (
    CONFIGURATION_SNAPSHOT_VERSION,
    historical_job_execution_strategy,
    historical_job_identification_mode,
    historical_job_identification_mode_source,
)
from src.domain.jobs.entities import Job, JobStatus
from src.domain.jobs.finalization import (
    CurrentFinalizationStep,
    FinalizationStatus,
    LastCompletedFinalizationStep,
)
from src.infrastructure.repositories.db_row_text import normalize_db_str

logger = logging.getLogger(__name__)

# Fixed column projection for inventory_jobs reads (not user-controlled).
JOB_SELECT_FIELDS = (
    "id, target_type, target_id, job_type, status, "
    "payload_json, result_json, error_message, created_at, updated_at, "
    "started_at, finished_at, last_heartbeat_at, cancel_requested_at, "
    "current_stage, current_substep, current_step_started_at, "
    "attempt_count, retry_of_job_id, failure_code, failure_message, execution_id, claim_owner_id, "
    "provider_name, model_name, prompt_key, engine_params_json, prompt_version, "
    "identification_mode, identification_mode_source, configuration_snapshot_version, "
    "execution_strategy, "
    "finalization_status, current_finalization_step, last_completed_finalization_step, "
    "finalization_error_code, finalization_error_metadata, finalization_started_at, "
    "finalization_completed_at, domain_persisted_at, artifacts_published_at, "
    "lease_fencing_token, lease_expires_at, lease_acquired_at"
)


def ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def status_from_row(row: Any, job_id: str = "?") -> JobStatus:
    raw = getattr(row, "status", None)
    if raw is None:
        status_str = "queued"
    elif isinstance(raw, str):
        status_str = raw.strip() or "queued"
    else:
        status_str = str(raw).strip() or "queued"
    try:
        return JobStatus(status_str)
    except ValueError:
        logger.warning(
            "Invalid job status from DB: %r, using QUEUED for job_id=%s",
            status_str,
            job_id,
        )
        return JobStatus.QUEUED


def finalization_status_from_row(row: Any) -> FinalizationStatus:
    raw = getattr(row, "finalization_status", None)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return FinalizationStatus.NOT_STARTED
    try:
        return FinalizationStatus(str(raw).strip())
    except ValueError:
        return FinalizationStatus.NOT_STARTED


def current_finalization_step_from_row(row: Any) -> CurrentFinalizationStep | None:
    raw = getattr(row, "current_finalization_step", None)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    try:
        return CurrentFinalizationStep(str(raw).strip())
    except ValueError:
        return None


def last_completed_step_from_row(row: Any) -> LastCompletedFinalizationStep:
    raw = getattr(row, "last_completed_finalization_step", None)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return LastCompletedFinalizationStep.NONE
    try:
        return LastCompletedFinalizationStep(str(raw).strip())
    except ValueError:
        return LastCompletedFinalizationStep.NONE


def parse_json(raw: object) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, str):
        text = raw.strip()
    else:
        text = str(raw).strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def parse_optional_json(raw: object) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        text = raw.strip()
    else:
        text = str(raw).strip()
    if not text:
        return None
    try:
        v = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(v, dict):
        return v
    return {"value": v}


def row_to_job(row: Any) -> Job:
    jid = getattr(row, "id", "")
    created = ensure_utc(getattr(row, "created_at", None))
    updated = ensure_utc(getattr(row, "updated_at", None))
    if created is None:
        logger.warning("inventory_jobs row missing created_at for job_id=%s", jid)
        raise ValueError("inventory_jobs row missing required created_at")
    if updated is None:
        logger.warning("inventory_jobs row missing updated_at for job_id=%s", jid)
        raise ValueError("inventory_jobs row missing required updated_at")
    return Job(
        id=jid,
        target_type=normalize_db_str(getattr(row, "target_type", None)),
        target_id=normalize_db_str(getattr(row, "target_id", None)),
        job_type=normalize_db_str(getattr(row, "job_type", None)),
        status=status_from_row(row, jid),
        payload_json=parse_json(getattr(row, "payload_json", None)),
        created_at=created,
        updated_at=updated,
        result_json=parse_json(getattr(row, "result_json", None)) or None,
        error_message=getattr(row, "error_message", None),
        started_at=ensure_utc(getattr(row, "started_at", None)),
        finished_at=ensure_utc(getattr(row, "finished_at", None)),
        last_heartbeat_at=ensure_utc(getattr(row, "last_heartbeat_at", None)),
        cancel_requested_at=ensure_utc(getattr(row, "cancel_requested_at", None)),
        current_stage=getattr(row, "current_stage", None),
        current_substep=getattr(row, "current_substep", None),
        current_step_started_at=ensure_utc(getattr(row, "current_step_started_at", None)),
        attempt_count=int(getattr(row, "attempt_count", 1) or 1),
        retry_of_job_id=getattr(row, "retry_of_job_id", None),
        failure_code=getattr(row, "failure_code", None),
        failure_message=getattr(row, "failure_message", None),
        execution_id=getattr(row, "execution_id", None),
        claim_owner_id=getattr(row, "claim_owner_id", None),
        provider_name=getattr(row, "provider_name", None),
        model_name=getattr(row, "model_name", None),
        prompt_key=getattr(row, "prompt_key", None),
        engine_params_json=parse_optional_json(getattr(row, "engine_params_json", None)),
        prompt_version=getattr(row, "prompt_version", None),
        identification_mode=historical_job_identification_mode(
            getattr(row, "identification_mode", None)
        ),
        identification_mode_source=historical_job_identification_mode_source(
            getattr(row, "identification_mode_source", None)
        ),
        configuration_snapshot_version=int(
            getattr(row, "configuration_snapshot_version", None)
            or CONFIGURATION_SNAPSHOT_VERSION
        ),
        execution_strategy=historical_job_execution_strategy(
            getattr(row, "execution_strategy", None)
        ),
        finalization_status=finalization_status_from_row(row),
        current_finalization_step=current_finalization_step_from_row(row),
        last_completed_finalization_step=last_completed_step_from_row(row),
        finalization_error_code=getattr(row, "finalization_error_code", None),
        finalization_error_metadata=parse_optional_json(
            getattr(row, "finalization_error_metadata", None)
        ),
        finalization_started_at=ensure_utc(getattr(row, "finalization_started_at", None)),
        finalization_completed_at=ensure_utc(getattr(row, "finalization_completed_at", None)),
        domain_persisted_at=ensure_utc(getattr(row, "domain_persisted_at", None)),
        artifacts_published_at=ensure_utc(getattr(row, "artifacts_published_at", None)),
        lease_fencing_token=int(getattr(row, "lease_fencing_token", 0) or 0),
        lease_expires_at=ensure_utc(getattr(row, "lease_expires_at", None)),
        lease_acquired_at=ensure_utc(getattr(row, "lease_acquired_at", None)),
    )


# Backward-compatible aliases used by older call sites / tests.
_ensure_utc = ensure_utc
_row_to_job = row_to_job
_JOB_SELECT_FIELDS = JOB_SELECT_FIELDS
