"""Evaluate authoritative aisle readiness for local-authority apply/finalize (Phase 6).

Single policy surface:
- can_apply: every PHOTO has a current authoritative row (or is excluded)
- can_finalize: every PHOTO is CONFIRMED_AND_APPLIED (applied_at + applied_job_id +
  position) or EXCLUDED

Backend is the authority — counters are derived from persisted rows only.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

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


def position_source_asset_id(position: Any) -> str | None:
    """Extract source asset id from a Position (summary JSON or attribute)."""
    direct = getattr(position, "source_asset_id", None) or getattr(position, "asset_id", None)
    if direct:
        return str(direct)
    summary = getattr(position, "detected_summary_json", None) or {}
    if isinstance(summary, dict):
        aid = summary.get("source_asset_id") or summary.get("source_image_id")
        if aid:
            return str(aid)
    return None


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
    can_apply: bool
    can_finalize: bool
    #: asset_id → position_id for applied rows (empty when unknown).
    position_ids_by_asset: tuple[tuple[str, str], ...] = ()


class EvaluateAuthoritativeAisleReadiness:
    def __init__(
        self,
        *,
        asset_repo: SourceAssetRepository,
        authoritative_repo: AuthoritativeLocalCodeScanRepository,
        finalization_repo: AuthoritativeAisleFinalizationRepository,
        position_repo: PositionRepository | None = None,
        enabled: bool,
        require_position_for_applied: bool = True,
    ) -> None:
        self._asset_repo = asset_repo
        self._auth_repo = authoritative_repo
        self._fin_repo = finalization_repo
        self._position_repo = position_repo
        self._enabled = enabled
        self._require_position = require_position_for_applied

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
                can_apply=False,
                can_finalize=False,
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
                can_apply=False,
                can_finalize=False,
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

        position_by_asset: dict[str, str] = {}
        if self._position_repo is not None:
            positions = list(self._position_repo.list_by_aisle(aisle_id))
            asset_counts: Counter[str] = Counter()
            for p in positions:
                aid = position_source_asset_id(p)
                if not aid:
                    continue
                asset_counts[aid] += 1
                pid = getattr(p, "id", None)
                if pid and aid not in position_by_asset:
                    position_by_asset[aid] = str(pid)
        else:
            asset_counts = Counter()

        reasons: list[str] = []
        applied = 0
        pending = 0
        conflicted = 0
        failed = 0
        codes: list[str] = []
        qty_sum = 0
        missing_confirm = 0
        applied_pairs: list[tuple[str, str]] = []

        for asset in assets:
            if asset.id in excluded_ids:
                continue
            row = by_asset.get(asset.id)
            if row is None:
                pending += 1
                missing_confirm += 1
                reasons.append(AuthoritativeReadinessReason.PENDING_CONFIRMATION.value)
                continue
            if row.inventory_id != inventory_id or row.aisle_id != aisle_id:
                conflicted += 1
                reasons.append(AuthoritativeReadinessReason.SESSION_INCONSISTENT.value)
                continue
            if row.applied_at is None or not row.applied_job_id:
                pending += 1
                reasons.append(AuthoritativeReadinessReason.PENDING_FINAL_APPLY.value)
                continue
            if self._require_position and self._position_repo is not None:
                pos_id = position_by_asset.get(asset.id)
                if not pos_id:
                    pending += 1
                    reasons.append(AuthoritativeReadinessReason.POSITION_MISSING.value)
                    continue
                if asset_counts.get(asset.id, 0) > 1:
                    conflicted += 1
                    reasons.append(
                        AuthoritativeReadinessReason.DUPLICATE_CURRENT_POSITION.value
                    )
                    continue
                applied_pairs.append((asset.id, pos_id))
            applied += 1
            codes.append(row.internal_code)
            if row.quantity is not None:
                qty_sum += int(row.quantity)

        excluded_count = len(excluded_ids)
        present_excluded = sum(1 for a in assets if a.id in excluded_ids)
        total = len(assets) + max(0, excluded_count - present_excluded)

        seen: set[str] = set()
        uniq_reasons: list[str] = []
        for r in reasons:
            if r not in seen:
                seen.add(r)
                uniq_reasons.append(r)

        can_apply = (
            total > 0
            and missing_confirm == 0
            and conflicted == 0
            and AuthoritativeReadinessReason.SESSION_INCONSISTENT.value not in seen
        )
        can_finalize = (
            total > 0
            and pending == 0
            and failed == 0
            and conflicted == 0
            and applied + excluded_count >= total
        )

        if conflicted > 0 or AuthoritativeReadinessReason.SESSION_INCONSISTENT.value in seen:
            status = AuthoritativeAisleReadinessStatus.BLOCKED
        elif can_finalize:
            status = AuthoritativeAisleReadinessStatus.READY
            uniq_reasons = []
        elif total == 0:
            status = AuthoritativeAisleReadinessStatus.NOT_READY
            uniq_reasons = [AuthoritativeReadinessReason.ASSET_MISSING.value]
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
            can_apply=can_apply,
            can_finalize=can_finalize,
            position_ids_by_asset=tuple(applied_pairs),
        )
