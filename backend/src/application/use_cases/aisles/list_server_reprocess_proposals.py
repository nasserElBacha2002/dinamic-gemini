"""List server reprocess proposals and summary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from src.application.ports.server_reprocess_repository import ServerReprocessRepository
from src.application.use_cases.aisles.build_server_reprocess_proposals import (
    ServerReprocessRunNotFoundError,
)
from src.domain.server_reprocess.entities import (
    ServerReprocessProposal,
    ServerReprocessRun,
)

_CHANGED = frozenset(
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


@dataclass(frozen=True)
class ServerReprocessProposalSummary:
    total: int
    same: int
    changed: int
    newly_resolved: int
    unresolved: int
    not_comparable: int


@dataclass(frozen=True)
class ListServerReprocessProposalsResult:
    run: ServerReprocessRun
    summary: ServerReprocessProposalSummary
    items: Sequence[ServerReprocessProposal]


class ListServerReprocessProposals:
    def __init__(self, *, reprocess_repo: ServerReprocessRepository) -> None:
        self._repo = reprocess_repo

    def execute(
        self,
        *,
        run_id: str,
        difference_type: str | None = None,
        asset_id: str | None = None,
        review_status: str | None = None,
        has_change: bool | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> ListServerReprocessProposalsResult:
        run = self._repo.get_run(run_id)
        if run is None:
            raise ServerReprocessRunNotFoundError(run_id)
        all_items = list(self._repo.list_proposals(run_id, limit=10_000))
        summary = self._summarize(all_items)
        items = list(
            self._repo.list_proposals(
                run_id,
                difference_type=difference_type,
                asset_id=asset_id,
                review_status=review_status,
                has_change=has_change,
                offset=offset,
                limit=limit,
            )
        )
        return ListServerReprocessProposalsResult(
            run=run, summary=summary, items=items
        )

    def _summarize(
        self, items: Sequence[ServerReprocessProposal]
    ) -> ServerReprocessProposalSummary:
        same = changed = newly = unresolved = not_comp = 0
        for p in items:
            if p.difference_type == "SAME_RESULT":
                same += 1
            elif p.difference_type == "PREVIOUS_UNRESOLVED_REMOTE_RESOLVED":
                newly += 1
                changed += 1
            elif p.difference_type.startswith("NOT_COMPARABLE"):
                not_comp += 1
            elif p.difference_type in _CHANGED:
                changed += 1
            if not p.remote_resolved:
                unresolved += 1
        return ServerReprocessProposalSummary(
            total=len(items),
            same=same,
            changed=changed,
            newly_resolved=newly,
            unresolved=unresolved,
            not_comparable=not_comp,
        )
