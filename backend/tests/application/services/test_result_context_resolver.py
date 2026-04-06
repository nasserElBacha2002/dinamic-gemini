"""ResultContextResolver — Phase 2 resolution rules."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.errors import JobDoesNotBelongToAisleError, JobNotFoundError
from src.application.services.result_context_resolver import ResultContextResolver
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.jobs.entities import Job, JobStatus
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository


def _aisle(op_job: str | None = None) -> Aisle:
    now = datetime.now(timezone.utc)
    return Aisle(
        id="a1",
        inventory_id="inv1",
        code="A",
        status=AisleStatus.PROCESSED,
        created_at=now,
        updated_at=now,
        operational_job_id=op_job,
    )


def _job(jid: str, aisle_id: str = "a1") -> Job:
    now = datetime.now(timezone.utc)
    return Job(
        id=jid,
        target_type="aisle",
        target_id=aisle_id,
        job_type="process_aisle",
        status=JobStatus.SUCCEEDED,
        payload_json={},
        created_at=now,
        updated_at=now,
        provider_name="gemini",
        model_name="m",
        prompt_key="p",
    )


def test_explicit_job_valid() -> None:
    repo = MemoryJobRepository()
    repo.save(_job("j1"))
    r = ResultContextResolver(repo).resolve(aisle=_aisle(), explicit_job_id="j1")
    assert r.job_id_for_slice == "j1"
    assert r.source == "explicit"


def test_explicit_job_missing_raises() -> None:
    with pytest.raises(JobNotFoundError):
        ResultContextResolver(MemoryJobRepository()).resolve(aisle=_aisle(), explicit_job_id="missing")


def test_explicit_job_wrong_aisle_raises() -> None:
    repo = MemoryJobRepository()
    repo.save(_job("j1", aisle_id="other"))
    with pytest.raises(JobDoesNotBelongToAisleError):
        ResultContextResolver(repo).resolve(aisle=_aisle(), explicit_job_id="j1")


def test_operational_fallback() -> None:
    repo = MemoryJobRepository()
    repo.save(_job("op-1"))
    r = ResultContextResolver(repo).resolve(aisle=_aisle(op_job="op-1"), explicit_job_id=None)
    assert r.job_id_for_slice == "op-1"
    assert r.source == "operational"


def test_operational_job_missing_raises() -> None:
    with pytest.raises(JobNotFoundError):
        ResultContextResolver(MemoryJobRepository()).resolve(
            aisle=_aisle(op_job="missing-op"), explicit_job_id=None
        )


def test_operational_job_wrong_aisle_raises() -> None:
    repo = MemoryJobRepository()
    repo.save(_job("j-op", aisle_id="other-aisle"))
    with pytest.raises(JobDoesNotBelongToAisleError):
        ResultContextResolver(repo).resolve(aisle=_aisle(op_job="j-op"), explicit_job_id=None)


def test_legacy_fallback() -> None:
    r = ResultContextResolver(MemoryJobRepository()).resolve(aisle=_aisle(op_job=None), explicit_job_id=None)
    assert r.job_id_for_slice is None
    assert r.source == "legacy"


def test_explicit_empty_string_treated_as_omitted() -> None:
    repo = MemoryJobRepository()
    repo.save(_job("op-1"))
    r = ResultContextResolver(repo).resolve(aisle=_aisle(op_job="op-1"), explicit_job_id="   ")
    assert r.source == "operational"
