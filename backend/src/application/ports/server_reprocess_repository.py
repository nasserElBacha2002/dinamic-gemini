"""Port for Phase 7 server reprocess persistence."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from src.domain.server_reprocess.entities import (
    ServerReprocessAdoption,
    ServerReprocessAdoptionItem,
    ServerReprocessProposal,
    ServerReprocessRun,
    ServerReprocessRunAsset,
)


class ServerReprocessRepository(Protocol):
    def get_run(self, run_id: str) -> ServerReprocessRun | None: ...

    def get_run_by_request_id(self, request_id: str) -> ServerReprocessRun | None: ...

    def list_runs_for_aisle(self, aisle_id: str) -> Sequence[ServerReprocessRun]: ...

    def save_run(
        self,
        *,
        run: ServerReprocessRun,
        assets: Sequence[ServerReprocessRunAsset],
    ) -> ServerReprocessRun: ...

    def update_run(self, run: ServerReprocessRun) -> ServerReprocessRun: ...

    def list_run_assets(self, run_id: str) -> Sequence[ServerReprocessRunAsset]: ...

    def replace_proposals(
        self,
        *,
        run_id: str,
        proposals: Sequence[ServerReprocessProposal],
    ) -> Sequence[ServerReprocessProposal]: ...

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
    ) -> Sequence[ServerReprocessProposal]: ...

    def get_proposal(self, proposal_id: str) -> ServerReprocessProposal | None: ...

    def update_proposal(self, proposal: ServerReprocessProposal) -> ServerReprocessProposal: ...

    def get_adoption_by_adoption_id(
        self, adoption_id: str
    ) -> ServerReprocessAdoption | None: ...

    def save_adoption(
        self,
        *,
        adoption: ServerReprocessAdoption,
        items: Sequence[ServerReprocessAdoptionItem],
        updated_proposals: Sequence[ServerReprocessProposal],
        updated_run: ServerReprocessRun,
    ) -> ServerReprocessAdoption: ...

    def try_acquire_lock(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        owner_token: str,
        expires_at: datetime,
    ) -> bool: ...

    def release_lock(self, *, aisle_id: str, owner_token: str) -> None: ...
