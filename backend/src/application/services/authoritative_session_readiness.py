"""Backend readiness for authoritative local CODE_SCAN before /process.

Fail-closed when enabled: every PHOTO asset must have a current authoritative row
(or the caller must not use skip-remote). Missing rows block /process so remote
CODE_SCAN is never an implicit fallback after local authority is opted in.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.ports.authoritative_local_code_scan_repository import (
    AuthoritativeLocalCodeScanRepository,
)
from src.application.ports.repositories import SourceAssetRepository
from src.domain.assets.entities import SourceAssetType
from src.domain.authoritative_aisle_finalization.entities import AuthoritativeReadinessReason


@dataclass(frozen=True)
class AuthoritativeSessionReadinessResult:
    ready: bool
    total_assets: int
    with_current_result: int
    missing_asset_ids: tuple[str, ...]
    reasons: tuple[str, ...]
    #: True when every photo has a current authoritative row (ready to apply positions).
    can_apply: bool
    #: Finalize requires applied positions — always False here (use EvaluateAuthoritativeAisleReadiness).
    can_finalize: bool


class AuthoritativeSessionReadiness:
    """Fail-closed apply readiness for authoritative local CODE_SCAN.

    Aligns with EvaluateAuthoritativeAisleReadiness.can_apply: missing current rows
    block processing when the skip-remote / local-authority path is enabled.
    """

    def __init__(
        self,
        *,
        asset_repo: SourceAssetRepository,
        authoritative_repo: AuthoritativeLocalCodeScanRepository,
        enabled: bool,
    ) -> None:
        self._asset_repo = asset_repo
        self._repo = authoritative_repo
        self._enabled = enabled

    def evaluate(
        self, *, inventory_id: str, aisle_id: str
    ) -> AuthoritativeSessionReadinessResult:
        if not self._enabled:
            return AuthoritativeSessionReadinessResult(
                ready=True,
                total_assets=0,
                with_current_result=0,
                missing_asset_ids=(),
                reasons=(),
                can_apply=True,
                can_finalize=False,
            )

        assets = [
            a
            for a in self._asset_repo.list_by_aisle(aisle_id)
            if a.type == SourceAssetType.PHOTO
        ]
        rows = list(
            self._repo.list_current_for_aisle(
                inventory_id=inventory_id, aisle_id=aisle_id
            )
        )
        by_asset = {r.asset_id: r for r in rows}
        missing: list[str] = []
        reasons: list[str] = []
        with_current = 0
        for asset in assets:
            row = by_asset.get(asset.id)
            if row is None:
                missing.append(asset.id)
                reasons.append(AuthoritativeReadinessReason.PENDING_CONFIRMATION.value)
                continue
            if row.inventory_id != inventory_id or row.aisle_id != aisle_id:
                reasons.append(AuthoritativeReadinessReason.SESSION_INCONSISTENT.value)
                continue
            with_current += 1

        can_apply = len(missing) == 0 and AuthoritativeReadinessReason.SESSION_INCONSISTENT.value not in reasons
        # Fail-closed: no implicit remote CODE_SCAN for missing local confirms.
        ready = can_apply
        # Dedupe reasons
        seen: set[str] = set()
        uniq: list[str] = []
        for r in reasons:
            if r not in seen:
                seen.add(r)
                uniq.append(r)
        return AuthoritativeSessionReadinessResult(
            ready=ready,
            total_assets=len(assets),
            with_current_result=with_current,
            missing_asset_ids=tuple(missing),
            reasons=tuple(uniq),
            can_apply=can_apply,
            can_finalize=False,
        )

    def require_ready(self, *, inventory_id: str, aisle_id: str) -> None:
        """Raise when aisle cannot apply local authority for all assets (fail-closed)."""
        from src.application.errors import AuthoritativeSessionNotReadyError

        result = self.evaluate(inventory_id=inventory_id, aisle_id=aisle_id)
        if not result.ready:
            raise AuthoritativeSessionNotReadyError(
                "Authoritative local results incomplete for aisle processing "
                "(fail-closed; remote CODE_SCAN fallback disabled)",
                reasons=result.reasons,
            )
