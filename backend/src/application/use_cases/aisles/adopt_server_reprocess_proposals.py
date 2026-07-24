"""Adopt server reprocess proposals with all-or-nothing batch + stale checks."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from src.application.ports.server_reprocess_repository import ServerReprocessRepository
from src.application.services.server_reprocess_adoption_hash import (
    canonicalize_adoption_content,
)
from src.application.use_cases.aisles.build_server_reprocess_proposals import (
    ServerReprocessRunNotFoundError,
)
from src.application.use_cases.aisles.create_server_reprocess_run import (
    ServerReprocessLockError,
)
from src.domain.authoritative_local_code_scan.entities import AuthoritativeLocalCodeScanResult
from src.domain.positions.entities import Position, PositionStatus
from src.domain.server_reprocess.entities import (
    ServerReprocessAdoption,
    ServerReprocessAdoptionAction,
    ServerReprocessAdoptionItem,
    ServerReprocessProposal,
    ServerReprocessProposalStatus,
    ServerReprocessReviewStatus,
    ServerReprocessRun,
)

logger = logging.getLogger(__name__)

SERVER_REPROCESS_ADOPTION_DISABLED = "SERVER_REPROCESS_ADOPTION_DISABLED"
SERVER_REPROCESS_STALE_PROPOSAL = "STALE_PROPOSAL"
SERVER_REPROCESS_ADOPTION_CONFLICT = "SERVER_REPROCESS_ADOPTION_CONFLICT"
SERVER_REPROCESS_PROPOSAL_NOT_FOUND = "SERVER_REPROCESS_PROPOSAL_NOT_FOUND"
SERVER_REPROCESS_NOT_COMPARABLE = "SERVER_REPROCESS_NOT_COMPARABLE"

LOCK_LEASE_SECONDS = 60


class ServerReprocessAdoptionDisabledError(Exception):
    def __init__(self) -> None:
        super().__init__("Server reprocess adoption is disabled")
        self.error_code = SERVER_REPROCESS_ADOPTION_DISABLED


class ServerReprocessStaleProposalError(Exception):
    def __init__(self, proposal_id: str) -> None:
        super().__init__(f"Proposal {proposal_id} is stale relative to current authority")
        self.error_code = SERVER_REPROCESS_STALE_PROPOSAL
        self.proposal_id = proposal_id


class ServerReprocessAdoptionConflictError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.error_code = SERVER_REPROCESS_ADOPTION_CONFLICT


class _AuthRepo(Protocol):
    def get_current_for_asset(
        self, asset_id: str
    ) -> AuthoritativeLocalCodeScanResult | None: ...

    def create_authoritative_version(
        self,
        *,
        new_result: AuthoritativeLocalCodeScanResult,
        expected_current_id: str | None,
        expected_row_version: int | None,
    ) -> AuthoritativeLocalCodeScanResult: ...


class _PositionRepo(Protocol):
    def get_by_id(self, position_id: str) -> Position | None: ...

    def save(self, position: Position) -> None: ...


@dataclass(frozen=True)
class AdoptItemCommand:
    proposal_id: str
    action: str
    edit_internal_code: str | None = None
    edit_quantity: float | None = None


@dataclass(frozen=True)
class AdoptServerReprocessCommand:
    inventory_id: str
    aisle_id: str
    run_id: str
    adoption_id: str
    adopted_by: str
    items: tuple[AdoptItemCommand, ...]


@dataclass(frozen=True)
class AdoptServerReprocessResult:
    adoption: ServerReprocessAdoption
    run: ServerReprocessRun
    replayed: bool


class AdoptServerReprocessProposals:
    """
    Explicit adoption creates a new authoritative version + updates position.
    All-or-nothing via repository save_adoption transaction; content_hash idempotency.
    """

    def __init__(
        self,
        *,
        enabled: bool,
        reprocess_repo: ServerReprocessRepository,
        authoritative_repo: _AuthRepo | None = None,
        position_repo: _PositionRepo | None = None,
        clock: Any = None,
    ) -> None:
        self._enabled = bool(enabled)
        self._repo = reprocess_repo
        self._auth_repo = authoritative_repo
        self._position_repo = position_repo
        self._clock = clock

    def _now(self) -> datetime:
        if self._clock is not None:
            return self._clock.now()
        return datetime.now(timezone.utc)

    def execute(self, command: AdoptServerReprocessCommand) -> AdoptServerReprocessResult:
        if not self._enabled:
            raise ServerReprocessAdoptionDisabledError()

        adoption_key = (command.adoption_id or "").strip()
        if not adoption_key:
            raise ServerReprocessAdoptionConflictError("adoption_id is required")

        content_hash = canonicalize_adoption_content(
            run_id=command.run_id, items=command.items
        )

        existing = self._repo.get_adoption_by_adoption_id(adoption_key)
        if existing is not None:
            if (existing.content_hash or "") and existing.content_hash != content_hash:
                raise ServerReprocessAdoptionConflictError(
                    "adoption_id already used with a different payload"
                )
            run = self._repo.get_run(existing.run_id)
            if run is None:
                raise ServerReprocessRunNotFoundError(existing.run_id)
            return AdoptServerReprocessResult(adoption=existing, run=run, replayed=True)

        run = self._repo.get_run(command.run_id)
        if run is None:
            raise ServerReprocessRunNotFoundError(command.run_id)
        if run.inventory_id != command.inventory_id or run.aisle_id != command.aisle_id:
            raise ServerReprocessAdoptionConflictError("Run does not belong to aisle")
        if not command.items:
            raise ServerReprocessAdoptionConflictError("items required")

        owner = str(uuid.uuid4())
        now = self._now()
        if not self._repo.try_acquire_lock(
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            owner_token=owner,
            expires_at=now + timedelta(seconds=LOCK_LEASE_SECONDS),
        ):
            raise ServerReprocessLockError()

        try:
            updated_proposals: list[ServerReprocessProposal] = []
            adoption_items: list[ServerReprocessAdoptionItem] = []
            adopted = kept = deferred = 0
            adoption_row_id = str(uuid.uuid4())

            prepared: list[
                tuple[
                    ServerReprocessProposal,
                    ServerReprocessAdoptionAction,
                    str | None,
                    float | None,
                ]
            ] = []
            for item in command.items:
                proposal = self._repo.get_proposal(item.proposal_id)
                if proposal is None or proposal.run_id != run.id:
                    raise ServerReprocessAdoptionConflictError(
                        f"Proposal {item.proposal_id} not found for run",
                    )
                if proposal.difference_type.startswith("NOT_COMPARABLE"):
                    raise ServerReprocessAdoptionConflictError(
                        f"Proposal {proposal.id} is not comparable",
                    )
                try:
                    action = ServerReprocessAdoptionAction((item.action or "").strip().upper())
                except ValueError as exc:
                    raise ServerReprocessAdoptionConflictError(
                        f"Invalid action {item.action}"
                    ) from exc

                if action in (
                    ServerReprocessAdoptionAction.ADOPT,
                    ServerReprocessAdoptionAction.EDIT_AND_ADOPT,
                ):
                    self._assert_not_stale(proposal)

                prepared.append(
                    (proposal, action, item.edit_internal_code, item.edit_quantity)
                )

            # Apply mutations then persist atomically via save_adoption.
            # If any apply fails, nothing is committed to proposals/adoptions.
            for proposal, action, edit_code, edit_qty in prepared:
                new_result_id: str | None = None
                new_position_id: str | None = proposal.previous_position_id
                if action == ServerReprocessAdoptionAction.KEEP_CURRENT:
                    status = ServerReprocessProposalStatus.KEPT_CURRENT.value
                    kept += 1
                elif action == ServerReprocessAdoptionAction.DEFER:
                    status = ServerReprocessProposalStatus.DEFERRED.value
                    deferred += 1
                else:
                    status = ServerReprocessProposalStatus.ADOPTED.value
                    adopted += 1
                    new_result_id, new_position_id = self._apply_adoption(
                        proposal=proposal,
                        action=action,
                        edit_code=edit_code,
                        edit_qty=edit_qty,
                        adopted_by=command.adopted_by,
                        run_id=run.id,
                        now=now,
                    )
                    if not new_result_id and not new_position_id:
                        raise ServerReprocessAdoptionConflictError(
                            f"Adoption did not update authority/position for {proposal.id}"
                        )

                updated = replace(
                    proposal,
                    status=status,
                    review_status=ServerReprocessReviewStatus.REVIEW_COMPLETED.value,
                    updated_at=now,
                )
                updated_proposals.append(updated)
                adoption_items.append(
                    ServerReprocessAdoptionItem(
                        id=str(uuid.uuid4()),
                        adoption_row_id=adoption_row_id,
                        proposal_id=proposal.id,
                        asset_id=proposal.asset_id,
                        action=action.value,
                        expected_previous_result_id=proposal.previous_result_id,
                        new_result_id=new_result_id,
                        new_position_id=new_position_id,
                        edit_internal_code=edit_code,
                        edit_quantity=edit_qty,
                        created_at=now,
                    )
                )

            review_status = (
                ServerReprocessReviewStatus.ADOPTED_COMPLETELY.value
                if adopted > 0 and kept == 0 and deferred == 0
                else ServerReprocessReviewStatus.ADOPTED_PARTIALLY.value
                if adopted > 0
                else ServerReprocessReviewStatus.REVIEW_COMPLETED.value
            )
            updated_run = replace(
                run,
                review_status=review_status,
                updated_at=now,
                row_version=run.row_version + 1,
            )
            adoption = ServerReprocessAdoption(
                id=adoption_row_id,
                adoption_id=adoption_key,
                run_id=run.id,
                inventory_id=run.inventory_id,
                aisle_id=run.aisle_id,
                status="COMPLETED",
                adopted_by=command.adopted_by,
                adopted_at=now,
                item_count=len(prepared),
                adopted_count=adopted,
                kept_count=kept,
                deferred_count=deferred,
                row_version=1,
                created_at=now,
                updated_at=now,
                content_hash=content_hash,
            )
            saved = self._repo.save_adoption(
                adoption=adoption,
                items=adoption_items,
                updated_proposals=updated_proposals,
                updated_run=updated_run,
            )
            logger.info(
                "server_reprocess_proposal_adopted run_id=%s adoption_id=%s "
                "adopted=%s kept=%s deferred=%s",
                run.id,
                adoption_key,
                adopted,
                kept,
                deferred,
            )
            return AdoptServerReprocessResult(
                adoption=saved, run=updated_run, replayed=False
            )
        finally:
            self._repo.release_lock(aisle_id=command.aisle_id, owner_token=owner)

    def _assert_not_stale(self, proposal: ServerReprocessProposal) -> None:
        if self._auth_repo is None:
            return
        current = self._auth_repo.get_current_for_asset(proposal.asset_id)
        current_id = current.id if current is not None else None
        if (proposal.previous_result_id or None) != (current_id or None):
            raise ServerReprocessStaleProposalError(proposal.id)

    def _apply_adoption(
        self,
        *,
        proposal: ServerReprocessProposal,
        action: ServerReprocessAdoptionAction,
        edit_code: str | None,
        edit_qty: float | None,
        adopted_by: str,
        run_id: str,
        now: datetime,
    ) -> tuple[str | None, str | None]:
        new_result_id: str | None = None
        new_position_id: str | None = proposal.previous_position_id

        code = (
            (edit_code or "").strip()
            if action == ServerReprocessAdoptionAction.EDIT_AND_ADOPT
            else (proposal.internal_code or "").strip()
        )
        if action == ServerReprocessAdoptionAction.EDIT_AND_ADOPT and edit_qty is not None:
            qty: int | None = int(edit_qty)
        elif proposal.quantity is not None:
            qty = int(proposal.quantity)
        else:
            qty = None
        if not code:
            raise ServerReprocessAdoptionConflictError(
                f"Proposal {proposal.id} has no code to adopt"
            )

        if self._auth_repo is not None:
            current = self._auth_repo.get_current_for_asset(proposal.asset_id)
            if current is None:
                raise ServerReprocessAdoptionConflictError(
                    f"No current authoritative result for asset {proposal.asset_id}"
                )
            # Re-validate stale inside apply (same connection window for memory/SQL auth).
            if (proposal.previous_result_id or None) != current.id:
                raise ServerReprocessStaleProposalError(proposal.id)

            row = AuthoritativeLocalCodeScanResult(
                id=str(uuid.uuid4()),
                asset_id=proposal.asset_id,
                inventory_id=current.inventory_id,
                aisle_id=current.aisle_id,
                client_file_id=current.client_file_id,
                result_version=current.result_version + 1,
                supersedes_result_id=current.id,
                is_current=True,
                internal_code=code,
                quantity=qty if qty is not None else current.quantity,
                quantity_status="PRESENT" if qty is not None else current.quantity_status,
                source="SERVER_REPROCESS_ADOPTION",
                detected_internal_code=proposal.internal_code,
                detected_quantity=int(proposal.quantity)
                if proposal.quantity is not None
                else None,
                detected_symbology=current.detected_symbology,
                parser_version=current.parser_version,
                detector_version=current.detector_version,
                prepared_asset_sha256=current.prepared_asset_sha256,
                content_hash=f"adopt:{run_id}:{proposal.id}:{code}:{qty}",
                confirmed_by=adopted_by,
                client_confirmed_at=now,
                server_confirmed_at=now,
                server_received_at=now,
                confirmed_at=now,
                applied_job_id=None,
                applied_at=None,
                row_version=1,
                schema_version=current.schema_version,
                created_at=now,
                updated_at=now,
            )
            saved = self._auth_repo.create_authoritative_version(
                new_result=row,
                expected_current_id=current.id,
                expected_row_version=current.row_version,
            )
            new_result_id = saved.id

        if self._position_repo is not None and proposal.previous_position_id:
            position = self._position_repo.get_by_id(proposal.previous_position_id)
            if position is None:
                raise ServerReprocessAdoptionConflictError(
                    f"Position {proposal.previous_position_id} missing for adoption"
                )
            prior = dict(position.corrected_summary_json or position.detected_summary_json or {})
            prior_history = list(prior.get("adoption_history") or [])
            prior_history.append(
                {
                    "superseded_at": now.isoformat(),
                    "previous_internal_code": prior.get("internal_code"),
                    "previous_quantity": prior.get("quantity"),
                    "adopted_from_run_id": run_id,
                    "adopted_from_proposal_id": proposal.id,
                }
            )
            corrected = {
                **prior,
                "source_asset_id": proposal.asset_id,
                "internal_code": code,
                "quantity": qty if qty is not None else prior.get("quantity"),
                "authoritative_result_id": new_result_id,
                "adopted_from_run_id": run_id,
                "adopted_from_proposal_id": proposal.id,
                "adopted_by": adopted_by,
                "adopted_at": now.isoformat(),
                "adoption_history": prior_history,
            }
            updated_position = replace(
                position,
                status=PositionStatus.CORRECTED,
                corrected_summary_json=corrected,
                needs_review=False,
                updated_at=now,
            )
            self._position_repo.save(updated_position)
            new_position_id = updated_position.id

        return new_result_id, new_position_id
