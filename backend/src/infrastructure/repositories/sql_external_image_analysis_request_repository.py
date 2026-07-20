"""SQL Server ExternalImageAnalysisRequestRepository (Phase 5 corrections)."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

import pyodbc

from src.application.ports.external_image_analysis_request_repository import (
    ExternalImageAnalysisRequestRepository,
)
from src.database.sqlserver import SqlServerClient
from src.domain.image_processing.external_image_analysis_request import (
    ExternalImageAnalysisRequest,
    ExternalRequestStatus,
)
from src.infrastructure.repositories.db_row_text import normalize_db_str

logger = logging.getLogger(__name__)

_SELECT = (
    "id, idempotency_key, job_id, asset_id, provider, model, prompt_key, prompt_version, "
    "configuration_snapshot_version, status, attempt_id, worker_token, "
    "request_image_sha256, provider_response_sha256, normalized_result_sha256, "
    "normalized_result_json, validation_result_json, usage_json, estimated_cost, "
    "duration_ms, confidence, error_code, error_message, position_id, active_result_id, "
    "client_id, created_at, updated_at"
)


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _loads(raw: object) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    text = str(raw).strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _dumps(data: dict[str, Any] | None) -> str | None:
    if data is None:
        return None
    return json.dumps(data)


def _row_to_entity(row: object) -> ExternalImageAnalysisRequest:
    status_raw = normalize_db_str(getattr(row, "status", None)) or "CLAIMED"
    try:
        status = ExternalRequestStatus(status_raw)
    except ValueError:
        logger.error("invalid_eiar_status value=%s id=%s", status_raw, getattr(row, "id", None))
        raise
    return ExternalImageAnalysisRequest(
        id=str(getattr(row, "id")),
        idempotency_key=str(getattr(row, "idempotency_key")),
        job_id=str(getattr(row, "job_id")),
        asset_id=str(getattr(row, "asset_id")),
        provider=str(getattr(row, "provider") or ""),
        model=normalize_db_str(getattr(row, "model", None)),
        prompt_key=normalize_db_str(getattr(row, "prompt_key", None)),
        prompt_version=normalize_db_str(getattr(row, "prompt_version", None)),
        configuration_snapshot_version=getattr(row, "configuration_snapshot_version", None),
        status=status,
        attempt_id=normalize_db_str(getattr(row, "attempt_id", None)),
        worker_token=normalize_db_str(getattr(row, "worker_token", None)),
        request_image_sha256=normalize_db_str(getattr(row, "request_image_sha256", None)),
        provider_response_sha256=normalize_db_str(getattr(row, "provider_response_sha256", None)),
        normalized_result_sha256=normalize_db_str(getattr(row, "normalized_result_sha256", None)),
        normalized_result=_loads(getattr(row, "normalized_result_json", None)),
        validation_result=_loads(getattr(row, "validation_result_json", None)),
        usage=_loads(getattr(row, "usage_json", None)),
        estimated_cost=getattr(row, "estimated_cost", None),
        duration_ms=getattr(row, "duration_ms", None),
        confidence=getattr(row, "confidence", None),
        error_code=normalize_db_str(getattr(row, "error_code", None)),
        error_message=normalize_db_str(getattr(row, "error_message", None)),
        position_id=normalize_db_str(getattr(row, "position_id", None)),
        active_result_id=normalize_db_str(getattr(row, "active_result_id", None)),
        client_id=normalize_db_str(getattr(row, "client_id", None)),
        created_at=_ensure_utc(getattr(row, "created_at", None)) or datetime.now(timezone.utc),
        updated_at=_ensure_utc(getattr(row, "updated_at", None)) or datetime.now(timezone.utc),
    )


class SqlExternalImageAnalysisRequestRepository(ExternalImageAnalysisRequestRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def save(self, request: ExternalImageAnalysisRequest) -> None:
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE external_image_analysis_requests SET
                    status = ?, attempt_id = ?, worker_token = ?,
                    request_image_sha256 = ?, provider_response_sha256 = ?,
                    normalized_result_sha256 = ?, normalized_result_json = ?,
                    validation_result_json = ?, usage_json = ?, estimated_cost = ?,
                    duration_ms = ?, confidence = ?, error_code = ?, error_message = ?,
                    position_id = ?, active_result_id = ?, client_id = ?,
                    provider = ?, model = ?, prompt_key = ?, prompt_version = ?,
                    configuration_snapshot_version = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    request.status.value,
                    request.attempt_id,
                    request.worker_token,
                    request.request_image_sha256,
                    request.provider_response_sha256,
                    request.normalized_result_sha256,
                    _dumps(request.normalized_result),
                    _dumps(request.validation_result),
                    _dumps(request.usage),
                    request.estimated_cost,
                    request.duration_ms,
                    request.confidence,
                    request.error_code,
                    (request.error_message or "")[:2048] if request.error_message else None,
                    request.position_id,
                    request.active_result_id,
                    request.client_id,
                    request.provider,
                    request.model,
                    request.prompt_key,
                    request.prompt_version,
                    request.configuration_snapshot_version,
                    request.updated_at.replace(tzinfo=None)
                    if request.updated_at.tzinfo
                    else request.updated_at,
                    request.id,
                ),
            )
            if cur.rowcount == 0:
                self._insert(cur, request)

    def _insert(self, cur, request: ExternalImageAnalysisRequest) -> None:
        cur.execute(
            f"""
            INSERT INTO external_image_analysis_requests (
                {_SELECT}
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request.id,
                request.idempotency_key,
                request.job_id,
                request.asset_id,
                request.provider,
                request.model,
                request.prompt_key,
                request.prompt_version,
                request.configuration_snapshot_version,
                request.status.value,
                request.attempt_id,
                request.worker_token,
                request.request_image_sha256,
                request.provider_response_sha256,
                request.normalized_result_sha256,
                _dumps(request.normalized_result),
                _dumps(request.validation_result),
                _dumps(request.usage),
                request.estimated_cost,
                request.duration_ms,
                request.confidence,
                request.error_code,
                (request.error_message or "")[:2048] if request.error_message else None,
                request.position_id,
                request.active_result_id,
                request.client_id,
                request.created_at.replace(tzinfo=None)
                if request.created_at.tzinfo
                else request.created_at,
                request.updated_at.replace(tzinfo=None)
                if request.updated_at.tzinfo
                else request.updated_at,
            ),
        )

    def get_by_id(self, request_id: str) -> ExternalImageAnalysisRequest | None:
        with self._client.cursor() as cur:
            cur.execute(
                f"SELECT {_SELECT} FROM external_image_analysis_requests WHERE id = ?",
                (request_id,),
            )
            row = cur.fetchone()
        return _row_to_entity(row) if row else None

    def get_by_idempotency_key(
        self, idempotency_key: str
    ) -> ExternalImageAnalysisRequest | None:
        with self._client.cursor() as cur:
            cur.execute(
                f"SELECT {_SELECT} FROM external_image_analysis_requests WHERE idempotency_key = ?",
                (idempotency_key,),
            )
            row = cur.fetchone()
        return _row_to_entity(row) if row else None

    def try_claim(
        self, *, request: ExternalImageAnalysisRequest
    ) -> ExternalImageAnalysisRequest:
        with self._client.cursor() as cur:
            try:
                self._insert(cur, request)
                return request
            except pyodbc.IntegrityError:
                cur.execute(
                    f"SELECT {_SELECT} FROM external_image_analysis_requests WHERE idempotency_key = ?",
                    (request.idempotency_key,),
                )
                row = cur.fetchone()
                if row is None:
                    raise
                return _row_to_entity(row)

    def list_by_job(self, job_id: str) -> Sequence[ExternalImageAnalysisRequest]:
        with self._client.cursor() as cur:
            cur.execute(
                f"SELECT {_SELECT} FROM external_image_analysis_requests WHERE job_id = ?",
                (job_id,),
            )
            rows = cur.fetchall()
        return [_row_to_entity(r) for r in rows]

    def list_by_job_and_asset(
        self, job_id: str, asset_id: str
    ) -> Sequence[ExternalImageAnalysisRequest]:
        with self._client.cursor() as cur:
            cur.execute(
                f"SELECT {_SELECT} FROM external_image_analysis_requests "
                "WHERE job_id = ? AND asset_id = ?",
                (job_id, asset_id),
            )
            rows = cur.fetchall()
        return [_row_to_entity(r) for r in rows]

    def count_by_job_statuses(
        self, job_id: str, statuses: Sequence[ExternalRequestStatus]
    ) -> int:
        if not statuses:
            return 0
        placeholders = ",".join("?" for _ in statuses)
        with self._client.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(1) AS c FROM external_image_analysis_requests "
                f"WHERE job_id = ? AND status IN ({placeholders})",
                (job_id, *[s.value for s in statuses]),
            )
            row = cur.fetchone()
        return int(getattr(row, "c", 0) or 0)


__all__ = ["SqlExternalImageAnalysisRequestRepository"]
