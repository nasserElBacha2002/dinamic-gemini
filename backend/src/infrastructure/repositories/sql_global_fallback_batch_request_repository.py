"""SQL Server GlobalFallbackBatchRequestRepository."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from src.application.ports.global_fallback_batch_request_repository import (
    GlobalFallbackBatchRequestRepository,
)
from src.domain.image_processing.global_fallback_batch_request import (
    GlobalFallbackBatchRequest,
    GlobalFallbackBatchStatus,
)


def _loads(raw: Any, default: Any) -> Any:
    if raw is None:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _row_to_entity(row: dict[str, Any]) -> GlobalFallbackBatchRequest:
    return GlobalFallbackBatchRequest(
        id=str(row["id"]),
        job_id=str(row["job_id"]),
        execution_id=str(row["execution_id"]),
        attempt=int(row["attempt"]),
        batch_index=int(row["batch_index"]),
        batch_count=int(row["batch_count"]),
        batch_fingerprint=str(row["batch_fingerprint"]),
        status=GlobalFallbackBatchStatus(str(row["status"])),
        ordered_asset_ids=list(_loads(row.get("ordered_asset_ids_json"), [])),
        provider=str(row["provider"]),
        model=str(row["model"]) if row.get("model") is not None else None,
        schema_version=str(row["schema_version"]),
        configuration_fingerprint=str(row["configuration_fingerprint"]),
        prompt_fingerprint=str(row["prompt_fingerprint"]),
        prepared_image_hashes=list(_loads(row.get("prepared_image_hashes_json"), [])),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        provider_request_id=row.get("provider_request_id"),
        response_sha256=row.get("response_sha256"),
        normalized_response_json=_loads(row.get("normalized_response_json"), None),
        frame_to_asset_map=dict(_loads(row.get("frame_to_asset_map_json"), {})),
        merge_plan_json=_loads(row.get("merge_plan_json"), None),
        applied_operation_keys=list(_loads(row.get("applied_operation_keys_json"), [])),
        error_code=row.get("error_code"),
        error_message=row.get("error_message"),
        worker_token=row.get("worker_token"),
        estimated_cost=row.get("estimated_cost"),
        prompt_tokens=row.get("prompt_tokens"),
        response_tokens=row.get("response_tokens"),
        duration_ms=row.get("duration_ms"),
    )


class SqlGlobalFallbackBatchRequestRepository(GlobalFallbackBatchRequestRepository):
    def __init__(self, sql_client: Any) -> None:
        self._sql = sql_client

    def save(self, request: GlobalFallbackBatchRequest) -> None:
        params = self._params(request)
        existing = self.get_by_id(request.id)
        if existing is None:
            self._sql.execute(
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
                    :id, :job_id, :execution_id, :attempt, :batch_index, :batch_count,
                    :batch_fingerprint, :status, :ordered_asset_ids_json, :provider, :model,
                    :schema_version, :configuration_fingerprint, :prompt_fingerprint,
                    :prepared_image_hashes_json, :provider_request_id, :response_sha256,
                    :normalized_response_json, :frame_to_asset_map_json, :merge_plan_json,
                    :applied_operation_keys_json, :error_code, :error_message, :worker_token,
                    :estimated_cost, :prompt_tokens, :response_tokens, :duration_ms,
                    :created_at, :updated_at
                )
                """,
                params,
            )
            return
        self._sql.execute(
            """
            UPDATE global_fallback_batch_requests SET
                status=:status,
                ordered_asset_ids_json=:ordered_asset_ids_json,
                provider_request_id=:provider_request_id,
                response_sha256=:response_sha256,
                normalized_response_json=:normalized_response_json,
                frame_to_asset_map_json=:frame_to_asset_map_json,
                merge_plan_json=:merge_plan_json,
                applied_operation_keys_json=:applied_operation_keys_json,
                error_code=:error_code,
                error_message=:error_message,
                worker_token=:worker_token,
                estimated_cost=:estimated_cost,
                prompt_tokens=:prompt_tokens,
                response_tokens=:response_tokens,
                duration_ms=:duration_ms,
                updated_at=:updated_at
            WHERE id=:id
            """,
            params,
        )

    def get_by_id(self, request_id: str) -> GlobalFallbackBatchRequest | None:
        rows = self._sql.fetch_all(
            "SELECT * FROM global_fallback_batch_requests WHERE id = :id",
            {"id": request_id},
        )
        if not rows:
            return None
        return _row_to_entity(rows[0])

    def get_by_fingerprint(
        self,
        *,
        job_id: str,
        execution_id: str,
        batch_fingerprint: str,
    ) -> GlobalFallbackBatchRequest | None:
        rows = self._sql.fetch_all(
            """
            SELECT * FROM global_fallback_batch_requests
            WHERE job_id=:job_id AND execution_id=:execution_id
              AND batch_fingerprint=:batch_fingerprint
            """,
            {
                "job_id": job_id,
                "execution_id": execution_id,
                "batch_fingerprint": batch_fingerprint,
            },
        )
        if not rows:
            return None
        return _row_to_entity(rows[0])

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
        except Exception:
            # Unique constraint race — reload.
            return None
        return self.get_by_id(request.id)

    def list_by_job(self, job_id: str) -> Sequence[GlobalFallbackBatchRequest]:
        rows = self._sql.fetch_all(
            """
            SELECT * FROM global_fallback_batch_requests
            WHERE job_id=:job_id
            ORDER BY batch_index ASC, created_at ASC
            """,
            {"job_id": job_id},
        )
        return [_row_to_entity(r) for r in rows]

    def append_applied_operation_key(self, request_id: str, *, operation_key: str) -> bool:
        row = self.get_by_id(request_id)
        if row is None:
            return False
        if operation_key in row.applied_operation_keys:
            return False
        row.applied_operation_keys.append(operation_key)
        row.updated_at = datetime.utcnow()
        self.save(row)
        return True

    @staticmethod
    def _params(request: GlobalFallbackBatchRequest) -> dict[str, Any]:
        return {
            "id": request.id,
            "job_id": request.job_id,
            "execution_id": request.execution_id,
            "attempt": request.attempt,
            "batch_index": request.batch_index,
            "batch_count": request.batch_count,
            "batch_fingerprint": request.batch_fingerprint,
            "status": request.status.value,
            "ordered_asset_ids_json": json.dumps(request.ordered_asset_ids),
            "provider": request.provider,
            "model": request.model,
            "schema_version": request.schema_version,
            "configuration_fingerprint": request.configuration_fingerprint,
            "prompt_fingerprint": request.prompt_fingerprint,
            "prepared_image_hashes_json": json.dumps(request.prepared_image_hashes),
            "provider_request_id": request.provider_request_id,
            "response_sha256": request.response_sha256,
            "normalized_response_json": json.dumps(request.normalized_response_json)
            if request.normalized_response_json is not None
            else None,
            "frame_to_asset_map_json": json.dumps(request.frame_to_asset_map),
            "merge_plan_json": json.dumps(request.merge_plan_json)
            if request.merge_plan_json is not None
            else None,
            "applied_operation_keys_json": json.dumps(request.applied_operation_keys),
            "error_code": request.error_code,
            "error_message": request.error_message,
            "worker_token": request.worker_token,
            "estimated_cost": request.estimated_cost,
            "prompt_tokens": request.prompt_tokens,
            "response_tokens": request.response_tokens,
            "duration_ms": request.duration_ms,
            "created_at": request.created_at,
            "updated_at": request.updated_at,
        }
