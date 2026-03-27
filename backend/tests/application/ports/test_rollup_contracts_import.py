"""Ensure AisleAssetRollup loads without pulling heavy contracts (worker / SQL repo init path)."""

from src.application.ports.rollup_contracts import AisleAssetRollup


def test_aisle_asset_rollup_constructible() -> None:
    r = AisleAssetRollup(count=0, last_uploaded_at=None)
    assert r.count == 0


def test_contracts_reexports_same_type() -> None:
    from src.application.ports.contracts import AisleAssetRollup as FromContracts

    assert FromContracts is AisleAssetRollup
