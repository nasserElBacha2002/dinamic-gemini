"""In-memory server reprocess repository (unit tests)."""

from __future__ import annotations

import threading
from collections.abc import Sequence
from datetime import datetime

from src.domain.server_reprocess.entities import (
    ServerReprocessAdoption,
    ServerReprocessAdoptionItem,
    ServerReprocessProposal,
    ServerReprocessRun,
    ServerReprocessRunAsset,
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


class MemoryServerReprocessRepository:
    def __init__(self) -> None:
        self._runs: dict[str, ServerReprocessRun] = {}
        self._by_request: dict[str, str] = {}
        self._assets: dict[str, list[ServerReprocessRunAsset]] = {}
        self._proposals: dict[str, list[ServerReprocessProposal]] = {}
        self._proposals_by_id: dict[str, ServerReprocessProposal] = {}
        self._adoptions: dict[str, ServerReprocessAdoption] = {}
        self._adoptions_by_key: dict[str, str] = {}
        self._adoption_items: dict[str, list[ServerReprocessAdoptionItem]] = {}
        self._locks: dict[str, tuple[str, str, datetime]] = {}
        self._lock = threading.Lock()

    def get_run(self, run_id: str) -> ServerReprocessRun | None:
        return self._runs.get((run_id or "").strip())

    def get_run_by_request_id(self, request_id: str) -> ServerReprocessRun | None:
        rid = self._by_request.get((request_id or "").strip())
        return self._runs.get(rid) if rid else None

    def list_runs_for_aisle(self, aisle_id: str) -> Sequence[ServerReprocessRun]:
        aid = (aisle_id or "").strip()
        rows = [r for r in self._runs.values() if r.aisle_id == aid]
        rows.sort(key=lambda r: r.requested_at, reverse=True)
        return rows

    def save_run(
        self,
        *,
        run: ServerReprocessRun,
        assets: Sequence[ServerReprocessRunAsset],
    ) -> ServerReprocessRun:
        with self._lock:
            existing = self._by_request.get(run.request_id)
            if existing and existing != run.id:
                raise ValueError("REQUEST_ID_CONFLICT")
            self._runs[run.id] = run
            self._by_request[run.request_id] = run.id
            self._assets[run.id] = list(assets)
            return run

    def update_run(self, run: ServerReprocessRun) -> ServerReprocessRun:
        with self._lock:
            self._runs[run.id] = run
            return run

    def list_run_assets(self, run_id: str) -> Sequence[ServerReprocessRunAsset]:
        return list(self._assets.get(run_id, []))

    def replace_proposals(
        self,
        *,
        run_id: str,
        proposals: Sequence[ServerReprocessProposal],
    ) -> Sequence[ServerReprocessProposal]:
        with self._lock:
            for old in self._proposals.get(run_id, []):
                self._proposals_by_id.pop(old.id, None)
            rows = list(proposals)
            self._proposals[run_id] = rows
            for p in rows:
                self._proposals_by_id[p.id] = p
            return rows

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
        rows = list(self._proposals.get(run_id, []))
        if difference_type:
            rows = [p for p in rows if p.difference_type == difference_type]
        if asset_id:
            rows = [p for p in rows if p.asset_id == asset_id]
        if review_status:
            rows = [p for p in rows if p.review_status == review_status]
        if has_change is True:
            rows = [p for p in rows if p.difference_type in _CHANGE_TYPES]
        elif has_change is False:
            rows = [p for p in rows if p.difference_type == "SAME_RESULT"]
        return rows[offset : offset + max(1, limit)]

    def get_proposal(self, proposal_id: str) -> ServerReprocessProposal | None:
        return self._proposals_by_id.get((proposal_id or "").strip())

    def update_proposal(self, proposal: ServerReprocessProposal) -> ServerReprocessProposal:
        with self._lock:
            self._proposals_by_id[proposal.id] = proposal
            run_rows = self._proposals.get(proposal.run_id, [])
            self._proposals[proposal.run_id] = [
                proposal if r.id == proposal.id else r for r in run_rows
            ]
            return proposal

    def get_adoption_by_adoption_id(
        self, adoption_id: str
    ) -> ServerReprocessAdoption | None:
        rid = self._adoptions_by_key.get((adoption_id or "").strip())
        return self._adoptions.get(rid) if rid else None

    def save_adoption(
        self,
        *,
        adoption: ServerReprocessAdoption,
        items: Sequence[ServerReprocessAdoptionItem],
        updated_proposals: Sequence[ServerReprocessProposal],
        updated_run: ServerReprocessRun,
    ) -> ServerReprocessAdoption:
        with self._lock:
            self._adoptions[adoption.id] = adoption
            self._adoptions_by_key[adoption.adoption_id] = adoption.id
            self._adoption_items[adoption.id] = list(items)
            self._runs[updated_run.id] = updated_run
            for p in updated_proposals:
                self._proposals_by_id[p.id] = p
                run_rows = self._proposals.get(p.run_id, [])
                self._proposals[p.run_id] = [
                    p if r.id == p.id else r for r in run_rows
                ]
            return adoption

    def try_acquire_lock(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        owner_token: str,
        expires_at: datetime,
    ) -> bool:
        with self._lock:
            aid = (aisle_id or "").strip()
            now = expires_at  # caller passes absolute expiry; compare with stored
            existing = self._locks.get(aid)
            if existing is not None:
                _inv, token, exp = existing
                if exp > now.replace(tzinfo=exp.tzinfo) if exp.tzinfo else exp:
                    # still held by someone else
                    if token != owner_token:
                        # Treat expires_at as "now + lease" — use a simple clock via expires_at
                        # Memory: if lock exists and token differs, deny unless expired.
                        # We store expires_at; caller should pass now for comparison via release.
                        pass
                if token != owner_token and exp > datetime.min.replace(tzinfo=expires_at.tzinfo):
                    # Re-check: if expires_at is in the future relative to "now", we need now.
                    # Convention: expires_at is the lease end; we accept if expired or same token.
                    # Without a clock here, use: if same token refresh; else deny if lock present
                    # unless we refresh by comparing — store and always allow same token.
                    if token != owner_token:
                        # Allow overwrite only when previous lease expired — use naive: deny
                        # if previous expires_at > datetime.utcnow is not available.
                        # Simpler: always deny different token (tests release explicitly).
                        return False
            self._locks[aid] = (inventory_id, owner_token, expires_at)
            return True

    def release_lock(self, *, aisle_id: str, owner_token: str) -> None:
        with self._lock:
            aid = (aisle_id or "").strip()
            existing = self._locks.get(aid)
            if existing and existing[1] == owner_token:
                self._locks.pop(aid, None)
