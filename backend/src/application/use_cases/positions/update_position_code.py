"""
UpdatePositionCode use case — v3.4 (Sprint 4.5).

Corrects the effective position_code for a position; sets position to corrected and records ReviewAction.

When POSITION_FLEXIBLE_REVIEW_ENABLED and auto-materialization are on, the code is
validated via CanonicalPositionValidator and materialize/reuse is required before accept.
"""

from __future__ import annotations

import hashlib
import uuid

from src.application.dto.access_principal import AccessPrincipal
from src.application.dto.position_materialization import MaterializePositionCommand
from src.application.ports.clock import Clock
from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
    PositionRepository,
    ReviewActionRepository,
)
from src.application.services.aisle_review_lifecycle_sync import AisleReviewLifecycleSync
from src.application.services.position_materialization.service import MaterializePositionService
from src.application.services.position_recognition import (
    AcceptPositionCoordinator,
    AcceptPositionRequest,
    CanonicalPositionValidationCommand,
    CanonicalPositionValidator,
    FlexiblePositionChannel,
    normalize_position_code,
)
from src.application.use_cases.shared.review_validation import (
    ensure_position_not_deleted,
    ensure_review_job_matches_position,
    resolve_position,
    storage_job_id_for_review_audit,
)
from src.domain.inventory.write_policy import require_inventory_writable
from src.domain.label_validation import CandidateLabel
from src.domain.label_validation.context import LabelValidationContext
from src.domain.position_recognition import (
    CanonicalPositionRecognition,
    PositionRecognitionSource,
    PositionSignatureEvidence,
    PositionSignatureVerification,
)
from src.domain.positions.entities import PositionReviewResolution, PositionStatus
from src.domain.reviews.entities import ReviewAction, ReviewActionType


class UpdatePositionCodeUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        position_repo: PositionRepository,
        review_repo: ReviewActionRepository,
        clock: Clock,
        aisle_review_sync: AisleReviewLifecycleSync,
        *,
        principal: AccessPrincipal | None = None,
        canonical_position_validator: CanonicalPositionValidator | None = None,
        accept_coordinator: AcceptPositionCoordinator | None = None,
        position_materializer: MaterializePositionService | None = None,
        flexible_review_enabled: bool = False,
        auto_materialization_enabled: bool = False,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._position_repo = position_repo
        self._review_repo = review_repo
        self._clock = clock
        self._aisle_review_sync = aisle_review_sync
        self._principal = principal
        self._canonical_position_validator = canonical_position_validator
        self._accept_coordinator = accept_coordinator
        self._position_materializer = position_materializer
        self._flexible_review_enabled = bool(flexible_review_enabled)
        self._auto_materialization_enabled = bool(auto_materialization_enabled)

    def execute(
        self,
        inventory_id: str,
        aisle_id: str,
        position_id: str,
        job_id: str | None,
        position_code: str,
    ) -> None:
        require_inventory_writable(
            self._inventory_repo.get_by_id(inventory_id),
            inventory_id=inventory_id,
        )
        position = resolve_position(
            self._inventory_repo,
            self._aisle_repo,
            self._position_repo,
            inventory_id,
            aisle_id,
            position_id,
        )
        ensure_position_not_deleted(position)
        ensure_review_job_matches_position(job_id, position)

        new_code = (position_code or "").strip()
        if not new_code:
            raise ValueError("position_code is required")
        normalized = normalize_position_code(new_code)

        location_id: str | None = None
        if self._flexible_review_enabled:
            location_id = self._validate_and_maybe_materialize(
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                position_id=position_id,
                raw_code=new_code,
                normalized_code=normalized.normalized_code,
            )
            if not (location_id or "").strip():
                raise ValueError("POSITION_LOCATION_ID_REQUIRED")

        now = self._clock.now()
        before_code = position.corrected_position_code
        before_resolution = (
            position.review_resolution.value if position.review_resolution is not None else None
        )

        position.corrected_position_code = normalized.normalized_code
        position.status = PositionStatus.CORRECTED
        position.review_resolution = PositionReviewResolution.POSITION_CODE_CORRECTED
        position.needs_review = False
        position.updated_at = now

        self._position_repo.save(position)

        after_json: dict[str, str | None] = {
            "corrected_position_code": normalized.normalized_code,
            "raw_position_code": new_code,
            "review_resolution": PositionReviewResolution.POSITION_CODE_CORRECTED.value,
        }
        if location_id is not None:
            after_json["location_id"] = location_id

        review = ReviewAction(
            id=str(uuid.uuid4()),
            position_id=position_id,
            action_type=ReviewActionType.UPDATE_POSITION_CODE,
            before_json={
                "corrected_position_code": before_code,
                "review_resolution": before_resolution,
            },
            after_json=after_json,
            created_at=now,
            job_id=storage_job_id_for_review_audit(position),
        )
        self._review_repo.save(review)
        self._aisle_review_sync.after_review_mutation(inventory_id, aisle_id)

    def _validate_and_maybe_materialize(
        self,
        *,
        inventory_id: str,
        aisle_id: str,
        position_id: str,
        raw_code: str,
        normalized_code: str,
    ) -> str | None:
        if self._canonical_position_validator is None:
            raise ValueError("POSITION_FLEXIBLE_REVIEW requires canonical position validator")
        inventory = self._inventory_repo.get_by_id(inventory_id)
        client_id = inventory.client_id if inventory is not None else None
        validation = self._canonical_position_validator.validate(
            CanonicalPositionValidationCommand(
                candidate=CandidateLabel(raw_payload=raw_code),
                source=PositionRecognitionSource.MANUAL,
                context=LabelValidationContext(
                    resolved_profiles=None,
                    client_id=client_id.strip() if isinstance(client_id, str) and client_id else None,
                ),
            )
        )
        if self._accept_coordinator is None:
            if not validation.operationally_accepted:
                raise ValueError(
                    validation.error_code or validation.status.value or "POSITION_REJECTED"
                )
            location_id = (validation.existing_position_label_id or "").strip() or None
            if location_id is None:
                raise ValueError("POSITION_LOCATION_ID_REQUIRED")
            return location_id

        materialize_command = None
        if self._auto_materialization_enabled:
            if self._principal is None:
                raise ValueError("POSITION_FLEXIBLE_REVIEW materialization requires principal")
            recognition = validation.recognition or CanonicalPositionRecognition(
                raw_code=raw_code,
                normalized_code=normalized_code,
                source=PositionRecognitionSource.MANUAL,
                signature=PositionSignatureEvidence(
                    present=False,
                    verification=PositionSignatureVerification.NOT_APPLICABLE,
                ),
            )
            identity = "\x00".join(
                (inventory_id.strip(), aisle_id.strip(), position_id.strip(), normalized_code)
            ).encode("utf-8")
            materialize_command = MaterializePositionCommand(
                recognition=recognition,
                inventory_id=inventory_id,
                aisle_id=aisle_id,
                principal=self._principal,
                idempotency_key=f"review-pos:{hashlib.sha256(identity).hexdigest()}",
                capture_id=position_id,
            )

        outcome = self._accept_coordinator.accept(
            AcceptPositionRequest(
                validation=validation,
                channel=FlexiblePositionChannel.REVIEW,
                materialize_command=materialize_command,
            )
        )
        if not outcome.accepted:
            raise ValueError(outcome.error_code or "POSITION_REJECTED")
        location_id = (outcome.location_id or "").strip() or None
        if location_id is None:
            raise ValueError("POSITION_LOCATION_ID_REQUIRED")

        materialization = outcome.materialization
        if (
            materialization is not None
            and (materialization.request_id or "").strip()
            and self._position_materializer is not None
        ):
            # Durable association for review-driven materialization (Phase 3 ports).
            self._position_materializer.complete_association(
                materialization.request_id,
                success=True,
                now=self._clock.now(),
            )
        return location_id
