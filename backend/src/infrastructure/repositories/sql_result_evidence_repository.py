"""SQL Server ResultEvidenceRepository — Phase 4.6."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from src.application.ports.repositories import ResultEvidenceRepository
from src.database.sqlserver import SqlServerClient
from src.domain.result_evidence.entities import ResultEvidenceRecord, ResultEvidenceRole
from src.domain.result_evidence.validation import validate_result_evidence_record
from src.infrastructure.database.sql_transaction import sql_repository_cursor


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _role_to_db(role: ResultEvidenceRole | None) -> str | None:
    return role.value if role is not None else None


def _role_from_db(raw: object) -> ResultEvidenceRole | None:
    if raw is None or not str(raw).strip():
        return None
    try:
        return ResultEvidenceRole(str(raw).strip())
    except ValueError:
        return ResultEvidenceRole.UNKNOWN


def _row_to_record(row) -> ResultEvidenceRecord:
    created = _ensure_utc(getattr(row, "created_at", None))
    updated = _ensure_utc(getattr(row, "updated_at", None))
    if created is None or updated is None:
        raise ValueError("result_evidence row missing required timestamps")
    return ResultEvidenceRecord(
        id=getattr(row, "id", "") or "",
        job_id=getattr(row, "job_id", "") or "",
        inventory_id=getattr(row, "inventory_id", "") or "",
        aisle_id=getattr(row, "aisle_id", "") or "",
        position_id=getattr(row, "position_id", None),
        entity_uid=getattr(row, "entity_uid", None),
        model_entity_id=getattr(row, "model_entity_id", None),
        raw_manifest_entry_id=getattr(row, "raw_manifest_entry_id", None),
        manifest_entry_id=getattr(row, "manifest_entry_id", None),
        raw_source_image_id=getattr(row, "raw_source_image_id", None),
        resolved_manifest_entry_id=getattr(row, "resolved_manifest_entry_id", None),
        source_image_id=getattr(row, "source_image_id", None),
        source_asset_id=getattr(row, "source_asset_id", None),
        traceability_status=getattr(row, "traceability_status", None),
        traceability_warning=getattr(row, "traceability_warning", None),
        role=_role_from_db(getattr(row, "role", None)),
        provider=getattr(row, "provider", None),
        model_name=getattr(row, "model_name", None),
        schema_version=getattr(row, "schema_version", None),
        manifest_version=getattr(row, "manifest_version", None),
        has_valid_evidence=bool(getattr(row, "has_valid_evidence", False)),
        evidence_kind=getattr(row, "evidence_kind", "") or "entity_traceability",
        created_at=created,
        updated_at=updated,
    )


class SqlResultEvidenceRepository(ResultEvidenceRepository):
    def __init__(self, client: SqlServerClient, *, connection: object | None = None) -> None:
        self._client = client
        self._connection = connection

    def save_many(self, records: list) -> None:
        if not records:
            return
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            for record in records:
                if not isinstance(record, ResultEvidenceRecord):
                    raise TypeError(f"Expected ResultEvidenceRecord, got {type(record)!r}")
                validate_result_evidence_record(record)
                created = _ensure_utc(record.created_at)
                updated = _ensure_utc(record.updated_at)
                update_params = (
                    record.job_id,
                    record.inventory_id,
                    record.aisle_id,
                    record.position_id,
                    record.entity_uid,
                    record.model_entity_id,
                    record.raw_manifest_entry_id,
                    record.manifest_entry_id,
                    record.raw_source_image_id,
                    record.resolved_manifest_entry_id,
                    record.source_image_id,
                    record.source_asset_id,
                    record.traceability_status,
                    record.traceability_warning,
                    _role_to_db(record.role),
                    record.provider,
                    record.model_name,
                    record.schema_version,
                    record.manifest_version,
                    1 if record.has_valid_evidence else 0,
                    record.evidence_kind,
                    updated,
                    record.id,
                )
                cur.execute(
                    """
                    UPDATE result_evidence SET
                        job_id = ?, inventory_id = ?, aisle_id = ?, position_id = ?,
                        entity_uid = ?, model_entity_id = ?,
                        raw_manifest_entry_id = ?, manifest_entry_id = ?,
                        raw_source_image_id = ?, resolved_manifest_entry_id = ?,
                        source_image_id = ?, source_asset_id = ?,
                        traceability_status = ?, traceability_warning = ?, role = ?,
                        provider = ?, model_name = ?, schema_version = ?, manifest_version = ?,
                        has_valid_evidence = ?, evidence_kind = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    update_params,
                )
                if cur.rowcount == 0:
                    cur.execute(
                        """
                        INSERT INTO result_evidence (
                            id, job_id, inventory_id, aisle_id, position_id,
                            entity_uid, model_entity_id,
                            raw_manifest_entry_id, manifest_entry_id,
                            raw_source_image_id, resolved_manifest_entry_id,
                            source_image_id, source_asset_id,
                            traceability_status, traceability_warning, role,
                            provider, model_name, schema_version, manifest_version,
                            has_valid_evidence, evidence_kind, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            record.id,
                            record.job_id,
                            record.inventory_id,
                            record.aisle_id,
                            record.position_id,
                            record.entity_uid,
                            record.model_entity_id,
                            record.raw_manifest_entry_id,
                            record.manifest_entry_id,
                            record.raw_source_image_id,
                            record.resolved_manifest_entry_id,
                            record.source_image_id,
                            record.source_asset_id,
                            record.traceability_status,
                            record.traceability_warning,
                            _role_to_db(record.role),
                            record.provider,
                            record.model_name,
                            record.schema_version,
                            record.manifest_version,
                            1 if record.has_valid_evidence else 0,
                            record.evidence_kind,
                            created,
                            updated,
                        ),
                    )

    def delete_by_job_id(self, job_id: str) -> int:
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute("DELETE FROM result_evidence WHERE job_id = ?", (job_id,))
            return int(cur.rowcount or 0)

    def delete_for_scope(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        job_id: str,
    ) -> int:
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(
                """
                DELETE FROM result_evidence
                WHERE inventory_id = ? AND aisle_id = ? AND job_id = ?
                """,
                (inventory_id, aisle_id, job_id),
            )
            return int(cur.rowcount or 0)

    def list_by_job_id(self, job_id: str) -> Sequence[ResultEvidenceRecord]:
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(
                "SELECT * FROM result_evidence WHERE job_id = ? ORDER BY created_at, id",
                (job_id,),
            )
            return [_row_to_record(row) for row in cur.fetchall()]

    def list_valid_by_job_id(self, job_id: str) -> Sequence[ResultEvidenceRecord]:
        with sql_repository_cursor(self._client, connection=self._connection) as cur:
            cur.execute(
                """
                SELECT * FROM result_evidence
                WHERE job_id = ? AND has_valid_evidence = 1
                ORDER BY created_at, id
                """,
                (job_id,),
            )
            return [_row_to_record(row) for row in cur.fetchall()]
