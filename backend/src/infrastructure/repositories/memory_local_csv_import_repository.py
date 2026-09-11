"""Process-local repository for local CSV imports."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from src.application.ports.local_csv_import_repository import LocalCsvProductiveApplier
from src.application.ports.sql_cursor import SqlCursorLike
from src.domain.local_csv_import.entities import (
    LocalCsvImport,
    LocalCsvImportRow,
)
from src.domain.local_csv_import.error_codes import normalize_stable_error_code
from src.domain.local_csv_import.errors import (
    LOCAL_CSV_EXPORT_CONFLICT,
    LOCAL_CSV_EXPORT_NOT_PREVIEWED,
    LOCAL_CSV_IMPORT_INVALID_STATUS,
    LOCAL_CSV_MATERIALIZATION_FAILED,
    LOCAL_CSV_SECONDARY_CONFLICT,
    LocalCsvImportError,
)
from src.domain.local_csv_import.lease import (
    assert_owner_may_finalize,
    build_lease_claim,
)
from src.domain.local_csv_import.statuses import (
    LOCAL_CSV_IMPORT_CLAIMED_STATUSES,
    LOCAL_CSV_IMPORT_RESUMABLE_STATUSES,
    LOCAL_CSV_IMPORT_STATUS_CONFIRMED,
    LOCAL_CSV_IMPORT_STATUS_MATERIALIZATION_FAILED,
    LOCAL_CSV_IMPORT_STATUS_MATERIALIZING,
    LOCAL_CSV_IMPORT_STATUS_PREVIEWED,
    LOCAL_CSV_IMPORT_STATUS_REQUIRES_REVIEW,
)


class MemoryLocalCsvImportRepository:
    def __init__(self) -> None:
        self._by_id: dict[str, LocalCsvImport] = {}
        self._lock = threading.Lock()

    def get_by_id(self, import_id: str) -> LocalCsvImport | None:
        return self._by_id.get((import_id or "").strip())

    def get_by_export_id(
        self, *, inventory_id: str, export_id: str
    ) -> LocalCsvImport | None:
        return next(
            (
                record
                for record in self._by_id.values()
                if record.inventory_id == inventory_id and record.export_id == export_id
            ),
            None,
        )

    def find_confirmed_secondary_keys(
        self,
        keys: set[tuple[str, str]],
        *,
        cursor: SqlCursorLike | None = None,
    ) -> set[tuple[str, str]]:
        _ = cursor
        if not keys:
            return set()
        return {
            row.secondary_key
            for record in self._by_id.values()
            if record.status in LOCAL_CSV_IMPORT_CLAIMED_STATUSES
            for row in record.rows
            if row.status == "IMPORTED" and row.secondary_key in keys
        }

    def stage_or_get_existing(self, record: LocalCsvImport) -> LocalCsvImport:
        with self._lock:
            existing = self.get_by_export_id(
                inventory_id=record.inventory_id, export_id=record.export_id
            )
            if existing is not None:
                if existing.content_hash != record.content_hash:
                    raise LocalCsvImportError(
                        LOCAL_CSV_EXPORT_CONFLICT,
                        "export_id already exists with different CSV content",
                    )
                return existing
            self._by_id[record.id] = record
            return record

    def select_rows_to_import_on_cursor(
        self,
        cur: SqlCursorLike,
        *,
        inventory_id: str,
        export_id: str,
        conflict_policy: str,
    ) -> tuple[LocalCsvImport, tuple[LocalCsvImportRow, ...], bool]:
        _ = cur
        record = self.get_by_export_id(inventory_id=inventory_id, export_id=export_id)
        if record is None:
            raise LocalCsvImportError(
                LOCAL_CSV_EXPORT_NOT_PREVIEWED, "export_id has not been previewed"
            )
        if record.status == LOCAL_CSV_IMPORT_STATUS_CONFIRMED:
            return record, (), True
        if record.status in LOCAL_CSV_IMPORT_RESUMABLE_STATUSES:
            return record, (), False
        if record.status != LOCAL_CSV_IMPORT_STATUS_PREVIEWED:
            raise LocalCsvImportError(
                LOCAL_CSV_IMPORT_INVALID_STATUS,
                f"Import status {record.status!r} cannot be confirmed",
            )

        eligible = {
            row.secondary_key for row in record.rows if row.status == "PREVIEW_VALID"
        }
        conflict_keys = self.find_confirmed_secondary_keys(eligible)
        if conflict_keys and conflict_policy == "REJECT":
            raise LocalCsvImportError(
                LOCAL_CSV_SECONDARY_CONFLICT,
                "One or more capture_session_id + capture_photo_id keys already exist",
            )

        to_import = tuple(
            row
            for row in record.rows
            if row.status == "PREVIEW_VALID" and row.secondary_key not in conflict_keys
        )
        return record, to_import, False

    def claim_import_for_materialization(
        self,
        *,
        inventory_id: str,
        export_id: str,
        conflict_policy: str,
        confirmed_by_user_id: str | None,
        apply_productive: LocalCsvProductiveApplier,
        clock_now: Callable[[], datetime],
        owner: str,
        lease_sec: int,
        cursor: SqlCursorLike | None = None,
    ) -> tuple[LocalCsvImport, bool]:
        with self._lock:
            return self._claim_import_locked(
                inventory_id=inventory_id,
                export_id=export_id,
                conflict_policy=conflict_policy,
                confirmed_by_user_id=confirmed_by_user_id,
                apply_productive=apply_productive,
                clock_now=clock_now,
                owner=owner,
                lease_sec=lease_sec,
                cursor=cursor,
            )

    def confirm_import_atomically(
        self,
        *,
        inventory_id: str,
        export_id: str,
        conflict_policy: str,
        confirmed_by_user_id: str | None,
        apply_productive: LocalCsvProductiveApplier,
        clock_now: Callable[[], datetime],
        cursor: SqlCursorLike | None = None,
        owner: str | None = None,
        lease_sec: int = 120,
    ) -> tuple[LocalCsvImport, bool]:
        resolved_owner = (owner or confirmed_by_user_id or "system-import").strip()
        return self.claim_import_for_materialization(
            inventory_id=inventory_id,
            export_id=export_id,
            conflict_policy=conflict_policy,
            confirmed_by_user_id=confirmed_by_user_id,
            apply_productive=apply_productive,
            clock_now=clock_now,
            owner=resolved_owner,
            lease_sec=lease_sec,
            cursor=cursor,
        )

    def _claim_import_locked(
        self,
        *,
        inventory_id: str,
        export_id: str,
        conflict_policy: str,
        confirmed_by_user_id: str | None,
        apply_productive: LocalCsvProductiveApplier,
        clock_now: Callable[[], datetime],
        owner: str,
        lease_sec: int,
        cursor: SqlCursorLike | None,
    ) -> tuple[LocalCsvImport, bool]:
        record, to_import, already_confirmed = self.select_rows_to_import_on_cursor(
            cursor,  # type: ignore[arg-type]
            inventory_id=inventory_id,
            export_id=export_id,
            conflict_policy=conflict_policy,
        )
        if already_confirmed:
            return record, True

        now = clock_now()
        claim = build_lease_claim(
            record, now=now, owner=owner, lease_sec=lease_sec
        )

        if record.status in LOCAL_CSV_IMPORT_RESUMABLE_STATUSES:
            resumed = replace(
                record,
                status=LOCAL_CSV_IMPORT_STATUS_MATERIALIZING,
                conflict_policy=conflict_policy or record.conflict_policy,
                confirmed_by_user_id=confirmed_by_user_id
                or record.confirmed_by_user_id,
                last_error_code=None,
                materialization_attempts=claim.attempts,
                materialization_owner=claim.owner,
                materialization_lease_expires_at=claim.lease_expires_at,
                materialization_started_at=claim.started_at,
                materialization_last_attempt_at=claim.last_attempt_at,
                materialization_next_retry_at=None,
                fencing_version=claim.fencing_version,
                updated_at=now,
            )
            self._by_id[resumed.id] = resumed
            return resumed, False

        conflict_keys = self.find_confirmed_secondary_keys(
            {row.secondary_key for row in record.rows if row.status == "PREVIEW_VALID"}
        )

        applied = apply_productive(
            record, to_import, confirmed_by_user_id, cursor=cursor
        )
        by_row_id = {r.import_row_id: r for r in applied}
        updated_rows: list[LocalCsvImportRow] = []
        for row in record.rows:
            if row.status != "PREVIEW_VALID":
                updated_rows.append(row)
                continue
            if row.secondary_key in conflict_keys:
                updated_rows.append(replace(row, status="DUPLICATE"))
                continue
            result = by_row_id.get(row.id)
            updated_rows.append(
                replace(
                    row,
                    status="IMPORTED",
                    productive_result_id=result.id if result else None,
                    requires_review=(
                        bool(result.requires_review) if result else row.requires_review
                    ),
                )
            )

        updated_rows.sort(key=lambda r: r.row_number)
        materializing = replace(
            record,
            status=LOCAL_CSV_IMPORT_STATUS_MATERIALIZING,
            valid_rows=sum(row.status == "IMPORTED" for row in updated_rows),
            duplicate_rows=sum(row.status == "DUPLICATE" for row in updated_rows),
            rejected_rows=sum(row.status == "REJECTED" for row in updated_rows),
            conflict_policy=conflict_policy,
            confirmed_at=None,
            confirmed_by_user_id=confirmed_by_user_id,
            last_error_code=None,
            materialization_attempts=claim.attempts,
            materialization_owner=claim.owner,
            materialization_lease_expires_at=claim.lease_expires_at,
            materialization_started_at=claim.started_at,
            materialization_last_attempt_at=claim.last_attempt_at,
            materialization_next_retry_at=None,
            fencing_version=claim.fencing_version,
            updated_at=now,
            rows=tuple(updated_rows),
        )
        self._by_id[materializing.id] = materializing
        return materializing, False

    def finalize_import_confirmation_on_cursor(
        self,
        cur: SqlCursorLike,
        *,
        import_id: str,
        clock_now: Callable[[], datetime],
        confirmed_by_user_id: str | None = None,
        owner: str | None = None,
        expected_fencing_version: int | None = None,
        require_inventory_writable_on_cursor: Callable[[SqlCursorLike, str], None]
        | None = None,
    ) -> LocalCsvImport:
        record = self.get_by_id(import_id)
        if record is None:
            raise LocalCsvImportError(
                LOCAL_CSV_EXPORT_NOT_PREVIEWED, "import not found"
            )
        if record.status == LOCAL_CSV_IMPORT_STATUS_CONFIRMED:
            return record
        assert_owner_may_finalize(
            record,
            owner=owner,
            expected_fencing_version=expected_fencing_version,
        )
        if record.status not in LOCAL_CSV_IMPORT_RESUMABLE_STATUSES:
            raise LocalCsvImportError(
                LOCAL_CSV_IMPORT_INVALID_STATUS,
                f"Import status {record.status!r} cannot be finalized",
            )
        if require_inventory_writable_on_cursor is not None:
            require_inventory_writable_on_cursor(cur, record.inventory_id)
        now = clock_now()
        confirmed = replace(
            record,
            status=LOCAL_CSV_IMPORT_STATUS_CONFIRMED,
            confirmed_at=now,
            confirmed_by_user_id=confirmed_by_user_id or record.confirmed_by_user_id,
            last_error_code=None,
            materialization_owner=None,
            materialization_lease_expires_at=None,
            materialization_next_retry_at=None,
            updated_at=now,
        )
        self._by_id[confirmed.id] = confirmed
        return confirmed

    def finalize_import_confirmation(
        self,
        *,
        import_id: str,
        clock_now: Callable[[], datetime],
        confirmed_by_user_id: str | None = None,
        owner: str | None = None,
        expected_fencing_version: int | None = None,
    ) -> LocalCsvImport:
        with self._lock:
            return self.finalize_import_confirmation_on_cursor(
                _MemoryCursor(self._lock),
                import_id=import_id,
                clock_now=clock_now,
                confirmed_by_user_id=confirmed_by_user_id,
                owner=owner,
                expected_fencing_version=expected_fencing_version,
            )

    def mark_materialization_failed_on_cursor(
        self,
        cur: SqlCursorLike,
        *,
        import_id: str,
        error_code: str,
        clock_now: Callable[[], datetime],
        requires_review: bool = False,
        next_retry_at: datetime | None = None,
        owner: str | None = None,
        expected_fencing_version: int | None = None,
    ) -> LocalCsvImport:
        _ = cur
        code = normalize_stable_error_code(
            error_code, fallback=LOCAL_CSV_MATERIALIZATION_FAILED
        )
        record = self.get_by_id(import_id)
        if record is None:
            raise LocalCsvImportError(
                LOCAL_CSV_EXPORT_NOT_PREVIEWED, "import not found"
            )
        if record.status == LOCAL_CSV_IMPORT_STATUS_CONFIRMED:
            return record
        assert_owner_may_finalize(
            record,
            owner=owner,
            expected_fencing_version=expected_fencing_version,
        )
        now = clock_now()
        failed = replace(
            record,
            status=(
                LOCAL_CSV_IMPORT_STATUS_REQUIRES_REVIEW
                if requires_review
                else LOCAL_CSV_IMPORT_STATUS_MATERIALIZATION_FAILED
            ),
            last_error_code=code,
            materialization_owner=None,
            materialization_lease_expires_at=None,
            materialization_next_retry_at=next_retry_at,
            updated_at=now,
        )
        self._by_id[failed.id] = failed
        return failed

    def mark_materialization_failed(
        self,
        *,
        import_id: str,
        error_code: str,
        clock_now: Callable[[], datetime],
        requires_review: bool = False,
        next_retry_at: datetime | None = None,
        owner: str | None = None,
        expected_fencing_version: int | None = None,
    ) -> LocalCsvImport:
        with self._lock:
            return self.mark_materialization_failed_on_cursor(
                _MemoryCursor(self._lock),
                import_id=import_id,
                error_code=error_code,
                clock_now=clock_now,
                requires_review=requires_review,
                next_retry_at=next_retry_at,
                owner=owner,
                expected_fencing_version=expected_fencing_version,
            )

    def list_recovery_candidates(
        self,
        *,
        now: datetime,
        limit: int,
    ) -> tuple[LocalCsvImport, ...]:
        capped = max(1, min(int(limit), 500))
        candidates: list[LocalCsvImport] = []
        with self._lock:
            for record in self._by_id.values():
                if record.status == LOCAL_CSV_IMPORT_STATUS_MATERIALIZING:
                    expires = record.materialization_lease_expires_at
                    if expires is not None and expires <= now:
                        candidates.append(record)
                elif record.status == LOCAL_CSV_IMPORT_STATUS_MATERIALIZATION_FAILED:
                    retry_at = record.materialization_next_retry_at
                    if retry_at is None or retry_at <= now:
                        candidates.append(record)
        candidates.sort(key=lambda r: r.updated_at)
        return tuple(candidates[:capped])

    def save(self, record: LocalCsvImport) -> LocalCsvImport:
        with self._lock:
            by_export = self.get_by_export_id(
                inventory_id=record.inventory_id, export_id=record.export_id
            )
            if by_export is not None and by_export.id != record.id:
                raise LocalCsvImportError(
                    LOCAL_CSV_EXPORT_CONFLICT,
                    "export_id already exists with a different import id",
                )
            self._by_id[record.id] = record
            return record


class _MemoryCursor:
    """Placeholder cursor token — memory repos use repo-level locks instead."""

    def __init__(self, lock: threading.Lock) -> None:
        self._lock = lock

    def execute(self, *args, **kwargs) -> None:
        _ = args, kwargs

    def executemany(self, *args, **kwargs) -> None:
        _ = args, kwargs

    def fetchone(self) -> None:
        return None

    def fetchall(self) -> list[object]:
        return []

    @property
    def rowcount(self) -> int:
        return 0
