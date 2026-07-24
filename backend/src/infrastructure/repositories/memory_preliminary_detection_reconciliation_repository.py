"""In-memory reconciliation repository for unit tests."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from src.application.ports.preliminary_detection_reconciliation_repository import (
    ReconciliationRowVersionConflictError,
    ReconciliationUniqueViolationError,
)
from src.application.services.preliminary_detection_compare import (
    OUTCOME_BOTH_AMBIGUOUS,
    OUTCOME_BOTH_UNRESOLVED,
    OUTCOME_CODE_MISMATCH,
    OUTCOME_LOCAL_AMBIGUOUS,
    OUTCOME_LOCAL_ONLY,
    OUTCOME_MATCH_CODE_AND_QUANTITY,
    OUTCOME_MATCH_CODE_BOTH_QUANTITY_MISSING,
    OUTCOME_MATCH_CODE_LOCAL_QUANTITY_MISSING,
    OUTCOME_MATCH_CODE_QUANTITY_DIFFERENT,
    OUTCOME_MATCH_CODE_REMOTE_QUANTITY_MISSING,
    OUTCOME_NOT_COMPARABLE,
    OUTCOME_REMOTE_AMBIGUOUS,
    OUTCOME_REMOTE_ONLY,
)
from src.domain.preliminary_detection_reconciliations.entities import (
    PreliminaryDetectionReconciliation,
)

_CODE_MATCH = {
    OUTCOME_MATCH_CODE_AND_QUANTITY,
    OUTCOME_MATCH_CODE_BOTH_QUANTITY_MISSING,
    OUTCOME_MATCH_CODE_LOCAL_QUANTITY_MISSING,
    OUTCOME_MATCH_CODE_REMOTE_QUANTITY_MISSING,
    OUTCOME_MATCH_CODE_QUANTITY_DIFFERENT,
}
_QTY_MATCH = {
    OUTCOME_MATCH_CODE_AND_QUANTITY,
    OUTCOME_MATCH_CODE_BOTH_QUANTITY_MISSING,
}
_AMBIGUOUS = {
    OUTCOME_LOCAL_AMBIGUOUS,
    OUTCOME_REMOTE_AMBIGUOUS,
    OUTCOME_BOTH_AMBIGUOUS,
}
_TERMINAL_DONE = {"COMPLETED", "NOT_COMPARABLE", "FAILED_TERMINAL"}


class MemoryPreliminaryDetectionReconciliationRepository:
    def __init__(self) -> None:
        self._by_id: dict[str, PreliminaryDetectionReconciliation] = {}
        self._by_key: dict[tuple[str, str, str], str] = {}

    def get_by_id(self, reconciliation_id: str) -> PreliminaryDetectionReconciliation | None:
        return self._by_id.get(reconciliation_id)

    def get_by_identity(
        self,
        *,
        preliminary_detection_id: str,
        comparison_version: str,
        job_id: str,
    ) -> PreliminaryDetectionReconciliation | None:
        key = (
            preliminary_detection_id.strip(),
            comparison_version.strip(),
            job_id.strip(),
        )
        rid = self._by_key.get(key)
        return self._by_id.get(rid) if rid else None

    def insert(
        self, row: PreliminaryDetectionReconciliation
    ) -> PreliminaryDetectionReconciliation:
        key = (row.preliminary_detection_id, row.comparison_version, row.job_id)
        if key in self._by_key:
            raise ReconciliationUniqueViolationError()
        self._by_id[row.id] = row
        self._by_key[key] = row.id
        return row

    def update_if_version(
        self, row: PreliminaryDetectionReconciliation, *, expected_version: int
    ) -> PreliminaryDetectionReconciliation:
        current = self._by_id.get(row.id)
        if current is None or current.row_version != expected_version:
            raise ReconciliationRowVersionConflictError()
        bumped = PreliminaryDetectionReconciliation(
            **{**row.__dict__, "row_version": expected_version + 1}
        )
        self._by_id[row.id] = bumped
        self._by_key[(bumped.preliminary_detection_id, bumped.comparison_version, bumped.job_id)] = (
            bumped.id
        )
        return bumped

    def list_by_aisle(self, **kwargs) -> Sequence[PreliminaryDetectionReconciliation]:
        limit = kwargs.pop("limit", 200)
        offset = kwargs.pop("offset", 0)
        rows = self._filter(**kwargs)
        rows.sort(key=lambda r: r.compared_at, reverse=True)
        return rows[offset : offset + limit]

    def count_by_aisle(self, **kwargs) -> int:
        return len(self._filter(**kwargs))

    def aggregate_metrics(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        job_id: str | None = None,
        parser_version: str | None = None,
        detector_version: str | None = None,
    ) -> dict[str, int]:
        rows = self._filter(
            inventory_id=inventory_id,
            aisle_id=aisle_id,
            job_id=job_id,
            preliminary_detection_id=None,
            comparison_version=None,
            outcome=None,
            asset_id=None,
            client_file_id=None,
            parser_version=parser_version,
            detector_version=detector_version,
            comparable_only=None,
            compared_after=None,
            compared_before=None,
        )
        pending = sum(
            1
            for r in rows
            if r.reconciliation_status in ("PENDING", "RUNNING", "RETRY_SCHEDULED")
        )
        done = [r for r in rows if r.reconciliation_status in _TERMINAL_DONE]
        not_comp = [r for r in done if r.outcome == OUTCOME_NOT_COMPARABLE]
        comparable = [r for r in done if r.outcome != OUTCOME_NOT_COMPARABLE]
        code_comp = [
            r
            for r in comparable
            if r.outcome not in _AMBIGUOUS and r.outcome != OUTCOME_BOTH_UNRESOLVED
        ]
        return {
            "total_reconciled": len(done),
            "total_pending": pending,
            "total_not_comparable": len(not_comp),
            "mapping_comparable": len(comparable),
            "code_comparable": len(code_comp),
            "quantity_comparable": sum(1 for r in code_comp if r.outcome in _CODE_MATCH),
            "code_match_count": sum(1 for r in comparable if r.outcome in _CODE_MATCH),
            "code_mismatch_count": sum(1 for r in comparable if r.outcome == OUTCOME_CODE_MISMATCH),
            "quantity_match_count": sum(1 for r in comparable if r.outcome in _QTY_MATCH),
            "quantity_mismatch_count": sum(
                1 for r in comparable if r.outcome == OUTCOME_MATCH_CODE_QUANTITY_DIFFERENT
            ),
            "local_only_count": sum(1 for r in comparable if r.outcome == OUTCOME_LOCAL_ONLY),
            "remote_only_count": sum(1 for r in comparable if r.outcome == OUTCOME_REMOTE_ONLY),
            "ambiguous_count": sum(1 for r in comparable if r.outcome in _AMBIGUOUS),
            "both_unresolved_count": sum(
                1 for r in comparable if r.outcome == OUTCOME_BOTH_UNRESOLVED
            ),
        }

    def claim_due(
        self,
        *,
        lease_token: str,
        lease_expires_at: datetime,
        now: datetime,
        limit: int = 50,
    ) -> Sequence[PreliminaryDetectionReconciliation]:
        due: list[PreliminaryDetectionReconciliation] = []
        for r in sorted(self._by_id.values(), key=lambda x: x.created_at):
            if len(due) >= limit:
                break
            st = r.reconciliation_status
            if st == "PENDING":
                pass
            elif st == "RETRY_SCHEDULED" and (r.next_retry_at is None or r.next_retry_at <= now):
                pass
            elif (
                st == "RUNNING"
                and r.lease_expires_at is not None
                and r.lease_expires_at <= now
            ):
                pass
            else:
                continue
            claimed = PreliminaryDetectionReconciliation(
                **{
                    **r.__dict__,
                    "reconciliation_status": "RUNNING",
                    "lease_token": lease_token,
                    "lease_expires_at": lease_expires_at,
                    "attempt_count": r.attempt_count + 1,
                    "row_version": r.row_version + 1,
                    "updated_at": now,
                }
            )
            self._by_id[r.id] = claimed
            due.append(claimed)
        return due

    def release_expired_leases(self, *, now: datetime) -> int:
        n = 0
        for r in list(self._by_id.values()):
            if (
                r.reconciliation_status == "RUNNING"
                and r.lease_expires_at is not None
                and r.lease_expires_at <= now
            ):
                self._by_id[r.id] = PreliminaryDetectionReconciliation(
                    **{
                        **r.__dict__,
                        "reconciliation_status": "RETRY_SCHEDULED"
                        if r.attempt_count > 0
                        else "PENDING",
                        "lease_token": None,
                        "lease_expires_at": None,
                        "next_retry_at": now,
                        "row_version": r.row_version + 1,
                        "updated_at": now,
                    }
                )
                n += 1
        return n

    def list_by_preliminary_ids(
        self, preliminary_ids: Sequence[str]
    ) -> Sequence[PreliminaryDetectionReconciliation]:
        ids = {p.strip() for p in preliminary_ids if p}
        return [r for r in self._by_id.values() if r.preliminary_detection_id in ids]

    def delete_expired(self, *, now: datetime, limit: int = 500) -> int:
        expired = [
            r for r in self._by_id.values() if r.expires_at is not None and r.expires_at <= now
        ][:limit]
        for r in expired:
            self._by_id.pop(r.id, None)
            self._by_key.pop(
                (r.preliminary_detection_id, r.comparison_version, r.job_id), None
            )
        return len(expired)

    def _filter(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        job_id: str | None = None,
        preliminary_detection_id: str | None = None,
        comparison_version: str | None = None,
        outcome: str | None = None,
        asset_id: str | None = None,
        client_file_id: str | None = None,
        parser_version: str | None = None,
        detector_version: str | None = None,
        comparable_only: bool | None = None,
        compared_after: datetime | None = None,
        compared_before: datetime | None = None,
    ) -> list[PreliminaryDetectionReconciliation]:
        out: list[PreliminaryDetectionReconciliation] = []
        for r in self._by_id.values():
            if r.inventory_id != inventory_id or r.aisle_id != aisle_id:
                continue
            if job_id and r.job_id != job_id:
                continue
            if preliminary_detection_id and r.preliminary_detection_id != preliminary_detection_id:
                continue
            if comparison_version and r.comparison_version != comparison_version:
                continue
            if outcome and r.outcome != outcome:
                continue
            if asset_id and r.asset_id != asset_id:
                continue
            if client_file_id and r.client_file_id != client_file_id:
                continue
            if parser_version and r.local_parser_version != parser_version:
                continue
            if detector_version and r.local_detector_version != detector_version:
                continue
            if comparable_only is True and r.outcome == OUTCOME_NOT_COMPARABLE:
                continue
            if comparable_only is False and r.outcome != OUTCOME_NOT_COMPARABLE:
                continue
            if compared_after and r.compared_at < compared_after:
                continue
            if compared_before and r.compared_at > compared_before:
                continue
            out.append(r)
        return out
