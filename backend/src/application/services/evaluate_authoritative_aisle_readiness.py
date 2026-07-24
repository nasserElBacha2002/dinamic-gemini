"""Evaluate authoritative aisle readiness for local-authority finalization (Phase 6).

Fail-closed: every PHOTO asset must be CONFIRMED_AND_APPLIED (authoritative row with
applied_at) or explicitly EXCLUDED. Backend is the authority — counters are derived
from persisted rows only.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from src.application.ports.authoritative_aisle_finalization_repository import (
    AuthoritativeAisleFinalizationRepository,
)
from src.application.ports.authoritative_local_code_scan_repository import (
    AuthoritativeLocalCodeScanRepository,
)
from src.application.ports.repositories import PositionRepository, SourceAssetRepository
from src.domain.assets.entities import SourceAssetType
from src.domain.authoritative_aisle_finalization.entities import (
    AuthoritativeAisleReadinessStatus,
    AuthoritativeReadinessReason,
)


@dataclass(frozen=True)
class AuthoritativeAisleReadinessResult:
    status: AuthoritativeAisleReadinessStatus
    total_images: int
    applied_images: int
    excluded_images: int
    pending_images: int
    conflicted_images: int
    failed_images: int
    reasons: tuple[str, ...]
    unique_codes: int
    total_quantity: int


class EvaluateAuthoritativeAisleReadiness:
    def __init__(
        self,
        *,
        asset_repo: SourceAssetRepository,
        authoritative_repo: AuthoritativeLocalCodeScanRepository,
        finalization_repo: AuthoritativeAisleFinalizationRepository,
        position_repo: PositionRepository | None = None,
        enabled: bool,
    ) -> None:
        self._asset_repo = asset_repo
        self._auth_repo = authoritative_repo
        self._fin_repo = finalization_repo
        self._position_repo = position_repo
        self._enabled = enabled

    def execute(
        self, *, inventory_id: str, aisle_id: str
    ) -> AuthoritativeAisleReadinessResult:
        if not self._enabled:
            return AuthoritativeAisleReadinessResult(
                status=AuthoritativeAisleReadinessStatus.BLOCKED,
                total_images=0,
                applied_images=0,
                excluded_images=0,
                pending_images=0,
                conflicted_images=0,
                failed_images=0,
                reasons=(AuthoritativeReadinessReason.FEATURE_DISABLED.value,),
                unique_codes=0,
                total_quantity=0,
            )

        current_fin = self._fin_repo.get_current_for_aisle(aisle_id)
        if (
            current_fin is not None
            and current_fin.status == "COMPLETED_BY_LOCAL_AUTHORITY"
        ):
            return AuthoritativeAisleReadinessResult(
                status=AuthoritativeAisleReadinessStatus.BLOCKED,
                total_images=current_fin.total_assets,
                applied_images=current_fin.applied_assets,
                excluded_images=current_fin.excluded_assets,
                pending_images=0,
                conflicted_images=0,
                failed_images=0,
                reasons=(AuthoritativeReadinessReason.AISLE_ALREADY_FINALIZED.value,),
                unique_codes=0,
                total_quantity=0,
            )

        assets = [
            a
            for a in self._asset_repo.list_by_aisle(aisle_id)
            if a.type == SourceAssetType.PHOTO
        ]
        exclusions = list(
            self._fin_repo.list_current_exclusions(
                inventory_id=inventory_id, aisle_id=aisle_id
            )
        )
        excluded_ids = {e.asset_id for e in exclusions}
        rows = list(
            self._auth_repo.list_current_for_aisle(
                inventory_id=inventory_id, aisle_id=aisle_id
            )
        )
        by_asset = {r.asset_id: r for r in rows}

        reasons: list[str] = []
        applied = 0
        pending = 0
        conflicted = 0
        failed = 0
        codes: list[str] = []
        qty_sum = 0

        for asset in assets:
            if asset.id in excluded_ids:
                continue
            row = by_asset.get(asset.id)
            if row is None:
                pending += 1
                reasons.append(AuthoritativeReadinessReason.PENDING_CONFIRMATION.value)
                continue
            if row.inventory_id != inventory_id or row.aisle_id != aisle_id:
                conflicted += 1
                reasons.append(AuthoritativeReadinessReason.SESSION_INCONSISTENT.value)
                continue
            if row.applied_at is None:
                pending += 1
                reasons.append(AuthoritativeReadinessReason.PENDING_FINAL_APPLY.value)
                continue
            applied += 1
            codes.append(row.internal_code)
            if row.quantity is not None:
                qty_sum += int(row.quantity)

        # Exclusions for assets no longer in aisle still count as decided.
        excluded_count = len(excluded_ids)
        # Assets present and excluded also count in total.
        present_excluded = sum(1 for a in assets if a.id in excluded_ids)
        total = len(assets) + max(0, excluded_count - present_excluded)

        # Duplicate current positions for same asset → BLOCKED.
        if self._position_repo is not None:
            positions = list(self._position_repo.list_by_aisle(aisle_id))
            asset_counts = Counter(
                getattr(p, "source_asset_id", None) or getattr(p, "asset_id", None)
                for p in positions
                if (getattr(p, "source_asset_id", None) or getattr(p, "asset_id", None))
            )
            for aid, n in asset_counts.items():
                if aid and n > 1:
                    conflicted += 1
                    reasons.append(
                        AuthoritativeReadinessReason.DUPLICATE_CURRENT_POSITION.value
                    )

        # Dedupe reason codes while preserving order.
        seen: set[str] = set()
        uniq_reasons: list[str] = []
        for r in reasons:
            if r not in seen:
                seen.add(r)
                uniq_reasons.append(r)

        if conflicted > 0 or AuthoritativeReadinessReason.SESSION_INCONSISTENT.value in seen:
            status = AuthoritativeAisleReadinessStatus.BLOCKED
        elif pending > 0 or failed > 0:
            status = AuthoritativeAisleReadinessStatus.NOT_READY
        elif total == 0:
            status = AuthoritativeAisleReadinessStatus.NOT_READY
            uniq_reasons = [AuthoritativeReadinessReason.ASSET_MISSING.value]
        elif applied + excluded_count >= total and pending == 0:
            status = AuthoritativeAisleReadinessStatus.READY
            uniq_reasons = []
        else:
            status = AuthoritativeAisleReadinessStatus.NOT_READY
            if not uniq_reasons:
                uniq_reasons = [AuthoritativeReadinessReason.PHOTO_NOT_DECIDED.value]

        return AuthoritativeAisleReadinessResult(
            status=status,
            total_images=total,
            applied_images=applied,
            excluded_images=excluded_count,
            pending_images=pending,
            conflicted_images=conflicted,
            failed_images=failed,
            reasons=tuple(uniq_reasons),
            unique_codes=len(set(codes)),
            total_quantity=qty_sum,
        )
