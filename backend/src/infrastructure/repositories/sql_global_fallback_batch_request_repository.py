"""SQL Server GlobalFallbackBatchRequestRepository.

Uses SqlServerClient.cursor() with ``?`` placeholders (same pattern as other SQL repos).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

import pyodbc

from src.application.ports.global_fallback_batch_request_repository import (
    GlobalFallbackBatchRequestRepository,
)
from src.database.sqlserver import SqlServerClient
from src.domain.image_processing.global_fallback_batch_request import (
    GlobalFallbackBatchRequest,
    GlobalFallbackBatchStatus,
)
from src.infrastructure.repositories.db_row_text import normalize_db_str

logger = logging.getLogger(__name__)

_SELECT_FIELDS = (
    "id, job_id, execution_id, attempt, batch_index, batch_count, batch_fingerprint, "
    "status, ordered_asset_ids_json, provider, model, schema_version, "
    "configuration_fingerprint, prompt_fingerprint, prepared_image_hashes_json, "
    "provider_request_id, response_sha256, normalized_response_json, "
    "frame_to_asset_map_json, merge_plan_json, applied_operation_keys_json, "
    "error_code, error_message, worker_token, estimated_cost, prompt_tokens, "
    "response_tokens, duration_ms, created_at, updated_at"
)


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _loads(raw: Any, default: Any) -> Any:
    if raw is None:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=True, default=str)


def _is_fingerprint_unique_violation(exc: pyodbc.IntegrityError) -> bool:
    return "uq_gfbr_job_exec_fingerprint" in str(exc).lower()


def _row_to_entity(row: object) -> GlobalFallbackBatchRequest:
    status_raw = normalize_db_str(getattr(row, "status", None)) or "PREPARED"
    try:
        status = GlobalFallbackBatchStatus(status_raw)
    except ValueError:
        logger.error("invalid_persisted_global_fallback_batch_status value=%s", status_raw)
        raise
    model = normalize_db_str(getattr(row, "model", None))
    return GlobalFallbackBatchRequest(
        id=str(getattr(row, "id")),
        job_id=str(getattr(row, "job_id")),
        execution_id=str(getattr(row, "execution_id")),
        attempt=int(getattr(row, "attempt")),
        batch_index=int(getattr(row, "batch_index")),
        batch_count=int(getattr(row, "batch_count")),
        batch_fingerprint=str(getattr(row, "batch_fingerprint")),
        status=status,
        ordered_asset_ids=list(_loads(getattr(row, "ordered_asset_ids_json", None), [])),
        provider=str(getattr(row, "provider") or ""),
        model=model,
        schema_version=str(getattr(row, "schema_version") or ""),
        configuration_fingerprint=str(getattr(row, "configuration_fingerprint") or ""),
        prompt_fingerprint=str(getattr(row, "prompt_fingerprint") or ""),
        prepared_image_hashes=list(
            _loads(getattr(row, "prepared_image_hashes_json", None), [])
        ),
        created_at=_ensure_utc(getattr(row, "created_at")) or datetime.now(timezone.utc),
        updated_at=_ensure_utc(getattr(row, "updated_at")) or datetime.now(timezone.utc),
        provider_request_id=normalize_db_str(getattr(row, "provider_request_id", None)),
        response_sha256=normalize_db_str(getattr(row, "response_sha256", None)),
        normalized_response_json=_loads(getattr(row, "normalized_response_json", None), None),
        frame_to_asset_map=dict(_loads(getattr(row, "frame_to_asset_map_json", None), {})),
        merge_plan_json=_loads(getattr(row, "merge_plan_json", None), None),
        applied_operation_keys=list(
            _loads(getattr(row, "applied_operation_keys_json", None), [])
        ),
        error_code=normalize_db_str(getattr(row, "error_code", None)),
        error_message=normalize_db_str(getattr(row, "error_message", None)),
        worker_token=normalize_db_str(getattr(row, "worker_token", None)),
        estimated_cost=getattr(row, "estimated_cost", None),
        prompt_tokens=getattr(row, "prompt_tokens", None),
        response_tokens=getattr(row, "response_tokens", None),
        duration_ms=getattr(row, "duration_ms", None),
    )


class SqlGlobalFallbackBatchRequestRepository(GlobalFallbackBatchRequestRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def save(self, request: GlobalFallbackBatchRequest) -> None:
        existing = self.get_by_id(request.id)
        params = self._params_tuple(request)
        with self._client.cursor() as cur:
            if existing is None:
                cur.execute(
                    """
                    INSERT INTO global_fallback_batch_requests (
                        id, job_id, execution_id, attempt, batch_index, batch_count,
                        batch_fingerprint, status, ordered_asset_ids_json, provider, model,
                        schema_version, configuration_fingerprint, prompt_fingerprint,
                        prepared_image_hashes_json, provider_request_id, response_sha256,
                        normalized_response_json, frame_to_asset_map_json, merge_plan_json,
                        applied_operation_keys_json, error_code, error_message, worker_token,
                        estimated_cost, prompt_tokens, response_tokens, duration_ms,
                        created_at, updated_at
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    params,
                )
                return
            cur.execute(
                """
                UPDATE global_fallback_batch_requests SET
                    status=?,
                    ordered_asset_ids_json=?,
                    provider_request_id=?,
                    response_sha256=?,
                    normalized_response_json=?,
                    frame_to_asset_map_json=?,
                    merge_plan_json=?,
                    applied_operation_keys_json=?,
                    error_code=?,
                    error_message=?,
                    worker_token=?,
                    estimated_cost=?,
                    prompt_tokens=?,
                    response_tokens=?,
                    duration_ms=?,
                    updated_at=?
                WHERE id=?
                """,
                (
                    request.status.value,
                    _dumps(request.ordered_asset_ids) or "[]",
                    request.provider_request_id,
                    request.response_sha256,
                    _dumps(request.normalized_response_json),
                    _dumps(request.frame_to_asset_map) or "{}",
                    _dumps(request.merge_plan_json),
                    _dumps(request.applied_operation_keys) or "[]",
                    request.error_code,
                    request.error_message,
                    request.worker_token,
                    request.estimated_cost,
                    request.prompt_tokens,
                    request.response_tokens,
                    request.duration_ms,
                    request.updated_at,
                    request.id,
                ),
            )

    def get_by_id(self, request_id: str) -> GlobalFallbackBatchRequest | None:
        with self._client.cursor() as cur:
            cur.execute(
                f"SELECT {_SELECT_FIELDS} FROM global_fallback_batch_requests WHERE id = ?",
                (request_id,),
            )
            row = cur.fetchone()
        return _row_to_entity(row) if row is not None else None

    def get_by_fingerprint(
        self,
        *,
        job_id: str,
        execution_id: str,
        batch_fingerprint: str,
    ) -> GlobalFallbackBatchRequest | None:
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_SELECT_FIELDS} FROM global_fallback_batch_requests
                WHERE job_id=? AND execution_id=? AND batch_fingerprint=?
                """,
                (job_id, execution_id, batch_fingerprint),
            )
            row = cur.fetchone()
        return _row_to_entity(row) if row is not None else None

    def try_insert(self, request: GlobalFallbackBatchRequest) -> GlobalFallbackBatchRequest | None:
        existing = self.get_by_fingerprint(
            job_id=request.job_id,
            execution_id=request.execution_id,
            batch_fingerprint=request.batch_fingerprint,
        )
        if existing is not None:
            return None
        try:
            self.save(request)
        except pyodbc.IntegrityError as exc:
            if _is_fingerprint_unique_violation(exc):
                return None
            raise
        return self.get_by_id(request.id)

    def list_by_job(self, job_id: str) -> Sequence[GlobalFallbackBatchRequest]:
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_SELECT_FIELDS} FROM global_fallback_batch_requests
                WHERE job_id=?
                ORDER BY batch_index ASC, created_at ASC
                """,
                (job_id,),
            )
            rows = cur.fetchall()
        return [_row_to_entity(r) for r in rows]

    def append_applied_operation_key(self, request_id: str, *, operation_key: str) -> bool:
        row = self.get_by_id(request_id)
        if row is None:
            return False
        if operation_key in row.applied_operation_keys:
            return False
        row.applied_operation_keys.append(operation_key)
        row.updated_at = datetime.now(timezone.utc)
        self.save(row)
        return True

    @staticmethod
    def _params_tuple(request: GlobalFallbackBatchRequest) -> tuple[Any, ...]:
        return (
            request.id,
            request.job_id,
            request.execution_id,
            request.attempt,
            request.batch_index,
            request.batch_count,
            request.batch_fingerprint,
            request.status.value,
            _dumps(request.ordered_asset_ids) or "[]",
            request.provider,
            request.model,
            request.schema_version,
            request.configuration_fingerprint,
            request.prompt_fingerprint,
            _dumps(request.prepared_image_hashes) or "[]",
            request.provider_request_id,
            request.response_sha256,
            _dumps(request.normalized_response_json),
            _dumps(request.frame_to_asset_map) or "{}",
            _dumps(request.merge_plan_json),
            _dumps(request.applied_operation_keys) or "[]",
            request.error_code,
            request.error_message,
            request.worker_token,
            request.estimated_cost,
            request.prompt_tokens,
            request.response_tokens,
            request.duration_ms,
            request.created_at,
            request.updated_at,
        )
