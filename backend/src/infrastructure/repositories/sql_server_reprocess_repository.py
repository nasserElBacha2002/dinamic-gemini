"""SQL Server repository for Phase 7 server reprocess (no silent memory fallback)."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from src.database.sqlserver import SqlServerClient
from src.domain.server_reprocess.entities import (
    ServerReprocessAdoption,
    ServerReprocessAdoptionItem,
    ServerReprocessProposal,
    ServerReprocessRun,
    ServerReprocessRunAsset,
)
from src.infrastructure.repositories.db_row_text import normalize_db_str, optional_nonempty_db_str

logger = logging.getLogger(__name__)

_RUN_COLS = (
    "id, request_id, inventory_id, aisle_id, source_session_id, company_id, run_type, strategy, "
    "scope_type, scope_json, snapshot_json, processing_mode, reason, status, review_status, "
    "requested_by, requested_at, started_at, completed_at, canceled_at, failed_at, failure_code, "
    "failure_message, pipeline_version, model_version, prompt_version, supplier_profile_id, "
    "linked_job_id, has_prior_authority, row_version, created_at, updated_at"
)

_CHANGE_TYPES = frozenset(
    {
        "CODE_CHANGED",
        "QUANTITY_CHANGED",
        "CODE_AND_QUANTITY_CHANGED",
        "PREVIOUS_UNRESOLVED_REMOTE_RESOLVED",
        "PREVIOUS_RESOLVED_REMOTE_UNRESOLVED",
        "REMOTE_AMBIGUOUS",
        "NO_PREVIOUS_RESULT",
    }
)


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _parse_json(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    text = str(raw).strip()
    if not text:
        return {}
    data = json.loads(text)
    return data if isinstance(data, dict) else {}


def _run_from_row(row) -> ServerReprocessRun:
    return ServerReprocessRun(
        id=normalize_db_str(getattr(row, "id", None)),
        request_id=normalize_db_str(getattr(row, "request_id", None)),
        inventory_id=normalize_db_str(getattr(row, "inventory_id", None)),
        aisle_id=normalize_db_str(getattr(row, "aisle_id", None)),
        source_session_id=optional_nonempty_db_str(getattr(row, "source_session_id", None)),
        company_id=optional_nonempty_db_str(getattr(row, "company_id", None)),
        run_type=normalize_db_str(getattr(row, "run_type", None)),
        strategy=optional_nonempty_db_str(getattr(row, "strategy", None)),
        scope_type=normalize_db_str(getattr(row, "scope_type", None)),
        scope_json=_parse_json(getattr(row, "scope_json", None)),
        snapshot_json=_parse_json(getattr(row, "snapshot_json", None)),
        processing_mode=normalize_db_str(getattr(row, "processing_mode", None)),
        reason=normalize_db_str(getattr(row, "reason", None)),
        status=normalize_db_str(getattr(row, "status", None)),
        review_status=normalize_db_str(getattr(row, "review_status", None)),
        requested_by=normalize_db_str(getattr(row, "requested_by", None)),
        requested_at=_ensure_utc(getattr(row, "requested_at", None)),  # type: ignore[arg-type]
        started_at=_ensure_utc(getattr(row, "started_at", None)),
        completed_at=_ensure_utc(getattr(row, "completed_at", None)),
        canceled_at=_ensure_utc(getattr(row, "canceled_at", None)),
        failed_at=_ensure_utc(getattr(row, "failed_at", None)),
        failure_code=optional_nonempty_db_str(getattr(row, "failure_code", None)),
        failure_message=optional_nonempty_db_str(getattr(row, "failure_message", None)),
        pipeline_version=optional_nonempty_db_str(getattr(row, "pipeline_version", None)),
        model_version=optional_nonempty_db_str(getattr(row, "model_version", None)),
        prompt_version=optional_nonempty_db_str(getattr(row, "prompt_version", None)),
        supplier_profile_id=optional_nonempty_db_str(getattr(row, "supplier_profile_id", None)),
        linked_job_id=optional_nonempty_db_str(getattr(row, "linked_job_id", None)),
        has_prior_authority=bool(getattr(row, "has_prior_authority", False)),
        row_version=int(getattr(row, "row_version", 1) or 1),
        created_at=_ensure_utc(getattr(row, "created_at", None)),  # type: ignore[arg-type]
        updated_at=_ensure_utc(getattr(row, "updated_at", None)),  # type: ignore[arg-type]
    )


def _proposal_from_row(row) -> ServerReprocessProposal:
    qty = getattr(row, "quantity", None)
    conf = getattr(row, "confidence", None)
    return ServerReprocessProposal(
        id=normalize_db_str(getattr(row, "id", None)),
        run_id=normalize_db_str(getattr(row, "run_id", None)),
        asset_id=normalize_db_str(getattr(row, "asset_id", None)),
        remote_result_id=optional_nonempty_db_str(getattr(row, "remote_result_id", None)),
        previous_result_id=optional_nonempty_db_str(getattr(row, "previous_result_id", None)),
        previous_position_id=optional_nonempty_db_str(getattr(row, "previous_position_id", None)),
        status=normalize_db_str(getattr(row, "status", None)),
        difference_type=normalize_db_str(getattr(row, "difference_type", None)),
        internal_code=optional_nonempty_db_str(getattr(row, "internal_code", None)),
        quantity=float(qty) if qty is not None else None,
        confidence=float(conf) if conf is not None else None,
        source=optional_nonempty_db_str(getattr(row, "source", None)),
        pipeline_version=optional_nonempty_db_str(getattr(row, "pipeline_version", None)),
        remote_resolved=bool(getattr(row, "remote_resolved", False)),
        review_status=normalize_db_str(getattr(row, "review_status", None)),
        created_at=_ensure_utc(getattr(row, "created_at", None)),  # type: ignore[arg-type]
        updated_at=_ensure_utc(getattr(row, "updated_at", None)),  # type: ignore[arg-type]
    )


def _adoption_from_row(row) -> ServerReprocessAdoption:
    return ServerReprocessAdoption(
        id=normalize_db_str(getattr(row, "id", None)),
        adoption_id=normalize_db_str(getattr(row, "adoption_id", None)),
        run_id=normalize_db_str(getattr(row, "run_id", None)),
        inventory_id=normalize_db_str(getattr(row, "inventory_id", None)),
        aisle_id=normalize_db_str(getattr(row, "aisle_id", None)),
        status=normalize_db_str(getattr(row, "status", None)),
        adopted_by=normalize_db_str(getattr(row, "adopted_by", None)),
        adopted_at=_ensure_utc(getattr(row, "adopted_at", None)),  # type: ignore[arg-type]
        item_count=int(getattr(row, "item_count", 0) or 0),
        adopted_count=int(getattr(row, "adopted_count", 0) or 0),
        kept_count=int(getattr(row, "kept_count", 0) or 0),
        deferred_count=int(getattr(row, "deferred_count", 0) or 0),
        row_version=int(getattr(row, "row_version", 1) or 1),
        created_at=_ensure_utc(getattr(row, "created_at", None)),  # type: ignore[arg-type]
        updated_at=_ensure_utc(getattr(row, "updated_at", None)),  # type: ignore[arg-type]
        content_hash=normalize_db_str(getattr(row, "content_hash", None) or ""),
    )


class SqlServerReprocessRepository:
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def get_run(self, run_id: str) -> ServerReprocessRun | None:
        with self._client.cursor() as cur:
            cur.execute(
                f"SELECT {_RUN_COLS} FROM server_reprocess_runs WHERE id = ?",
                ((run_id or "").strip(),),
            )
            row = cur.fetchone()
        return _run_from_row(row) if row else None

    def get_run_by_request_id(self, request_id: str) -> ServerReprocessRun | None:
        with self._client.cursor() as cur:
            cur.execute(
                f"SELECT {_RUN_COLS} FROM server_reprocess_runs WHERE request_id = ?",
                ((request_id or "").strip(),),
            )
            row = cur.fetchone()
        return _run_from_row(row) if row else None

    def list_runs_for_aisle(self, aisle_id: str) -> Sequence[ServerReprocessRun]:
        with self._client.cursor() as cur:
            cur.execute(
                f"SELECT {_RUN_COLS} FROM server_reprocess_runs "
                "WHERE aisle_id = ? ORDER BY requested_at DESC",
                ((aisle_id or "").strip(),),
            )
            rows = cur.fetchall()
        return [_run_from_row(r) for r in rows]

    def save_run(
        self,
        *,
        run: ServerReprocessRun,
        assets: Sequence[ServerReprocessRunAsset],
    ) -> ServerReprocessRun:
        with self._client.begin_transaction() as txn:
            cur = txn.connection.cursor()
            cur.execute(
                "SELECT id FROM server_reprocess_runs WITH (UPDLOCK, HOLDLOCK) "
                "WHERE request_id = ?",
                (run.request_id,),
            )
            existing = cur.fetchone()
            if existing is not None:
                existing_id = normalize_db_str(getattr(existing, "id", None))
                if existing_id != run.id:
                    raise ValueError("REQUEST_ID_CONFLICT")
                return self.get_run(run.id) or run

            cur.execute(
                "INSERT INTO server_reprocess_runs ("
                "id, request_id, inventory_id, aisle_id, source_session_id, company_id, "
                "run_type, strategy, scope_type, scope_json, snapshot_json, processing_mode, "
                "reason, status, review_status, requested_by, requested_at, started_at, "
                "completed_at, canceled_at, failed_at, failure_code, failure_message, "
                "pipeline_version, model_version, prompt_version, supplier_profile_id, "
                "linked_job_id, has_prior_authority, row_version, created_at, updated_at"
                ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    run.id,
                    run.request_id,
                    run.inventory_id,
                    run.aisle_id,
                    run.source_session_id,
                    run.company_id,
                    run.run_type,
                    run.strategy,
                    run.scope_type,
                    json.dumps(run.scope_json, ensure_ascii=False),
                    json.dumps(run.snapshot_json, ensure_ascii=False),
                    run.processing_mode,
                    run.reason,
                    run.status,
                    run.review_status,
                    run.requested_by,
                    run.requested_at,
                    run.started_at,
                    run.completed_at,
                    run.canceled_at,
                    run.failed_at,
                    run.failure_code,
                    run.failure_message,
                    run.pipeline_version,
                    run.model_version,
                    run.prompt_version,
                    run.supplier_profile_id,
                    run.linked_job_id,
                    1 if run.has_prior_authority else 0,
                    run.row_version,
                    run.created_at,
                    run.updated_at,
                ),
            )
            for asset in assets:
                cur.execute(
                    "INSERT INTO server_reprocess_run_assets ("
                    "id, run_id, asset_id, asset_hash, previous_result_id, previous_position_id, "
                    "previous_internal_code, previous_quantity, previous_resolved, created_at"
                    ") VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        asset.id,
                        asset.run_id,
                        asset.asset_id,
                        asset.asset_hash,
                        asset.previous_result_id,
                        asset.previous_position_id,
                        asset.previous_internal_code,
                        asset.previous_quantity,
                        1 if asset.previous_resolved else 0,
                        asset.created_at,
                    ),
                )
        return run

    def update_run(self, run: ServerReprocessRun) -> ServerReprocessRun:
        with self._client.begin_transaction() as txn:
            cur = txn.connection.cursor()
            cur.execute(
                "UPDATE server_reprocess_runs SET "
                "status = ?, review_status = ?, started_at = ?, completed_at = ?, "
                "canceled_at = ?, failed_at = ?, failure_code = ?, failure_message = ?, "
                "linked_job_id = ?, row_version = ?, updated_at = ?, "
                "scope_json = ?, snapshot_json = ? "
                "WHERE id = ? AND row_version = ?",
                (
                    run.status,
                    run.review_status,
                    run.started_at,
                    run.completed_at,
                    run.canceled_at,
                    run.failed_at,
                    run.failure_code,
                    run.failure_message,
                    run.linked_job_id,
                    run.row_version,
                    run.updated_at,
                    json.dumps(run.scope_json, ensure_ascii=False),
                    json.dumps(run.snapshot_json, ensure_ascii=False),
                    run.id,
                    run.row_version - 1 if run.row_version > 1 else 1,
                ),
            )
            if cur.rowcount == 0:
                # Allow first update when row_version stayed 1
                cur.execute(
                    "UPDATE server_reprocess_runs SET "
                    "status = ?, review_status = ?, started_at = ?, completed_at = ?, "
                    "canceled_at = ?, failed_at = ?, failure_code = ?, failure_message = ?, "
                    "linked_job_id = ?, row_version = ?, updated_at = ? "
                    "WHERE id = ?",
                    (
                        run.status,
                        run.review_status,
                        run.started_at,
                        run.completed_at,
                        run.canceled_at,
                        run.failed_at,
                        run.failure_code,
                        run.failure_message,
                        run.linked_job_id,
                        run.row_version,
                        run.updated_at,
                        run.id,
                    ),
                )
        return run

    def list_run_assets(self, run_id: str) -> Sequence[ServerReprocessRunAsset]:
        with self._client.cursor() as cur:
            cur.execute(
                "SELECT id, run_id, asset_id, asset_hash, previous_result_id, previous_position_id, "
                "previous_internal_code, previous_quantity, previous_resolved, created_at "
                "FROM server_reprocess_run_assets WHERE run_id = ?",
                ((run_id or "").strip(),),
            )
            rows = cur.fetchall()
        out: list[ServerReprocessRunAsset] = []
        for r in rows:
            qty = getattr(r, "previous_quantity", None)
            out.append(
                ServerReprocessRunAsset(
                    id=normalize_db_str(getattr(r, "id", None)),
                    run_id=normalize_db_str(getattr(r, "run_id", None)),
                    asset_id=normalize_db_str(getattr(r, "asset_id", None)),
                    asset_hash=optional_nonempty_db_str(getattr(r, "asset_hash", None)),
                    previous_result_id=optional_nonempty_db_str(
                        getattr(r, "previous_result_id", None)
                    ),
                    previous_position_id=optional_nonempty_db_str(
                        getattr(r, "previous_position_id", None)
                    ),
                    previous_internal_code=optional_nonempty_db_str(
                        getattr(r, "previous_internal_code", None)
                    ),
                    previous_quantity=float(qty) if qty is not None else None,
                    previous_resolved=bool(getattr(r, "previous_resolved", False)),
                    created_at=_ensure_utc(getattr(r, "created_at", None)),  # type: ignore[arg-type]
                )
            )
        return out

    def replace_proposals(
        self,
        *,
        run_id: str,
        proposals: Sequence[ServerReprocessProposal],
    ) -> Sequence[ServerReprocessProposal]:
        with self._client.begin_transaction() as txn:
            cur = txn.connection.cursor()
            cur.execute(
                "DELETE FROM server_reprocess_proposals WHERE run_id = ?",
                (run_id.strip(),),
            )
            for p in proposals:
                cur.execute(
                    "INSERT INTO server_reprocess_proposals ("
                    "id, run_id, asset_id, remote_result_id, previous_result_id, "
                    "previous_position_id, status, difference_type, internal_code, quantity, "
                    "confidence, source, pipeline_version, remote_resolved, review_status, "
                    "created_at, updated_at"
                    ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        p.id,
                        p.run_id,
                        p.asset_id,
                        p.remote_result_id,
                        p.previous_result_id,
                        p.previous_position_id,
                        p.status,
                        p.difference_type,
                        p.internal_code,
                        p.quantity,
                        p.confidence,
                        p.source,
                        p.pipeline_version,
                        1 if p.remote_resolved else 0,
                        p.review_status,
                        p.created_at,
                        p.updated_at,
                    ),
                )
        return list(proposals)

    def list_proposals(
        self,
        run_id: str,
        *,
        difference_type: str | None = None,
        asset_id: str | None = None,
        review_status: str | None = None,
        has_change: bool | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[ServerReprocessProposal]:
        clauses = ["run_id = ?"]
        params: list[Any] = [run_id.strip()]
        if difference_type:
            clauses.append("difference_type = ?")
            params.append(difference_type)
        if asset_id:
            clauses.append("asset_id = ?")
            params.append(asset_id.strip())
        if review_status:
            clauses.append("review_status = ?")
            params.append(review_status)
        if has_change is True:
            placeholders = ",".join("?" for _ in _CHANGE_TYPES)
            clauses.append(f"difference_type IN ({placeholders})")
            params.extend(sorted(_CHANGE_TYPES))
        elif has_change is False:
            clauses.append("difference_type = ?")
            params.append("SAME_RESULT")
        where = " AND ".join(clauses)
        sql = (
            "SELECT id, run_id, asset_id, remote_result_id, previous_result_id, "
            "previous_position_id, status, difference_type, internal_code, quantity, "
            "confidence, source, pipeline_version, remote_resolved, review_status, "
            "created_at, updated_at FROM server_reprocess_proposals "
            f"WHERE {where} ORDER BY asset_id "
            "OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
        )
        params.extend([max(0, offset), max(1, limit)])
        with self._client.cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
        return [_proposal_from_row(r) for r in rows]

    def get_proposal(self, proposal_id: str) -> ServerReprocessProposal | None:
        with self._client.cursor() as cur:
            cur.execute(
                "SELECT id, run_id, asset_id, remote_result_id, previous_result_id, "
                "previous_position_id, status, difference_type, internal_code, quantity, "
                "confidence, source, pipeline_version, remote_resolved, review_status, "
                "created_at, updated_at FROM server_reprocess_proposals WHERE id = ?",
                ((proposal_id or "").strip(),),
            )
            row = cur.fetchone()
        return _proposal_from_row(row) if row else None

    def update_proposal(self, proposal: ServerReprocessProposal) -> ServerReprocessProposal:
        with self._client.begin_transaction() as txn:
            cur = txn.connection.cursor()
            cur.execute(
                "UPDATE server_reprocess_proposals SET status = ?, review_status = ?, "
                "updated_at = ? WHERE id = ?",
                (proposal.status, proposal.review_status, proposal.updated_at, proposal.id),
            )
        return proposal

    def get_adoption_by_adoption_id(
        self, adoption_id: str
    ) -> ServerReprocessAdoption | None:
        with self._client.cursor() as cur:
            cur.execute(
                "SELECT id, adoption_id, run_id, inventory_id, aisle_id, status, adopted_by, "
                "adopted_at, item_count, adopted_count, kept_count, deferred_count, "
                "row_version, created_at, updated_at, "
                "ISNULL(content_hash, '') AS content_hash "
                "FROM server_reprocess_adoptions WHERE adoption_id = ?",
                ((adoption_id or "").strip(),),
            )
            row = cur.fetchone()
        return _adoption_from_row(row) if row else None

    def save_adoption(
        self,
        *,
        adoption: ServerReprocessAdoption,
        items: Sequence[ServerReprocessAdoptionItem],
        updated_proposals: Sequence[ServerReprocessProposal],
        updated_run: ServerReprocessRun,
    ) -> ServerReprocessAdoption:
        with self._client.begin_transaction() as txn:
            cur = txn.connection.cursor()
            cur.execute(
                "INSERT INTO server_reprocess_adoptions ("
                "id, adoption_id, run_id, inventory_id, aisle_id, status, adopted_by, "
                "adopted_at, item_count, adopted_count, kept_count, deferred_count, "
                "row_version, created_at, updated_at, content_hash"
                ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    adoption.id,
                    adoption.adoption_id,
                    adoption.run_id,
                    adoption.inventory_id,
                    adoption.aisle_id,
                    adoption.status,
                    adoption.adopted_by,
                    adoption.adopted_at,
                    adoption.item_count,
                    adoption.adopted_count,
                    adoption.kept_count,
                    adoption.deferred_count,
                    adoption.row_version,
                    adoption.created_at,
                    adoption.updated_at,
                    adoption.content_hash or "",
                ),
            )
            for item in items:
                cur.execute(
                    "INSERT INTO server_reprocess_adoption_items ("
                    "id, adoption_row_id, proposal_id, asset_id, action, "
                    "expected_previous_result_id, new_result_id, new_position_id, "
                    "edit_internal_code, edit_quantity, created_at"
                    ") VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        item.id,
                        item.adoption_row_id,
                        item.proposal_id,
                        item.asset_id,
                        item.action,
                        item.expected_previous_result_id,
                        item.new_result_id,
                        item.new_position_id,
                        item.edit_internal_code,
                        item.edit_quantity,
                        item.created_at,
                    ),
                )
            for p in updated_proposals:
                cur.execute(
                    "UPDATE server_reprocess_proposals SET status = ?, review_status = ?, "
                    "updated_at = ? WHERE id = ? AND run_id = ?",
                    (p.status, p.review_status, p.updated_at, p.id, p.run_id),
                )
            cur.execute(
                "UPDATE server_reprocess_runs SET review_status = ?, row_version = ?, "
                "updated_at = ? WHERE id = ?",
                (
                    updated_run.review_status,
                    updated_run.row_version,
                    updated_run.updated_at,
                    updated_run.id,
                ),
            )
        return adoption

    def try_acquire_lock(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        owner_token: str,
        expires_at: datetime,
    ) -> bool:
        now = datetime.now(timezone.utc)
        with self._client.begin_transaction() as txn:
            cur = txn.connection.cursor()
            cur.execute(
                "SELECT inventory_id, owner_token, expires_at FROM server_reprocess_locks "
                "WITH (UPDLOCK, HOLDLOCK) WHERE aisle_id = ?",
                (aisle_id.strip(),),
            )
            row = cur.fetchone()
            if row is not None:
                token = normalize_db_str(getattr(row, "owner_token", None))
                exp = _ensure_utc(getattr(row, "expires_at", None))
                if token != owner_token and exp is not None and exp > now:
                    return False
                cur.execute(
                    "UPDATE server_reprocess_locks SET inventory_id = ?, owner_token = ?, "
                    "expires_at = ? WHERE aisle_id = ?",
                    (inventory_id, owner_token, expires_at, aisle_id.strip()),
                )
            else:
                cur.execute(
                    "INSERT INTO server_reprocess_locks (inventory_id, aisle_id, owner_token, "
                    "expires_at) VALUES (?,?,?,?)",
                    (inventory_id, aisle_id.strip(), owner_token, expires_at),
                )
        return True

    def release_lock(self, *, aisle_id: str, owner_token: str) -> None:
        with self._client.begin_transaction() as txn:
            cur = txn.connection.cursor()
            cur.execute(
                "DELETE FROM server_reprocess_locks WHERE aisle_id = ? AND owner_token = ?",
                (aisle_id.strip(), owner_token),
            )
