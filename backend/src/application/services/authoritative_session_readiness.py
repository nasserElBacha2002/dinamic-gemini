"""Backend readiness for authoritative local CODE_SCAN before /process."""

from __future__ import annotations

from dataclasses import dataclass

from src.application.ports.authoritative_local_code_scan_repository import (
    AuthoritativeLocalCodeScanRepository,
)
from src.application.ports.repositories import SourceAssetRepository
from src.domain.assets.entities import SourceAssetType


@dataclass(frozen=True)
class AuthoritativeSessionReadinessResult:
    ready: bool
    total_assets: int
    with_current_result: int
    missing_asset_ids: tuple[str, ...]
    reasons: tuple[str, ...]


class AuthoritativeSessionReadiness:
    """Hybrid readiness for authoritative local CODE_SCAN.

    Photos *with* a current authoritative row use LOCAL_AUTHORITY at process time.
    Photos *without* a row fall through to remote CODE_SCAN.

    Missing rows are therefore **not** a hard block — only scope mismatches are.
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
                continue
            if row.inventory_id != inventory_id or row.aisle_id != aisle_id:
                reasons.append(f"scope_mismatch:{asset.id}")
                continue
            with_current += 1

        # Hybrid: missing authoritative rows are expected (remote CODE_SCAN).
        ready = not reasons
        return AuthoritativeSessionReadinessResult(
            ready=ready,
            total_assets=len(assets),
            with_current_result=with_current,
            missing_asset_ids=tuple(missing),
            reasons=tuple(reasons),
        )

    def require_ready(self, *, inventory_id: str, aisle_id: str) -> None:
        """Raise only on hard scope errors — never on missing local confirms."""
        from src.application.errors import AuthoritativeSessionNotReadyError

        result = self.evaluate(inventory_id=inventory_id, aisle_id=aisle_id)
        if not result.ready:
            raise AuthoritativeSessionNotReadyError(
                "Authoritative local results have scope conflicts for aisle processing",
                reasons=result.reasons,
            )
